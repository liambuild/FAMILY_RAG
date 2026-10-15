"""Garde-fous de la suite : pas de réseau, pas de fuite de configuration entre tests."""

import socket

import pytest

from config import get_settings


def test_outgoing_connections_are_refused():
    with pytest.raises(RuntimeError, match="réseau interdit"):
        socket.create_connection(("127.0.0.1", 9), timeout=1)


def test_settings_changes_are_restored_between_tests(make_engine):
    engine = make_engine()
    engine.update_settings(top_k=99, llm_model="modifie")
    engine.update_embedding_model("modifie")


def test_settings_were_restored_by_the_previous_test():
    settings = get_settings()
    assert settings.top_k != 99
    assert settings.llm_model != "modifie"
    assert settings.embedding_model != "modifie"
