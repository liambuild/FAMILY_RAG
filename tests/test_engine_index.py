"""Tests de caractérisation du moteur : indexation, sauvegarde/chargement, changement de modèle.

Vrai `RAGEngine`, faux embeddings et faux chat model (voir conftest.py), sans réseau.
Les `xfail(strict=True)` décrivent le comportement voulu ; ils sont rattachés au lot
de AUDIT.md §6 qui corrige le bug et doivent y être retirés.
"""

import pytest

from conftest import write_files

CORPUS = {
    "contrat.txt": "Contrat de location : le loyer mensuel est de 800 euros.",
    "recette.txt": "Recette de la tarte : farine, beurre, pommes, cuisson au four.",
}


def indexed_sources(engine) -> list:
    return engine.get_index_details()["indexed_files"]


@pytest.fixture
def indexed(engine, data_dir):
    """Moteur avec le corpus CORPUS indexé."""
    write_files(data_dir, CORPUS)
    result = engine.index_documents()
    assert result["success"]
    return engine


# --- index_documents ----------------------------------------------------------

class TestIndexDocuments:
    def test_all_documents_are_indexed(self, engine, data_dir):
        write_files(data_dir, CORPUS)
        result = engine.index_documents()
        assert result["success"] is True
        assert result["documents"] == 2
        assert result["chunks"] == 2
        assert sorted(result["indexed_files"]) == ["contrat.txt", "recette.txt"]
        assert indexed_sources(engine) == ["contrat.txt", "recette.txt"]

    def test_empty_data_dir_is_an_error(self, engine):
        result = engine.index_documents()
        assert result == {"success": False, "error": "Aucun document trouvé dans /data", "documents": 0, "chunks": 0}
        assert engine.vectorstore is None

    def test_selected_files_only(self, engine, data_dir):
        write_files(data_dir, CORPUS)
        result = engine.index_documents(selected_files=["contrat.txt"])
        assert result["documents"] == 1
        assert indexed_sources(engine) == ["contrat.txt"]

    def test_oversized_chunks_are_recut(self, engine, data_dir):
        write_files(data_dir, {"long.txt": "mot " * 1000})
        result = engine.index_documents()
        assert result["chunks"] > 1
        assert all(len(d.page_content) <= 1500 for d in engine.vectorstore.docstore._dict.values())

    def test_embedding_failure_is_reported_as_error(self, engine, data_dir):
        class Broken:
            def embed_documents(self, texts):
                raise RuntimeError("the input length exceeds the context length")

        write_files(data_dir, CORPUS)
        engine.embeddings = Broken()
        result = engine.index_documents()
        assert result["success"] is False
        assert "trop longs" in result["error"]

    def test_indexing_replaces_the_whole_index(self, indexed, data_dir):
        """Caractérisation de F1 : indexer b.txt efface ce qui était indexé (lot 9)."""
        write_files(data_dir, {"nouveau.txt": "Un nouveau document sur le jardin."})
        indexed.index_documents(selected_files=["nouveau.txt"])
        assert indexed_sources(indexed) == ["nouveau.txt"]

    @pytest.mark.xfail(reason="F1/D1 : l'indexation sélective doit ajouter, pas remplacer (lot 9)")
    def test_selective_indexing_adds_to_the_existing_index(self, indexed, data_dir):
        write_files(data_dir, {"nouveau.txt": "Un nouveau document sur le jardin."})
        indexed.index_documents(selected_files=["nouveau.txt"])
        assert indexed_sources(indexed) == ["contrat.txt", "nouveau.txt", "recette.txt"]


# --- Sauvegarde et chargement -------------------------------------------------

