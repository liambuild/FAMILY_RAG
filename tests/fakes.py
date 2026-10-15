"""Doubles de test pour le moteur : aucun appel à Ollama ni au réseau."""

from langchain_core.language_models.chat_models import SimpleChatModel
from pydantic import Field

# Marqueur du prompt de re-ranking dans rag_engine._rerank_chunks
RERANK_MARKER = "Réponds UNIQUEMENT avec un nombre entre 0 et 10"


class FakeChat(SimpleChatModel):
    """Faux chat model qui enregistre les prompts reçus.

    - un prompt de re-ranking reçoit la note du premier motif de `rerank_scores`
      présent dans le prompt (5 par défaut), ou lève une erreur si `fail_rerank` ;
    - tout autre prompt reçoit `answer`.
    """

    answer: str = "Réponse de test."
    rerank_scores: dict = Field(default_factory=dict)
    fail_rerank: bool = False
    prompts: list = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "fake-test"

    def _call(self, messages, stop=None, run_manager=None, **kwargs) -> str:
        text = "\n".join(str(m.content) for m in messages)
        self.prompts.append(text)
        if RERANK_MARKER in text:
            if self.fail_rerank:
                raise RuntimeError("panne simulée du re-ranking")
            for needle, score in self.rerank_scores.items():
                if needle in text:
                    return str(score)
            return "5"
        return self.answer

    @property
    def rerank_prompts(self) -> list:
        return [p for p in self.prompts if RERANK_MARKER in p]

    @property
    def answer_prompts(self) -> list:
        return [p for p in self.prompts if RERANK_MARKER not in p]
