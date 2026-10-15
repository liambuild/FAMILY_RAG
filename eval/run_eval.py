"""Mesure de qualité et de latence du RAG sur eval/corpus/ (Ollama requis, hors pytest).

    .venv/bin/python eval/run_eval.py --label lot-1b --llm gemma3:4b
    .venv/bin/python eval/run_eval.py --label v1-legacy --app-dir /chemin/vers/worktree/app
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


def grade(question: dict, answer: str, sources: list[str]) -> dict:
    """Notes d'une réponse. Les listes `sources` et la réponse sont celles du moteur."""
    expected = question.get("expected_sources", [])
    ranks = [next((i + 1 for i, s in enumerate(sources) if source_matches(s, e)), None) for e in expected]
    normalized_answer = normalize(answer)

    elements = question.get("key_elements", [])
    found = 0
    for element in elements:
        variants = element if isinstance(element, list) else [element]
        found += any(normalize(v) in normalized_answer for v in variants)

    cited = sorted({m.group(0) for m in CITATION.finditer(answer)})
    retrieved_names = {Path(s).name for s in sources}
    result = {
        "source_ranks": ranks,
        "source_hit": all(r is not None for r in ranks) if expected else None,
        "key_elements_found": found,
        "key_elements_total": len(elements),
        "cited_files": cited,
        "citations_valid": all(Path(c).name in retrieved_names for c in cited) if cited else None,
    }
    if question.get("abstain"):
        result["abstained"] = any(marker in normalized_answer for marker in ABSTENTION)
    return result


def summarize(rows: list[dict]) -> dict:
    """Agrégats d'un mode : tout, puis hors écarts connus (`known_gap`)."""
    def block(subset: list[dict]) -> dict:
        measured = [r for r in subset if not r.get("skipped")]
        latencies = [r["latency_s"] for r in measured]
        with_sources = [r for r in measured if r["source_hit"] is not None]
        with_elements = [r for r in measured if r["key_elements_total"]]
        cited = [r for r in measured if r["citations_valid"] is not None]
        abstain = [r for r in measured if "abstained" in r]

        def rate(items: list[dict], test) -> str | None:
            return f"{sum(1 for r in items if test(r))}/{len(items)}" if items else None

        return {
            "questions": len(measured),
            "latency_p50_s": percentile(latencies, 0.5),
            "latency_p95_s": percentile(latencies, 0.95),
            "latency_mean_s": round(statistics.mean(latencies), 2) if latencies else None,
            "source_found": rate(with_sources, lambda r: r["source_hit"]),
            "key_elements_complete": rate(with_elements, lambda r: r["key_elements_found"] == r["key_elements_total"]),
            "answers_with_citation": rate(measured, lambda r: r["cited_files"]),
            "citations_valid": rate(cited, lambda r: r["citations_valid"]),
            "good_abstentions": rate(abstain, lambda r: r["abstained"]),
        }

    return {"all": block(rows), "without_known_gaps": block([r for r in rows if not r.get("known_gap")])}


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

    base_url = f"http://{args.ollama_host}"
    infos = ollama_checks(base_url, [args.llm, args.embedding])

    origin = Path.cwd()
    with tempfile.TemporaryDirectory(prefix="family-rag-eval-") as index_dir:
        os.environ.update(OLLAMA_HOST=args.ollama_host, EMBEDDING_MODEL=args.embedding, LLM_MODEL=args.llm,
                          DATA_DIR=str(EVAL_DIR / "corpus"), INDEX_DIR=index_dir)
        sys.path.insert(0, str(app_dir))
        os.chdir(index_dir)  # un éventuel .env du dossier courant ne doit pas s'appliquer
        logging.disable(logging.INFO)
        from config import get_settings
        from rag_engine import RAGEngine

        settings = get_settings()
        engine = RAGEngine()

        started = time.perf_counter()
        indexing = engine.index_documents()
        index_s = round(time.perf_counter() - started, 1)
        if not indexing.get("success"):
            sys.exit(f"Indexation échouée : {indexing}")
        print(f"Indexation : {indexing.get('documents')} documents, {indexing.get('chunks')} chunks, {index_s} s", file=sys.stderr)

        started = time.perf_counter()
        # Charge le modèle en mémoire sans rien générer (prompt vide) : exclu des latences mesurées
        httpx.post(f"{base_url}/api/generate", json={"model": args.llm, "prompt": "", "keep_alive": "30m"}, timeout=1800)
        warmup_s = round(time.perf_counter() - started, 1)

        modes = {"off": [False], "on": [True], "both": [False, True]}[args.rerank]
        results = {}
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
                started = time.perf_counter()
                result = engine.query(question["question"], enable_reranking=rerank)
                latency = round(time.perf_counter() - started, 2)
                sources = [s["source"] for s in result.sources]
                row.update(latency_s=latency, answer=result.answer, sources=sources,
                           **grade(question, result.answer, sources))
                rows.append(row)
                print(f"[{name}] Q{question['id']:>2} {latency:>6.1f} s  source={row['source_hit']}  "
                      f"éléments={row['key_elements_found']}/{row['key_elements_total']}", file=sys.stderr)
            results[name] = {"questions": rows, "summary": summarize(rows)}

        os.chdir(origin)
        meta = {
            "label": args.label, "date": datetime.now().isoformat(timespec="seconds"),
            "code": command_output("git", "-C", str(app_dir), "describe", "--tags", "--always", "--dirty"),
            "app_dir": str(app_dir), "machine": machine_info(), **infos,
            "llm": settings.llm_model, "embedding": settings.embedding_model,
            "parameters": {"top_k": settings.top_k, "temperature": settings.temperature,
                           "chunk_size": settings.chunk_size, "chunk_overlap": settings.chunk_overlap},
            "index": {"documents": indexing.get("documents"), "chunks": indexing.get("chunks"), "seconds": index_s},
            "warmup_s": warmup_s,
            "source_matching": "chemin relatif exact ; nom de base si le moteur ne renvoie que des noms (v1-legacy)",
            "heuristics": "citations = noms de fichiers cités dans la réponse ; abstention = formules d'aveu d'ignorance",
        }
    return {"meta": meta, "results": results}


def print_report(report: dict) -> None:
    meta = report["meta"]
    print(f"\n== {meta['label']} — {meta['code']} — {meta['llm']} / {meta['embedding']} — "
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
            changes = [f"{k}: {row[k]} → {other[k]}" for k in ("source_hit", "key_elements_found", "citations_valid")
                       if row[k] != other[k]]
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
    parser.add_argument("--only", type=int, nargs="+", help="numéros de questions à poser")
    parser.add_argument("--output", help="fichier JSON (défaut : eval/results/<label>.json)")
    parser.add_argument("--compare", nargs=2, metavar=("A.json", "B.json"), help="compare deux mesures et quitte")
    args = parser.parse_args()

    if args.compare:
        compare(*args.compare)
        return
    report = run(args)
    output = Path(args.output).resolve() if args.output else EVAL_DIR / "results" / f"{args.label}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print_report(report)
    print(f"\nRésultats : {output}")


if __name__ == "__main__":
    main()
