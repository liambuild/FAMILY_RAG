"""Contrat API ↔ moteur : parcours de bout en bout avec un vrai RAGEngine.

Contrairement à test_api.py (MagicMock), le moteur est réel (faux embeddings et faux
chat model, voir conftest.py) : une dérive de signature ou de format entre
`main.py` et `rag_engine.py` fait échouer ces tests.
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from conftest import write_files

CORPUS = {
    "contrat.txt": "Contrat de location : le loyer mensuel est de 800 euros.",
    "recette.txt": "Recette de la tarte : farine, beurre, pommes, cuisson au four.",
}
QUESTION = "Quel est le loyer ?"


@pytest.fixture
def make_client(make_engine):
    """Fabrique de clients : chaque `with` redémarre l'application (lifespan) avec un nouveau moteur."""
    def factory():
        import main
        with patch("main.RAGEngine", make_engine):
            return TestClient(main.app)
    return factory


@pytest.fixture
def client(make_client):
    with make_client() as c:
        yield c


@pytest.fixture
def indexed_client(client, data_dir):
    write_files(data_dir, CORPUS)
    assert client.post("/api/index", json={}).status_code == 200
    return client


class TestIndexingFlow:
    def test_index_without_documents_is_a_400(self, client):
        r = client.post("/api/index", json={})
        assert r.status_code == 400
        assert r.json()["detail"] == "Aucun document trouvé dans /data"

    def test_files_then_index_then_details(self, client, data_dir):
        write_files(data_dir, CORPUS)
        assert [f["path"] for f in client.get("/api/files").json()["files"]] == ["contrat.txt", "recette.txt"]

        r = client.post("/api/index", json={})
        assert r.status_code == 200
        body = r.json()
        assert (body["success"], body["documents"], body["chunks"]) == (True, 2, 2)
        assert sorted(body["indexed_files"]) == ["contrat.txt", "recette.txt"]

        details = client.get("/api/index/details").json()
        assert details["exists"] is True
        assert details["total_vectors"] == 2
        assert details["indexed_files"] == ["contrat.txt", "recette.txt"]

    def test_selective_index_is_forwarded_to_the_engine(self, client, data_dir):
        write_files(data_dir, CORPUS)
        r = client.post("/api/index", json={"selected_files": ["recette.txt"]})
        assert r.json()["indexed_files"] == ["recette.txt"]

    def test_stats_reflect_the_index_and_settings(self, indexed_client):
        stats = indexed_client.get("/api/stats").json()
        assert stats["index"] == {"exists": True, "total_documents": 2, "total_chunks": 2, "status": "ok", "message": None}
        assert stats["settings"]["llm_model"] == "fake-llm"
        assert stats["settings"]["embedding_model"] == "fake-embed"


class TestQueryFlow:
    def test_query_returns_answer_sources_and_metrics(self, indexed_client):
        r = indexed_client.post("/api/query", json={"question": QUESTION})
        assert r.status_code == 200
        body = r.json()
        assert body["answer"] == "Réponse de test."
        assert sorted(s["source"] for s in body["sources"]) == ["contrat.txt", "recette.txt"]
        assert len(body["chunks_preview"]) == 2
        assert {"query_time_ms", "chunks_found", "model"} <= set(body["metrics"])
        assert body["metrics"]["model"] == "fake-llm"
        assert body["metrics"]["chunks_found"] == 2

    def test_query_without_index_explains_what_to_do(self, client):
        body = client.post("/api/query", json={"question": QUESTION}).json()
        assert body["answer"].startswith("Aucun document n'a été indexé")
        assert body["sources"] == []

    def test_selected_sources_filter_the_results(self, indexed_client):
        body = indexed_client.post(
            "/api/query", json={"question": QUESTION, "selected_sources": ["recette.txt"]}
        ).json()
        assert [s["source"] for s in body["sources"]] == ["recette.txt"]

    def test_unknown_selected_source_gives_the_no_match_message(self, indexed_client):
        body = indexed_client.post(
            "/api/query", json={"question": QUESTION, "selected_sources": ["absent.txt"]}
        ).json()
        assert body["answer"].startswith("Aucun document trouvé correspondant aux critères")

    def test_top_k_from_the_request_is_applied(self, indexed_client):
        body = indexed_client.post("/api/query", json={"question": QUESTION, "top_k": 1}).json()
        assert body["metrics"]["chunks_found"] == 1


class TestSettingsFlow:
    def test_settings_are_applied_to_the_engine(self, indexed_client):
        r = indexed_client.put("/api/settings", json={"temperature": 0.2, "top_k": 1, "llm_model": "autre-llm"})
        assert r.json() == {
            "status": "ok", "llm_model": "autre-llm", "embedding_model": "fake-embed",
            "temperature": 0.2, "top_k": 1, "needs_reindex": False,
        }
        body = indexed_client.post("/api/query", json={"question": QUESTION}).json()
        assert body["metrics"]["chunks_found"] == 1
        assert body["metrics"]["model"] == "autre-llm"

    def test_changing_the_embedding_model_asks_for_reindexing(self, indexed_client):
        r = indexed_client.put("/api/settings", json={"embedding_model": "autre-modele"})
        assert r.json()["needs_reindex"] is True
        assert r.json()["embedding_model"] == "autre-modele"
        assert indexed_client.get("/api/index/details").json()["exists"] is False

    def test_same_embedding_model_does_not_ask_for_reindexing(self, indexed_client):
        r = indexed_client.put("/api/settings", json={"embedding_model": "fake-embed"})
        assert r.json()["needs_reindex"] is False


class TestRestart:
    def test_index_survives_an_application_restart(self, make_client, data_dir):
        write_files(data_dir, CORPUS)
        with make_client() as first:
            assert first.post("/api/index", json={}).status_code == 200
        with make_client() as second:
            assert second.get("/api/index/details").json()["total_vectors"] == 2
            body = second.post("/api/query", json={"question": QUESTION}).json()
            assert body["answer"] == "Réponse de test."
