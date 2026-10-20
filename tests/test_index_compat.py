"""Compatibilité d'index (lot 4b, D2/D12) : index_meta.json, index incompatible, jamais de suppression.

Vrai RAGEngine, faux embeddings et faux chat model (voir conftest.py), sans réseau.
"""

import json
import shutil
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from conftest import EMBEDDING_SIZE, write_files

CORPUS = {
    "contrat.txt": "Contrat de location : le loyer mensuel est de 800 euros.",
    "recette.txt": "Recette de la tarte : farine, beurre, pommes, cuisson au four.",
}
QUESTION = "Quel est le loyer ?"


@pytest.fixture(autouse=True)
def never_delete_an_index(monkeypatch):
    """Dans tous ces tests, toute tentative de suppression d'un dossier échoue bruyamment."""
    def refuse(*args, **kwargs):
        raise AssertionError("suppression d'un dossier interdite : un index ne doit jamais être supprimé")

    monkeypatch.setattr(shutil, "rmtree", refuse)


@pytest.fixture
def indexed(engine, data_dir):
    write_files(data_dir, CORPUS)
    assert engine.index_documents()["success"]
    return engine


def meta_path(engine):
    return engine.index_path / "index_meta.json"


def read_meta(engine) -> dict:
    return json.loads(meta_path(engine).read_text(encoding="utf-8"))


def write_meta(engine, **changes) -> None:
    meta = {**read_meta(engine), **changes}
    meta_path(engine).write_text(json.dumps(meta), encoding="utf-8")


def snapshot(engine) -> dict:
    """Contenu de tous les fichiers de l'index, pour prouver qu'il n'a pas bougé."""
    return {f.name: f.read_bytes() for f in engine.index_path.iterdir()}


class TestMetaFile:
    def test_saving_writes_index_meta(self, indexed):
        from importlib.metadata import version

        meta = read_meta(indexed)
        assert meta["format_version"] == 1
        assert meta["embedding_model"] == "fake-embed"
        assert meta["embedding_dimension"] == EMBEDDING_SIZE
        assert meta["langchain_core"] == version("langchain-core")
        assert meta["faiss_cpu"] == version("faiss-cpu")
        assert meta["created_at"]
        assert not (indexed.index_path / "index_meta.json.tmp").exists()

    def test_compatible_index_is_loaded_after_restart(self, indexed, make_engine):
        restarted = make_engine()
        assert restarted.index_status == "ok"
        assert restarted.vectorstore is not None
        assert restarted.get_stats().status == "ok"

    def test_no_index_means_absent_not_incompatible(self, engine):
        assert engine.index_status == "absent"
        stats = engine.get_stats()
        assert (stats.status, stats.message) == ("absent", None)

    def test_equivalent_model_names_are_compatible(self, indexed, make_engine):
        write_meta(indexed, embedding_model="fake-embed:latest")
        assert make_engine().index_status == "ok"


