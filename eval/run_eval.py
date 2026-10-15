"""Mesure de qualité et de latence du RAG sur eval/corpus/ (Ollama requis, hors pytest).

    .venv/bin/python eval/run_eval.py --label lot-1b --llm gemma3:4b
    .venv/bin/python eval/run_eval.py --label v1-legacy --app-dir /chemin/vers/worktree/app
    .venv/bin/python eval/run_eval.py --label lot-1b-retrieval --retrieval-only   # sans génération
    .venv/bin/python eval/run_eval.py --compare eval/results/a.json eval/results/b.json

L'index est construit dans un dossier temporaire supprimé en fin de run : l'index de
l'utilisateur n'est jamais lu, modifié ni supprimé.
"""

import argparse
import json
import logging
import os
import platform
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
from datetime import datetime
from pathlib import Path

import httpx
import yaml

EVAL_DIR = Path(__file__).resolve().parent
REPO_DIR = EVAL_DIR.parent
CITATION = re.compile(r"[\w\-./]+\.(?:pdf|docx|eml|md|txt|png|jpe?g|csv)", re.IGNORECASE)
ABSTENTION = [
    "ne trouve pas", "pas d'information", "aucune information", "pas mentionn", "n'est pas mentionn",
    "ne sais pas", "ne contiennent pas", "ne contient pas", "pas precis", "n'est pas precis",
    "pas disponible", "ne permet pas", "ne permettent pas", "aucun document", "aucune mention",
    "impossible de repondre", "pas en mesure",
]


def normalize(text: str) -> str:
    """Minuscules, sans accents, espaces (dont insécables) réduits à un seul."""
    text = unicodedata.normalize("NFKD", text.replace(" ", " ").replace(" ", " ")).lower()
    text = "".join(c for c in text if not unicodedata.combining(c)).replace("’", "'")
    return re.sub(r"\s+", " ", text)


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    low, high = int(position), min(int(position) + 1, len(ordered) - 1)
    return round(ordered[low] + (ordered[high] - ordered[low]) * (position - low), 2)


def source_matches(retrieved: str, expected: str) -> bool:
    """Chemin relatif exact ; sous v1-legacy, `source` n'est qu'un nom de fichier (comparaison au nom de base)."""
    return retrieved == expected or ("/" not in retrieved and retrieved == Path(expected).name)


def is_abstention(answer: str) -> bool:
    """La réponse avoue-t-elle ne pas savoir ? Détection par formules (ABSTENTION), insensible à la casse et aux accents."""
    normalized_answer = normalize(answer)
    return any(marker in normalized_answer for marker in ABSTENTION)


def grade_retrieval(question: dict, sources: list[str]) -> dict:
    """Notes de la seule recherche. `sources` : sources des extraits retrouvés, dans l'ordre (les top_k premiers).

    `recall_at_k` : part des sources attendues retrouvées parmi ces extraits (None si aucune n'est attendue).
    """
    expected = question.get("expected_sources", [])
    ranks = [next((i + 1 for i, s in enumerate(sources) if source_matches(s, e)), None) for e in expected]
    return {
        "source_ranks": ranks,
        "source_hit": all(r is not None for r in ranks) if expected else None,
        "recall_at_k": sum(r is not None for r in ranks) / len(expected) if expected else None,
    }


def cites_expected_source(question: dict, cited: list[str]) -> bool | None:
    """F3 : la réponse cite-t-elle au moins une des sources attendues ? None si la question n'en attend aucune."""
    expected = question.get("expected_sources", [])
    if not expected:
        return None
    return any(source_matches(c, e) for c in cited for e in expected)


def grade(question: dict, answer: str, sources: list[str]) -> dict:
    """Notes d'une réponse. Les listes `sources` et la réponse sont celles du moteur."""
    normalized_answer = normalize(answer)

    elements = question.get("key_elements", [])
    found = 0
    for element in elements:
        variants = element if isinstance(element, list) else [element]
        found += any(normalize(v) in normalized_answer for v in variants)

    cited = sorted({m.group(0) for m in CITATION.finditer(answer)})
    retrieved_names = {Path(s).name for s in sources}
    result = {
        **grade_retrieval(question, sources),
        "key_elements_found": found,
        "key_elements_total": len(elements),
        "cited_files": cited,
        "citations_valid": all(Path(c).name in retrieved_names for c in cited) if cited else None,
        "cites_expected_source": cites_expected_source(question, cited),
    }
    if question.get("abstain"):
        result["abstained"] = is_abstention(answer)
    return result


