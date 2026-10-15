"""Configuration pytest — chemin et répertoire de travail."""

import os
import socket
import sys
from pathlib import Path

import pytest

APP_DIR = Path(__file__).parent.parent / "app"

# Rend les modules de app/ importables sans modifier PYTHONPATH en dehors des tests
sys.path.insert(0, str(APP_DIR))

# StaticFiles et Jinja2Templates de Starlette cherchent leurs dossiers
# relativement au cwd — on pointe donc sur app/ avant tout import de main
os.chdir(APP_DIR)


# Les fakes de tests/ sont importables directement (`from fakes import FakeChat`)
sys.path.insert(0, str(Path(__file__).parent))

EMBEDDING_SIZE = 32


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Interdit toute connexion sortante : les tests doivent tourner sans réseau."""
    def refuse(self, *args, **kwargs):
        raise RuntimeError("Accès réseau interdit dans les tests")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """Dossier /data de test, branché sur le singleton Settings (restauré en fin de test)."""
    from config import get_settings

    path = tmp_path / "data"
    path.mkdir()
    monkeypatch.setattr(get_settings(), "data_dir", str(path))
    return path


@pytest.fixture
def index_dir(tmp_path, monkeypatch):
    """Dossier d'index de test, branché sur le singleton Settings."""
    from config import get_settings

    path = tmp_path / "index"
    path.mkdir()
    monkeypatch.setattr(get_settings(), "index_dir", str(path))
    return path


@pytest.fixture
def make_engine(data_dir, index_dir, monkeypatch):
    """Fabrique de vrais RAGEngine avec faux embeddings et faux chat model.

    Chaque appel crée un nouveau moteur (utile pour simuler un redémarrage) ;
    le faux chat model est partagé et accessible via `engine.llm`.
    """
    import rag_engine as rag_module
    from config import get_settings
    from fakes import FakeChat
    from langchain_core.embeddings import DeterministicFakeEmbedding

    settings = get_settings()
    # Valeurs restaurées en fin de test, même si le moteur les modifie
    monkeypatch.setattr(settings, "llm_model", "fake-llm")
    monkeypatch.setattr(settings, "embedding_model", "fake-embed")
    monkeypatch.setattr(settings, "temperature", settings.temperature)
    monkeypatch.setattr(settings, "top_k", settings.top_k)

    chat = FakeChat()
    monkeypatch.setattr(
        rag_module, "OllamaEmbeddings",
        lambda **kwargs: DeterministicFakeEmbedding(size=EMBEDDING_SIZE),
    )
    monkeypatch.setattr(rag_module, "ChatOllama", lambda **kwargs: chat)

    def factory():
        return rag_module.RAGEngine()

    return factory


@pytest.fixture
def engine(make_engine):
    """RAGEngine prêt à l'emploi, sans index."""
    return make_engine()


def write_files(base: Path, files: dict) -> None:
    """Écrit {chemin_relatif: texte} sous `base`, en créant les sous-dossiers."""
    for relative, text in files.items():
        target = base / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
