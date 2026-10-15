"""Tests de caractérisation de RAGEngine.query : retours anticipés, filtre, re-ranking, contexte, scores.

Vrai moteur, faux embeddings et faux chat model (voir conftest.py et fakes.py).
"""

import pytest

from conftest import write_files

CORPUS = {
    "contrat_dupont.txt": "Contrat de location signe par Dupont : loyer de 800 euros par mois.",
    "recette_tarte.txt": "Recette de la tarte aux pommes : farine, beurre, cuisson au four.",
    "jardin.txt": "Entretien du jardin : tailler les rosiers en mars.",
}
QUESTION = "Quel est le loyer ?"


@pytest.fixture
def indexed(engine, data_dir):
    write_files(data_dir, CORPUS)
    assert engine.index_documents()["success"]
    return engine


def spy_on_search(engine, monkeypatch) -> list:
    """Enregistre le `k` demandé à FAISS à chaque recherche."""
    asked = []
    original = engine.vectorstore.similarity_search_with_score

    def spy(query, k=4, **kwargs):
        asked.append(k)
        return original(query, k=k, **kwargs)

    monkeypatch.setattr(engine.vectorstore, "similarity_search_with_score", spy)
    return asked


# --- Retours anticipés --------------------------------------------------------

class TestEarlyReturns:
    def test_no_llm(self, indexed):
        indexed.llm = None
        result = indexed.query(QUESTION)
        assert result.answer.startswith("Aucun modèle LLM disponible")
        assert (result.model_used, result.sources, result.chunks_found) == ("Aucun", [], 0)

    def test_no_index(self, engine):
        result = engine.query(QUESTION)
        assert result.answer.startswith("Aucun document n'a été indexé")
        assert result.model_used == "fake-llm"
        assert result.sources == []

    def test_no_result_from_the_search(self, indexed, monkeypatch):
        monkeypatch.setattr(indexed.vectorstore, "similarity_search_with_score", lambda *a, **k: [])
        result = indexed.query(QUESTION)
        assert result.answer == "Aucun document pertinent trouvé pour cette question."
        assert result.chunks_found == 0

    def test_early_returns_do_not_call_the_model(self, engine):
        engine.query(QUESTION)
        assert engine.llm.prompts == []


# --- Requête simple -----------------------------------------------------------

class TestPlainQuery:
    def test_answer_comes_from_the_model(self, indexed):
        result = indexed.query(QUESTION, enable_reranking=False)
        assert result.answer == "Réponse de test."
        assert result.model_used == "fake-llm"
        assert result.chunks_found == 3
        assert result.query_time_ms >= 0

    def test_sources_have_source_score_and_preview(self, indexed):
        result = indexed.query(QUESTION, enable_reranking=False)
        assert sorted(s["source"] for s in result.sources) == sorted(CORPUS)
        for source in result.sources:
            assert set(source) == {"source", "score", "preview"}
            assert source["preview"] == CORPUS[source["source"]]

    def test_preview_is_cut_at_200_characters(self, engine, data_dir):
        write_files(data_dir, {"long.txt": "a" * 600})
        engine.index_documents()
        preview = engine.query(QUESTION, enable_reranking=False).sources[0]["preview"]
        assert preview == "a" * 200 + "..."

    def test_top_k_limits_the_number_of_chunks(self, indexed):
        result = indexed.query(QUESTION, top_k=2, enable_reranking=False)
        assert result.chunks_found == len(result.sources) == 2

    def test_default_top_k_comes_from_settings(self, indexed):
        indexed.settings.top_k = 1
        assert indexed.query(QUESTION, enable_reranking=False).chunks_found == 1

    def test_faiss_is_asked_for_k_then_2k_with_reranking_then_4k_with_filter(self, indexed, monkeypatch):
        asked = spy_on_search(indexed, monkeypatch)
        indexed.query(QUESTION, top_k=2, enable_reranking=False)
        indexed.query(QUESTION, top_k=2, enable_reranking=True)
        indexed.query(QUESTION, top_k=2, filter_metadata={"source": ["jardin.txt"]})
        assert asked == [2, 4, 8]

    def test_without_reranking_the_score_is_the_faiss_distance(self, indexed):
        """Caractérisation de F6 : plus bas = mieux, 0 pour un texte identique (lot 7)."""
        result = indexed.query(CORPUS["jardin.txt"], top_k=3, enable_reranking=False)
        scores = {s["source"]: s["score"] for s in result.sources}
        assert scores["jardin.txt"] == 0.0
        assert all(score > 0 for name, score in scores.items() if name != "jardin.txt")