class TestIncompatibleIndex:
    @pytest.fixture
    def make_incompatible(self, indexed, make_engine):
        """Renvoie un moteur redémarré sur un index modifié par `change(engine)`."""
        def factory(change):
            change(indexed)
            before = snapshot(indexed)
            restarted = make_engine()
            assert snapshot(restarted) == before, "l'index a été modifié"
            return restarted
        return factory

    @pytest.mark.parametrize("change", [
        pytest.param(lambda e: meta_path(e).unlink(), id="sans-index_meta (v1-legacy)"),
        pytest.param(lambda e: meta_path(e).write_text("pas du json", encoding="utf-8"), id="meta-illisible"),
        pytest.param(lambda e: meta_path(e).write_text("[1, 2]", encoding="utf-8"), id="meta-pas-un-objet"),
        pytest.param(lambda e: write_meta(e, format_version=99), id="autre-format"),
        pytest.param(lambda e: write_meta(e, embedding_model="autre-modele"), id="autre-modele"),
        pytest.param(lambda e: write_meta(e, langchain_core="0.0.1"), id="autre-langchain-core"),
        pytest.param(lambda e: write_meta(e, faiss_cpu="0.0.1"), id="autre-faiss"),
        pytest.param(lambda e: write_meta(e, embedding_dimension=999), id="autre-dimension"),
        pytest.param(lambda e: (e.index_path / "index.pkl").write_bytes(b"corrompu"), id="pickle-illisible"),
    ])
    def test_index_is_not_loaded_and_not_touched(self, make_incompatible, change):
        restarted = make_incompatible(change)
        assert restarted.vectorstore is None
        assert restarted.index_status == "incompatible"
        assert restarted.index_problem
        assert (restarted.index_path / "index.faiss").is_file()

    def test_stats_and_details_expose_the_state(self, make_incompatible):
        restarted = make_incompatible(lambda e: meta_path(e).unlink())
        stats = restarted.get_stats()
        assert stats.index_exists is False
        assert stats.status == "incompatible"
        assert "index_meta.json" in stats.message and "Indexer" in stats.message
        details = restarted.get_index_details()
        assert (details["exists"], details["status"]) == (False, "incompatible")
        assert details["message"] == stats.message

    def test_query_asks_to_reindex_without_calling_the_llm(self, make_incompatible, make_engine):
        restarted = make_incompatible(lambda e: write_meta(e, embedding_model="autre-modele"))
        result = restarted.query(QUESTION)
        assert "Indexer" in result.answer and "autre-modele" in result.answer
        assert "pas été supprimé" in result.answer
        assert (result.sources, result.chunks_found) == ([], 0)
        assert restarted.llm.prompts == []

    def test_reindexing_makes_it_usable_again(self, make_incompatible, data_dir):
        restarted = make_incompatible(lambda e: meta_path(e).unlink())
        assert restarted.index_documents()["success"]
        assert restarted.index_status == "ok"
        assert meta_path(restarted).is_file()
        result = restarted.query(QUESTION)  # les faux embeddings classent au hasard : on vérifie seulement qu'elle aboutit
        assert result.chunks_found == 2 and result.answer == "Réponse de test."

    def test_failed_reindexing_keeps_the_old_index(self, make_incompatible):
        restarted = make_incompatible(lambda e: meta_path(e).unlink())

        class Broken:
            def embed_documents(self, texts):
                raise RuntimeError("Ollama indisponible")

        restarted.embeddings = Broken()
        before = snapshot(restarted)
        assert restarted.index_documents()["success"] is False
        assert snapshot(restarted) == before
        assert restarted.index_status == "incompatible"


class TestEmbeddingModelChange:
    def test_changing_model_keeps_files_and_marks_incompatible(self, indexed):
        before = snapshot(indexed)
        assert indexed.update_embedding_model("autre-modele") is True
        assert indexed.index_status == "incompatible"
        assert "autre-modele" in indexed.get_stats().message
        assert snapshot(indexed) == before

    def test_going_back_to_the_original_model_restores_the_index(self, indexed):
        indexed.update_embedding_model("autre-modele")
        assert indexed.update_embedding_model("fake-embed") is False
        assert indexed.index_status == "ok"
        assert indexed.vectorstore is not None

    def test_changing_model_without_index_still_asks_to_index(self, engine):
        assert engine.update_embedding_model("autre-modele") is True
        assert engine.index_status == "absent"


class TestApi:
    @pytest.fixture
    def client(self, make_engine):
        import main
        with patch("main.RAGEngine", make_engine), TestClient(main.app) as c:
            yield c

    def test_stats_show_incompatible_index(self, indexed_by_api, client):
        stats = client.get("/api/stats").json()["index"]
        assert stats["status"] == "incompatible"
        assert stats["exists"] is False
        assert "Indexer" in stats["message"]

    def test_query_returns_the_message_as_an_answer(self, indexed_by_api, client):
        body = client.post("/api/query", json={"question": QUESTION}).json()
        assert "Indexer" in body["answer"] and body["sources"] == []

    def test_changing_embedding_model_via_settings_keeps_the_index(self, client, data_dir):
        write_files(data_dir, CORPUS)
        assert client.post("/api/index", json={}).status_code == 200
        r = client.put("/api/settings", json={"embedding_model": "autre-modele"})
        assert r.json()["needs_reindex"] is True
        stats = client.get("/api/stats").json()["index"]
        assert stats["status"] == "incompatible"
        assert client.get("/api/index/details").json()["status"] == "incompatible"


@pytest.fixture
def indexed_by_api(data_dir, index_dir, make_engine):
    """Index créé puis rendu 'v1-legacy' (sans index_meta.json) AVANT le démarrage du client."""
    engine = make_engine()
    write_files(data_dir, CORPUS)
    assert engine.index_documents()["success"]
    meta_path(engine).unlink()