class TestSaveLoad:
    def test_index_files_are_written_after_indexing(self, indexed):
        assert (indexed.index_path / "index.faiss").is_file()
        assert (indexed.index_path / "index.pkl").is_file()

    def test_round_trip_through_a_restart(self, indexed, make_engine):
        before = indexed.get_index_details()
        restarted = make_engine()
        assert restarted.vectorstore is not None
        after = restarted.get_index_details()
        assert after["total_vectors"] == before["total_vectors"] == 2
        assert after["indexed_files"] == before["indexed_files"]

    def test_round_trip_keeps_search_results(self, indexed, make_engine):
        question = "Contrat de location : le loyer mensuel est de 800 euros."
        before = indexed.vectorstore.similarity_search_with_score(question, k=2)
        after = make_engine().vectorstore.similarity_search_with_score(question, k=2)
        assert [(d.page_content, round(float(s), 5)) for d, s in before] == \
               [(d.page_content, round(float(s), 5)) for d, s in after]

    def test_no_index_on_disk_means_no_vectorstore(self, engine):
        assert engine.vectorstore is None
        assert not engine.index_path.exists()

    def test_unreadable_index_is_left_in_place(self, indexed, make_engine, caplog):
        """S6/D2/D12 : un index illisible n'est jamais supprimé automatiquement, l'erreur est journalisée."""
        (indexed.index_path / "index.pkl").write_bytes(b"corrompu")
        with caplog.at_level("ERROR"):
            restarted = make_engine()
        assert restarted.vectorstore is None
        assert (restarted.index_path / "index.faiss").is_file()
        assert (restarted.index_path / "index.pkl").read_bytes() == b"corrompu"
        assert "Index illisible" in caplog.text


# --- Changement de modèle d'embedding ----------------------------------------

class TestEmbeddingModelChange:
    def test_same_model_changes_nothing(self, indexed):
        assert indexed.update_embedding_model("fake-embed") is False
        assert indexed.vectorstore is not None
        assert indexed.index_path.exists()

    def test_new_model_asks_for_reindexing_and_drops_the_index(self, indexed):
        """Caractérisation de F8 : l'index est supprimé avant toute réindexation (lot 4b)."""
        assert indexed.update_embedding_model("autre-modele") is True
        assert indexed.settings.embedding_model == "autre-modele"
        assert indexed.vectorstore is None
        assert not indexed.index_path.exists()

    @pytest.mark.xfail(reason="F8/D2 : l'index existant doit rester en place tant que la réindexation "
                              "n'a pas réussi ; il est seulement déclaré incompatible (lot 4b)")
    def test_new_model_keeps_the_existing_index_on_disk(self, indexed):
        indexed.update_embedding_model("autre-modele")
        assert indexed.index_path.exists()

    def test_new_model_is_not_persisted(self, indexed, make_engine, monkeypatch):
        """Caractérisation de F8 : après redémarrage, le modèle de la configuration revient."""
        from config import get_settings
        indexed.update_embedding_model("autre-modele")
        monkeypatch.setattr(get_settings(), "embedding_model", "fake-embed")  # ce que relirait .env
        assert make_engine().settings.embedding_model == "fake-embed"


# --- Statistiques, détails et réglages ----------------------------------------

class TestStatsAndSettings:
    def test_stats_without_index(self, engine):
        stats = engine.get_stats()
        assert (stats.total_documents, stats.total_chunks, stats.index_exists) == (0, 0, False)

    def test_stats_with_index(self, indexed):
        stats = indexed.get_stats()
        assert (stats.total_documents, stats.total_chunks, stats.index_exists) == (2, 2, True)

    def test_stats_count_files_in_data_not_indexed_files(self, indexed, data_dir):
        """Caractérisation de F19 : total_documents compte les fichiers de /data."""
        write_files(data_dir, {"pas_indexe.txt": "jamais indexé"})
        assert indexed.get_stats().total_documents == 3

    def test_index_details_without_index(self, engine):
        details = engine.get_index_details()
        assert details["exists"] is False
        assert details["indexed_files"] == []

    def test_index_details_with_index(self, indexed):
        details = indexed.get_index_details()
        assert details["exists"] is True
        assert details["total_vectors"] == 2
        assert details["embedding_model"] == "fake-embed"

    def test_update_settings_changes_values(self, engine):
        engine.update_settings(temperature=0.1, top_k=3, llm_model="autre-llm")
        assert (engine.settings.temperature, engine.settings.top_k, engine.settings.llm_model) == (0.1, 3, "autre-llm")
        assert engine.llm is not None

    def test_update_settings_none_changes_nothing(self, engine):
        before = (engine.settings.temperature, engine.settings.top_k, engine.settings.llm_model)
        engine.update_settings()
        assert (engine.settings.temperature, engine.settings.top_k, engine.settings.llm_model) == before
