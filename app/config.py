"""Configuration centralisée de l'application."""

from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    """Paramètres de l'application, chargés depuis les variables d'environnement."""
    
    # Ollama
    ollama_host: str = "host.docker.internal:11434"
    embedding_model: str = "nomic-embed-text"
    llm_model: str = ""  # Auto-détecté au démarrage si vide
    
    # RAG
    chunk_size: int = 1200  # Augmenté pour capturer plus de contexte (expériences complètes)
    chunk_overlap: int = 300  # Réduit pour éviter trop de redondance
    top_k: int = 12  # Augmenté pour récupérer plus de chunks pertinents
    
    # LLM
    temperature: float = 0.7
    
    # Chemins
    data_dir: str = "/data"
    index_dir: str = "/app/index"
    
    @property
    def ollama_base_url(self) -> str:
        return f"http://{self.ollama_host}"

    model_config = SettingsConfigDict(env_file=".env")


@lru_cache
def get_settings() -> Settings:
    return Settings()