def throughput(rows: list[dict], count: str, duration: str) -> float | None:
    """Tokens par seconde sur l'ensemble des appels (durées Ollama en nanosecondes)."""
    tokens = sum(r.get(count) or 0 for r in rows)
    nanoseconds = sum(r.get(duration) or 0 for r in rows)
    return round(tokens / (nanoseconds / 1e9), 1) if nanoseconds else None


def summarize(rows: list[dict]) -> dict:
    """Agrégats d'un mode : tout, puis hors écarts connus (`known_gap`)."""
    def block(subset: list[dict]) -> dict:
        measured = [r for r in subset if not r.get("skipped")]
        latencies = [r["latency_s"] for r in measured]
        with_sources = [r for r in measured if r["source_hit"] is not None]
        with_elements = [r for r in measured if r["key_elements_total"]]
        cited = [r for r in measured if r["citations_valid"] is not None]
        abstain = [r for r in measured if "abstained" in r]
        expecting = [r for r in measured if r.get("cites_expected_source") is not None]

        def rate(items: list[dict], test) -> str | None:
            return f"{sum(1 for r in items if test(r))}/{len(items)}" if items else None

        return {
            "questions": len(measured),
            "latency_p50_s": percentile(latencies, 0.5),
            "latency_p95_s": percentile(latencies, 0.95),
            "latency_mean_s": round(statistics.mean(latencies), 2) if latencies else None,
            "prompt_tokens_p50": percentile([r["prompt_eval_count"] for r in measured if r.get("prompt_eval_count")], 0.5),
            "prompt_tokens_max": max((r["prompt_eval_count"] for r in measured if r.get("prompt_eval_count")), default=None),
            "prompt_tokens_per_s": throughput(measured, "prompt_eval_count", "prompt_eval_duration"),
            "generated_tokens_per_s": throughput(measured, "eval_count", "eval_duration"),
            "source_found": rate(with_sources, lambda r: r["source_hit"]),
            "key_elements_complete": rate(with_elements, lambda r: r["key_elements_found"] == r["key_elements_total"]),
            "answers_with_citation": rate(measured, lambda r: r["cited_files"]),
            "citations_valid": rate(cited, lambda r: r["citations_valid"]),
            "cites_expected_source": rate(expecting, lambda r: r["cites_expected_source"]),
            "good_abstentions": rate(abstain, lambda r: r["abstained"]),
        }

    return {"all": block(rows), "without_known_gaps": block([r for r in rows if not r.get("known_gap")])}


def summarize_retrieval(rows: list[dict]) -> dict:
    """Agrégats du mode --retrieval-only : recall@k moyen et sources attendues toutes retrouvées."""
    def block(subset: list[dict]) -> dict:
        measured = [r for r in subset if not r.get("skipped") and r["recall_at_k"] is not None]
        return {
            "questions": len(measured),
            "recall_at_k": round(statistics.mean(r["recall_at_k"] for r in measured), 3) if measured else None,
            "source_found": f"{sum(1 for r in measured if r['source_hit'])}/{len(measured)}" if measured else None,
            "search_p50_s": percentile([r["latency_s"] for r in measured], 0.5),
        }

    return {"all": block(rows), "without_known_gaps": block([r for r in rows if not r.get("known_gap")])}


def retrieve(engine, question: str, k: int) -> list[str]:
    """Sources des k extraits les plus proches, sans re-ranking ni génération (même recherche que RAGEngine.query)."""
    found = engine.vectorstore.similarity_search_with_score(question, k=k)
    return [doc.metadata.get("source", "") for doc, _ in found]


USAGE_FIELDS = ("prompt_eval_count", "prompt_eval_duration", "eval_count", "eval_duration")


