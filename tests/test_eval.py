"""Tests de la partie de eval/ qui n'a pas besoin d'Ollama : corpus, notation, recall@k.

Le script de mesure lui-même (indexation, génération) n'est pas testé ici : il exige Ollama.
"""

import sys
from pathlib import Path

import pytest
import yaml
from langchain_core.documents import Document

EVAL_DIR = Path(__file__).parent.parent / "eval"
sys.path.insert(0, str(EVAL_DIR))

import build_corpus  # noqa: E402
import run_eval  # noqa: E402

QUESTIONS = yaml.safe_load((EVAL_DIR / "questions.yaml").read_text(encoding="utf-8"))
BY_ID = {q["id"]: q for q in QUESTIONS}


def count_chunks(corpus: Path, data_dir_setting) -> int:
    """Nombre d'extraits indexés pour ce corpus, avec le chargeur et le splitter de l'application."""
    from config import get_settings
    from document_loader import DocumentLoader
    from structure_aware_splitter import StructureAwareSplitter

    settings = get_settings()
    data_dir_setting(str(corpus))
    documents = DocumentLoader().load_all()
    splitter = StructureAwareSplitter(chunk_size=settings.chunk_size, chunk_overlap=settings.chunk_overlap,
                                      min_chunk_size=100, max_chunk_size=1500)
    return len(splitter.split_documents(documents))


@pytest.fixture
def set_data_dir(monkeypatch):
    from config import get_settings

    return lambda path: monkeypatch.setattr(get_settings(), "data_dir", path)


# --- Construction du corpus ----------------------------------------------------

class TestCorpus:
    def test_built_corpus_has_at_least_four_times_top_k_chunks(self, tmp_path, set_data_dir):
        from config import get_settings

        build_corpus.build(tmp_path / "corpus")
        assert count_chunks(tmp_path / "corpus", set_data_dir) >= 4 * get_settings().top_k

    def test_committed_corpus_has_at_least_four_times_top_k_chunks(self, set_data_dir):
        from config import get_settings

        assert count_chunks(build_corpus.CORPUS, set_data_dir) >= 4 * get_settings().top_k

    def test_distractors_contain_no_answer_element(self):
        """Un distracteur qui contiendrait une réponse fausserait la mesure."""
        texts = [run_eval.normalize(f.read_text(encoding="utf-8"))
                 for f in (build_corpus.CORPUS / "distracteurs").glob("*.md")]
        assert texts
        for question in QUESTIONS:
            for element in question.get("key_elements", []):
                for variant in element if isinstance(element, list) else [element]:
                    assert not any(run_eval.normalize(variant) in text for text in texts), (question["id"], variant)

    def test_every_expected_source_exists_in_the_corpus(self):
        for question in QUESTIONS:
            for source in question.get("expected_sources", []):
                assert (build_corpus.CORPUS / source).exists(), (question["id"], source)


# --- Éléments clés -------------------------------------------------------------

class TestKeyElements:
    @staticmethod
    def found(question_id: int, answer: str) -> tuple[int, int]:
        graded = run_eval.grade(BY_ID[question_id], answer, [])
        return graded["key_elements_found"], graded["key_elements_total"]

    def test_variants_are_alternatives(self):
        assert self.found(2, "Le contrat expire le 31 décembre 2025.") == (1, 1)
        assert self.found(2, "Échéance : 31/12/2025.") == (1, 1)
        assert self.found(2, "Il expire en 2026.") == (0, 1)

    def test_case_and_accents_are_ignored(self):
        assert self.found(2, "LE 31 DECEMBRE 2025") == (1, 1)
        assert self.found(13, "Le sujet est « Dîner dimanche ».") == (1, 1)
        assert self.found(13, "DINER DIMANCHE") == (1, 1)

    def test_non_breaking_spaces_and_curly_apostrophes_are_normalized(self):
        assert self.found(5, "À 15 h 30.") == (1, 1)
        assert run_eval.normalize("L’été  dernier") == "l'ete dernier"

    def test_every_listed_element_is_required(self):
        assert self.found(14, "C'est la facture du garage.") == (1, 2)
        assert self.found(14, "La facture du garage, 342 euros, est la plus élevée.") == (2, 2)
        assert self.found(8, "Il faut des pommes, de la farine et du beurre.") == (3, 4)

    def test_q14_requires_garage_and_342(self):
        assert BY_ID[14]["key_elements"] == ["garage", "342"]


# --- Abstention ----------------------------------------------------------------

class TestAbstention:
    @pytest.mark.parametrize("answer", [
        "Je ne trouve pas cette information dans les documents.",
        "Cette information n’est pas mentionnée dans vos documents.",
        "Je NE SAIS PAS.",
        "Les documents fournis ne contiennent pas de réponse à cette question.",
        "Je ne suis pas en mesure de répondre.",
    ])
    def test_admissions_of_ignorance_are_detected(self, answer):
        assert run_eval.is_abstention(answer)

    @pytest.mark.parametrize("answer", [
        "Le code wifi des voisins est AZERTY1234.",
        "",
        "La franchise est de 250 euros.",
    ])
    def test_confident_answers_are_not_abstentions(self, answer):
        assert not run_eval.is_abstention(answer)

    def test_only_abstain_questions_get_an_abstained_field(self):
        assert BY_ID[15]["abstain"] and BY_ID[15]["expected_sources"] == []
        assert run_eval.grade(BY_ID[15], "Je ne sais pas.", [])["abstained"] is True
        assert run_eval.grade(BY_ID[15], "Le code est AZERTY.", [])["abstained"] is False
        assert "abstained" not in run_eval.grade(BY_ID[1], "250 euros", ["assurance/contrat_habitation.pdf"])

    def test_abstention_summary(self):
        rows = [{"id": i, "category": "x", "latency_s": 1.0, "source_hit": None, "key_elements_total": 0,
                 "cited_files": [], "citations_valid": None, "abstained": ok} for i, ok in ((15, True), (16, False))]
        assert run_eval.summarize(rows)["all"]["good_abstentions"] == "1/2"