# --- Contexte et prompt -------------------------------------------------------

class TestContext:
    def test_context_is_the_chunks_separated_by_dashes(self, indexed):
        indexed.query(QUESTION, enable_reranking=False)
        prompt = indexed.llm.answer_prompts[-1]
        for text in CORPUS.values():
            assert text in prompt
        assert prompt.count("\n\n---\n\n") == 2
        assert f"QUESTION : {QUESTION}" in prompt

    def test_prompt_asks_for_citations_between_brackets(self, indexed):
        indexed.query(QUESTION, enable_reranking=False)
        assert "[nom_fichier]" in indexed.llm.answer_prompts[-1]

    def test_context_does_not_contain_source_names(self, indexed):
        """Caractérisation de F3 : le modèle ne voit jamais les noms de fichiers (lot 7)."""
        indexed.query(QUESTION, enable_reranking=False)
        prompt = indexed.llm.answer_prompts[-1]
        assert "contrat_dupont.txt" not in prompt

    @pytest.mark.xfail(reason="F3 : chaque extrait doit être préfixé par [source] (lot 7)")
    def test_each_extract_is_prefixed_with_its_source(self, indexed):
        indexed.query(QUESTION, enable_reranking=False)
        prompt = indexed.llm.answer_prompts[-1]
        assert "[contrat_dupont.txt]" in prompt
        assert "[jardin.txt]" in prompt


# --- Filtre par métadonnées ---------------------------------------------------

class TestFilter:
    def test_filter_on_a_list_of_sources(self, indexed):
        result = indexed.query(QUESTION, filter_metadata={"source": ["jardin.txt", "recette_tarte.txt"]},
                               enable_reranking=False)
        assert sorted(s["source"] for s in result.sources) == ["jardin.txt", "recette_tarte.txt"]

    def test_filter_on_a_single_value(self, indexed):
        result = indexed.query(QUESTION, filter_metadata={"source": "jardin.txt"}, enable_reranking=False)
        assert [s["source"] for s in result.sources] == ["jardin.txt"]

    def test_filter_without_match_gives_a_message_and_no_model_call(self, indexed):
        result = indexed.query(QUESTION, filter_metadata={"source": ["absent.txt"]})
        assert result.answer.startswith("Aucun document trouvé correspondant aux critères")
        assert result.sources == [] and result.chunks_found == 0
        assert indexed.llm.prompts == []

    def test_filter_on_a_missing_metadata_key_matches_nothing(self, indexed):
        result = indexed.query(QUESTION, filter_metadata={"inexistante": "x"})
        assert result.answer.startswith("Aucun document trouvé correspondant aux critères")

    def test_range_filter_on_year(self, engine, data_dir):
        write_files(data_dir, {"releve_2019.txt": "relevé ancien", "releve_2023.txt": "relevé récent"})
        engine.index_documents()
        result = engine.query(QUESTION, filter_metadata={"year": {"gte": 2020}}, enable_reranking=False)
        assert [s["source"] for s in result.sources] == ["releve_2023.txt"]
        result = engine.query(QUESTION, filter_metadata={"year": {"lte": 2020}}, enable_reranking=False)
        assert [s["source"] for s in result.sources] == ["releve_2019.txt"]
        result = engine.query(QUESTION, filter_metadata={"year": {"eq": 2023}}, enable_reranking=False)
        assert [s["source"] for s in result.sources] == ["releve_2023.txt"]


def build_f5_scenario(engine, data_dir):
    """25 documents distracteurs et une cible, requête = texte d'un distracteur, top_k = 2.

    FAISS interroge 4×k = 8 chunks : la cible, bien indexée, n'est pas dans ce top 8.
    """
    files = {f"distracteur_{i:02d}.txt": f"Document distracteur numéro {i}." for i in range(25)}
    files["cible.txt"] = "Le document cible, rangé loin dans le classement."
    write_files(data_dir, files)
    assert engine.index_documents()["success"]
    question = files["distracteur_00.txt"]
    top = engine.vectorstore.similarity_search_with_score(question, k=8)
    assert "cible.txt" not in [doc.metadata["source"] for doc, _ in top], "scénario F5 invalide"
    assert any(d.metadata["source"] == "cible.txt" for d in engine.vectorstore.docstore._dict.values())
    return question