class UsageCollector:
    """Cumule les compteurs renvoyés par Ollama (durées en nanosecondes) pour chaque appel au LLM.

    Branché sur `engine.llm.callbacks` : le code de app/ n'est pas modifié, ce qui permet de
    mesurer aussi bien lot-1b que v1-legacy. Avec le re-ranking, une question fait plusieurs appels ;
    `answer_call` est le dernier, c'est-à-dire la génération de la réponse.
    """

    def __init__(self) -> None:
        from langchain_core.callbacks import BaseCallbackHandler

        collector = self

        class Handler(BaseCallbackHandler):
            def on_llm_end(self, response, **kwargs) -> None:
                for generations in response.generations:
                    for generation in generations:
                        metadata = getattr(getattr(generation, "message", None), "response_metadata", None) or {}
                        collector.add({f: metadata.get(f) for f in USAGE_FIELDS})

        self.handler = Handler()
        self._lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        self.calls: list[dict] = []

    def add(self, call: dict) -> None:
        with self._lock:
            self.calls.append(call)

    def snapshot(self) -> dict:
        totals = {f: sum(c[f] or 0 for c in self.calls) for f in USAGE_FIELDS}
        return {"llm_calls": len(self.calls), **totals, "answer_call": self.calls[-1] if self.calls else None}


def command_output(*command: str) -> str | None:
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=10).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def machine_info() -> dict:
    cpu = next((l.split(":", 1)[1].strip() for l in Path("/proc/cpuinfo").read_text().splitlines()
                if l.startswith("model name")), None) if Path("/proc/cpuinfo").exists() else platform.processor()
    memory = None
    if Path("/proc/meminfo").exists():
        kib = int(Path("/proc/meminfo").read_text().split()[1])
        memory = f"{kib / 1024 / 1024:.1f} Go"
    return {
        "os": platform.platform(), "cpu": cpu, "cores": os.cpu_count(), "ram": memory,
        "gpu": "non détecté" if shutil.which("nvidia-smi") is None else "nvidia-smi présent",
        "python": platform.python_version(),
    }


def ollama_checks(base_url: str, models: list[str]) -> dict:
    """Vérifie que Ollama répond et que les modèles demandés sont installés ; renvoie version et empreintes."""
    try:
        version = httpx.get(f"{base_url}/api/version", timeout=10).json().get("version")
        installed = {m["name"]: m.get("digest", "")[:12] for m in httpx.get(f"{base_url}/api/tags", timeout=10).json()["models"]}
    except (httpx.HTTPError, KeyError, ValueError) as error:
        sys.exit(f"Ollama ne répond pas sur {base_url} : {error}")
    digests = {}
    for model in models:
        name = model if ":" in model else f"{model}:latest"
        if name not in installed:
            sys.exit(f"Modèle absent d'Ollama : {model} (ollama pull {model}). Installés : {', '.join(installed) or 'aucun'}")
        digests[model] = installed[name]
    return {"ollama_version": version, "model_digests": digests}