# --- Recherche : rang et recall@k ----------------------------------------------

class TestRetrieval:
    def test_ranks_and_recall_with_all_expected_sources_found(self):
        graded = run_eval.grade_retrieval(BY_ID[14], ["menage.md", "garage/facture.pdf", "x.md", "edf/facture.pdf"])
        assert graded["source_ranks"] == [4, 2]
        assert graded["source_hit"] is True
        assert graded["recall_at_k"] == 1.0

    def test_partial_recall(self):
        graded = run_eval.grade_retrieval(BY_ID[14], ["edf/facture.pdf", "menage.md"])
        assert graded["source_ranks"] == [1, None]
        assert graded["source_hit"] is False
        assert graded["recall_at_k"] == 0.5

    def test_homonyms_are_told_apart_by_relative_path(self):
        graded = run_eval.grade_retrieval(BY_ID[11], ["edf/facture.pdf"])
        assert graded["source_ranks"] == [None]
        assert run_eval.grade_retrieval(BY_ID[11], ["edf/facture.pdf", "garage/facture.pdf"])["source_ranks"] == [2]

    def test_legacy_bare_names_match_on_base_name(self):
        assert run_eval.grade_retrieval(BY_ID[10], ["facture.pdf"])["source_ranks"] == [1]

    def test_no_expected_source_gives_no_recall(self):
        graded = run_eval.grade_retrieval(BY_ID[15], ["menage.md"])
        assert graded["recall_at_k"] is None and graded["source_hit"] is None

    def test_retrieve_returns_sources_in_order_of_the_store(self):
        class FakeStore:
            def similarity_search_with_score(self, question, k):
                docs = [(Document(page_content="a", metadata={"source": f"d{i}.md"}), 0.1 * i) for i in range(10)]
                return docs[:k]

        class FakeEngine:
            vectorstore = FakeStore()

        assert run_eval.retrieve(FakeEngine(), "?", 3) == ["d0.md", "d1.md", "d2.md"]

    def test_summary_averages_recall_and_separates_known_gaps(self):
        def row(question_id, sources, known_gap=None):
            return {"id": question_id, "category": "x", "latency_s": 0.1, "known_gap": known_gap,
                    **run_eval.grade_retrieval(BY_ID[question_id], sources)}

        rows = [row(1, ["assurance/contrat_habitation.pdf"]),
                row(14, ["edf/facture.pdf"]),
                row(4, ["menage.md"], known_gap="F16"),
                row(15, ["menage.md"])]  # sans source attendue : exclue du calcul
        summary = run_eval.summarize_retrieval(rows)
        assert summary["all"]["questions"] == 3
        assert summary["all"]["recall_at_k"] == 0.5  # (1 + 0,5 + 0) / 3
        assert summary["all"]["source_found"] == "1/3"
        assert summary["without_known_gaps"]["recall_at_k"] == 0.75


# --- F3 : la réponse cite-t-elle une source attendue ---------------------------

class TestCitesExpectedSource:
    def test_citation_of_an_expected_source(self):
        graded = run_eval.grade(BY_ID[1], "La franchise est de 250 euros [assurance/contrat_habitation.pdf].",
                                ["assurance/contrat_habitation.pdf"])
        assert graded["cites_expected_source"] is True

    def test_citation_of_another_file_does_not_count(self):
        graded = run_eval.grade(BY_ID[1], "250 euros [menage.md]", ["menage.md"])
        assert graded["cites_expected_source"] is False

    def test_no_citation_does_not_count(self):
        assert run_eval.grade(BY_ID[1], "250 euros", [])["cites_expected_source"] is False

    def test_one_expected_source_is_enough(self):
        graded = run_eval.grade(BY_ID[14], "Voir [garage/facture.pdf].", ["garage/facture.pdf"])
        assert graded["cites_expected_source"] is True

    def test_homonym_cited_with_wrong_folder_does_not_count(self):
        assert run_eval.grade(BY_ID[11], "[edf/facture.pdf]", [])["cites_expected_source"] is False

    def test_not_applicable_without_expected_source(self):
        assert run_eval.grade(BY_ID[15], "Je ne sais pas.", [])["cites_expected_source"] is None

    def test_summary_rate(self):
        rows = [{"id": i, "category": "x", "latency_s": 1.0, "source_hit": True, "key_elements_total": 0,
                 "cited_files": [], "citations_valid": None, "cites_expected_source": value}
                for i, value in enumerate([True, False, None, True])]
        assert run_eval.summarize(rows)["all"]["cites_expected_source"] == "2/3"