class TestFilterRecall:
    def test_selected_source_outside_the_global_top_is_not_found(self, engine, data_dir):
        """Caractérisation de F5 : filtre appliqué après une recherche globale limitée à 4×k (lot 7)."""
        question = build_f5_scenario(engine, data_dir)
        result = engine.query(question, top_k=2, filter_metadata={"source": ["cible.txt"]}, enable_reranking=False)
        assert result.answer.startswith("Aucun document trouvé correspondant aux critères")
        assert result.chunks_found == 0

    @pytest.mark.xfail(reason="F5 : le filtre doit s'appliquer dans la recherche FAISS (filter= + fetch_k=) (lot 7)")
    def test_selected_source_is_found_wherever_it_ranks(self, engine, data_dir):
        question = build_f5_scenario(engine, data_dir)
        result = engine.query(question, top_k=2, filter_metadata={"source": ["cible.txt"]}, enable_reranking=False)
        assert [s["source"] for s in result.sources] == ["cible.txt"]


# --- Re-ranking ---------------------------------------------------------------

@pytest.fixture
def ranked(engine, data_dir):
    """Six documents « marqueur_N » dont la note de re-ranking vaut N."""
    write_files(data_dir, {f"doc_{n}.txt": f"Texte du document marqueur_{n}." for n in range(1, 7)})
    engine.index_documents()
    engine.llm.rerank_scores = {f"marqueur_{n}": n for n in range(1, 7)}
    return engine


class TestReranking:
    def test_candidates_are_rescored_by_the_model_and_cut_to_top_k(self, ranked):
        result = ranked.query(QUESTION, top_k=2, enable_reranking=True)
        assert len(ranked.llm.rerank_prompts) == 4  # 2×k candidats
        assert len(result.sources) == 2
        scores = [s["score"] for s in result.sources]
        assert scores == sorted(scores, reverse=True)
        assert all(0.0 <= score <= 1.0 for score in scores)
        for source in result.sources:  # note N sur 10 pour « marqueur_N »
            n = int(source["source"][4])
            assert source["score"] == n / 10

    def test_reranking_keeps_the_best_candidates(self, ranked):
        candidates = ranked.vectorstore.similarity_search_with_score(QUESTION, k=4)
        best = sorted((int(doc.metadata["source"][4]) for doc, _ in candidates), reverse=True)[:2]
        result = ranked.query(QUESTION, top_k=2, enable_reranking=True)
        assert [int(s["source"][4]) for s in result.sources] == best

    def test_reranking_is_skipped_when_candidates_do_not_exceed_k(self, ranked):
        result = ranked.query(QUESTION, top_k=12, enable_reranking=True)
        assert ranked.llm.rerank_prompts == []
        assert result.chunks_found == 6

    def test_reranking_can_be_disabled(self, ranked):
        ranked.query(QUESTION, top_k=2, enable_reranking=False)
        assert ranked.llm.rerank_prompts == []

    def test_reranking_failure_falls_back_to_a_similarity_from_the_distance(self, ranked):
        ranked.llm.fail_rerank = True
        result = ranked.query(QUESTION, top_k=2, enable_reranking=True)
        assert len(result.sources) == 2
        assert all(0.0 < s["score"] <= 1.0 for s in result.sources)  # 1 / (1 + distance)

    def test_unparsable_rerank_answer_falls_back_to_the_faiss_score(self, ranked, monkeypatch):
        monkeypatch.setattr(type(ranked.llm), "_call", lambda self, messages, **kw: "aucune idée")
        result = ranked.query(QUESTION, top_k=2, enable_reranking=True)
        assert len(result.sources) == 2
        assert all(0.0 < s["score"] <= 1.0 for s in result.sources)

    def test_a_rerank_prompt_contains_the_question_and_the_chunk(self, ranked):
        ranked.query(QUESTION, top_k=2, enable_reranking=True)
        prompt = ranked.llm.rerank_prompts[0]
        assert f"QUESTION : {QUESTION}" in prompt
        assert "EXTRAIT 1 :" in prompt
        assert "marqueur_" in prompt