def run(args: argparse.Namespace) -> dict:
    app_dir = Path(args.app_dir).resolve()
    if not (app_dir / "rag_engine.py").exists():
        sys.exit(f"{app_dir} ne contient pas rag_engine.py (option --app-dir)")
    questions = yaml.safe_load((EVAL_DIR / "questions.yaml").read_text(encoding="utf-8"))
    if args.only:
        questions = [q for q in questions if q["id"] in args.only]

    if args.rerank != "off" and not args.retrieval_only:
        print("Attention : le timeout du re-ranking est inopérant (AUDIT.md S1, corrigé au lot 8) ; un Ollama lent "
              "peut bloquer une question sans limite. Mesure avec re-ranking à ne pas exploiter avant le lot 8.",
              file=sys.stderr)

    base_url = f"http://{args.ollama_host}"
    # Sans génération, seul le modèle d'embedding est nécessaire
    infos = ollama_checks(base_url, [args.embedding] if args.retrieval_only else [args.llm, args.embedding])

    origin = Path.cwd()
    with tempfile.TemporaryDirectory(prefix="family-rag-eval-") as index_dir:
        os.environ.update(OLLAMA_HOST=args.ollama_host, EMBEDDING_MODEL=args.embedding, LLM_MODEL=args.llm,
                          DATA_DIR=str(EVAL_DIR / "corpus"), INDEX_DIR=index_dir)
        if args.top_k:
            os.environ["TOP_K"] = str(args.top_k)
        sys.path.insert(0, str(app_dir))
        os.chdir(index_dir)  # un éventuel .env du dossier courant ne doit pas s'appliquer
        logging.disable(logging.INFO)
        from config import get_settings
        from rag_engine import RAGEngine

        settings = get_settings()
        engine = RAGEngine()
        usage = UsageCollector()
        if engine.llm:
            engine.llm.callbacks = [usage.handler]

        started = time.perf_counter()
        indexing = engine.index_documents()
        index_s = round(time.perf_counter() - started, 1)
        if not indexing.get("success"):
            sys.exit(f"Indexation échouée : {indexing}")
        print(f"Indexation : {indexing.get('documents')} documents, {indexing.get('chunks')} chunks, {index_s} s", file=sys.stderr)

        results = {}
        warmup_s = None
        if args.retrieval_only:
            rows = []
            for question in questions:
                row = {"id": question["id"], "category": question["category"], "question": question["question"],
                       "known_gap": question.get("known_gap")}
                started = time.perf_counter()
                sources = retrieve(engine, question["question"], settings.top_k)
                row.update(latency_s=round(time.perf_counter() - started, 3), sources=sources,
                           **grade_retrieval(question, sources))
                rows.append(row)
                print(f"[retrieval] Q{question['id']:>2} rangs={row['source_ranks']}  recall@{settings.top_k}={row['recall_at_k']}",
                      file=sys.stderr)
            results["retrieval"] = {"questions": rows, "summary": summarize_retrieval(rows)}

        started = time.perf_counter()
        if not args.retrieval_only:
            # Charge le modèle en mémoire sans rien générer (prompt vide) : exclu des latences mesurées
            httpx.post(f"{base_url}/api/generate", json={"model": args.llm, "prompt": "", "keep_alive": "30m"}, timeout=1800)
            warmup_s = round(time.perf_counter() - started, 1)

        modes = [] if args.retrieval_only else {"off": [False], "on": [True], "both": [False, True]}[args.rerank]
        for rerank in modes:
            name = "rerank_on" if rerank else "rerank_off"
            rows = []
            for question in questions:
                row = {"id": question["id"], "category": question["category"], "question": question["question"],
                       "known_gap": question.get("known_gap")}
                if question.get("requires") and not shutil.which(question["requires"]):
                    row.update(skipped=f"{question['requires']} absent de cette machine")
                    rows.append(row)
                    print(f"[{name}] Q{question['id']:>2} ignorée ({row['skipped']})", file=sys.stderr)
                    continue
                usage.reset()
                started = time.perf_counter()
                result = engine.query(question["question"], enable_reranking=rerank)
                latency = round(time.perf_counter() - started, 2)
                sources = [s["source"] for s in result.sources]
                row.update(latency_s=latency, answer=result.answer, sources=sources, **usage.snapshot(),
                           index_documents=indexing.get("documents"), **grade(question, result.answer, sources))
                rows.append(row)
                print(f"[{name}] Q{question['id']:>2} {latency:>6.1f} s  source={row['source_hit']}  "
                      f"éléments={row['key_elements_found']}/{row['key_elements_total']}  "
                      f"prompt={row['prompt_eval_count']} tok", file=sys.stderr)
            results[name] = {"questions": rows, "summary": summarize(rows)}

        os.chdir(origin)
        meta = {
            "label": args.label, "date": datetime.now().isoformat(timespec="seconds"),
            "code": command_output("git", "-C", str(app_dir), "describe", "--tags", "--always", "--dirty"),
            "app_dir": str(app_dir), "machine": machine_info(), **infos,
            "llm": None if args.retrieval_only else settings.llm_model, "embedding": settings.embedding_model,
            "retrieval_only": args.retrieval_only,
            "parameters": {"top_k": settings.top_k, "temperature": settings.temperature,
                           "chunk_size": settings.chunk_size, "chunk_overlap": settings.chunk_overlap},
            "index": {"documents": indexing.get("documents"), "chunks": indexing.get("chunks"), "seconds": index_s},
            "warmup_s": warmup_s,
            "note": args.note,
            "source_matching": "chemin relatif exact ; nom de base si le moteur ne renvoie que des noms (v1-legacy)",
            "heuristics": "citations = noms de fichiers cités dans la réponse ; abstention = formules d'aveu d'ignorance",
            "rerank_note": "re-ranking activé non mesurable avant la correction de S1 (lot 8)",
        }
    return {"meta": meta, "results": results}


def merge_into(path: Path, report: dict) -> dict:
    """Remplace dans une mesure existante les seules questions remesurées, puis recalcule les résumés."""
    previous = json.loads(path.read_text(encoding="utf-8"))
    for mode, data in report["results"].items():
        previous["results"].setdefault(mode, {"questions": [], "summary": {}})  # mode mesuré pour la première fois
        new_ids = {r["id"] for r in data["questions"]}
        rows = [r for r in previous["results"][mode]["questions"] if r["id"] not in new_ids] + data["questions"]
        rows.sort(key=lambda r: r["id"])
        previous["results"][mode] = {"questions": rows,
                                     "summary": summarize_retrieval(rows) if mode == "retrieval" else summarize(rows)}
    previous["meta"].setdefault("remeasured", []).append({
        "questions": sorted(new_ids), "date": report["meta"]["date"], "index": report["meta"]["index"],
        "code": report["meta"]["code"], "tesseract": bool(shutil.which("tesseract")),
        "modes": list(report["results"]), "note": report["meta"]["note"],
    })
    return previous


def print_report(report: dict) -> None:
    meta = report["meta"]
    print(f"\n== {meta['label']} — {meta['code']} — {meta['llm'] or 'sans LLM'} / {meta['embedding']} — "
          f"{meta['machine']['cores']} cœurs, {meta['machine']['ram']}, GPU : {meta['machine']['gpu']}")
    for mode, data in report["results"].items():
        print(f"\n[{mode}]")
        for key, value in data["summary"]["all"].items():
            without = data["summary"]["without_known_gaps"][key]
            print(f"  {key:<24} {str(value):>8}   (hors écarts connus : {without})")


def compare(path_a: str, path_b: str) -> None:
    a, b = (json.loads(Path(p).read_text(encoding="utf-8")) for p in (path_a, path_b))
    print(f"A = {a['meta']['label']} ({a['meta']['code']})   B = {b['meta']['label']} ({b['meta']['code']})")
    for mode in sorted(set(a["results"]) & set(b["results"])):
        print(f"\n[{mode}]")
        for key in a["results"][mode]["summary"]["all"]:
            print(f"  {key:<24} A={a['results'][mode]['summary']['all'][key]!s:>8}  B={b['results'][mode]['summary']['all'][key]!s:>8}")
        rows_b = {r["id"]: r for r in b["results"][mode]["questions"]}
        for row in a["results"][mode]["questions"]:
            other = rows_b.get(row["id"])
            if not other or row.get("skipped") or other.get("skipped"):
                continue
            changes = [f"{k}: {row.get(k)} → {other.get(k)}"
                       for k in ("source_hit", "key_elements_found", "citations_valid", "cites_expected_source")
                       if row.get(k) != other.get(k)]
            if changes:
                print(f"  Q{row['id']:>2} {'; '.join(changes)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--label", default="local", help="nom de la mesure (fichier de sortie)")
    parser.add_argument("--app-dir", default=str(REPO_DIR / "app"), help="dossier app/ à mesurer (ex. worktree v1-legacy)")
    parser.add_argument("--llm", default=os.environ.get("LLM_MODEL", "gemma3:4b"))
    parser.add_argument("--embedding", default=os.environ.get("EMBEDDING_MODEL", "nomic-embed-text"))
    parser.add_argument("--ollama-host", default=os.environ.get("OLLAMA_HOST", "127.0.0.1:11434"))
    parser.add_argument("--rerank", choices=["off", "on", "both"], default="off")
    parser.add_argument("--retrieval-only", action="store_true",
                        help="mesure seulement la recherche (rang des sources attendues, recall@k) : ni génération ni LLM, "
                             "seul le modèle d'embedding est requis")
    parser.add_argument("--top-k", type=int, help="nombre d'extraits retrouvés (défaut : réglage TOP_K de l'application)")
    parser.add_argument("--only", type=int, nargs="+", help="numéros de questions à poser")
    parser.add_argument("--merge", action="store_true",
                        help="avec --only : remplace ces questions dans le fichier de sortie existant au lieu de l'écraser")
    parser.add_argument("--note", default="", help="remarque libre enregistrée dans meta")
    parser.add_argument("--output", help="fichier JSON (défaut : eval/results/<label>.json)")
    parser.add_argument("--compare", nargs=2, metavar=("A.json", "B.json"), help="compare deux mesures et quitte")
    args = parser.parse_args()

    if args.compare:
        compare(*args.compare)
        return
    report = run(args)
    output = Path(args.output).resolve() if args.output else EVAL_DIR / "results" / f"{args.label}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    if args.merge:
        if not args.only or not output.exists():
            sys.exit("--merge exige --only et un fichier de sortie existant (--output ou --label)")
        report = merge_into(output, report)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print_report(report)
    print(f"\nRésultats : {output}")


if __name__ == "__main__":
    main()
