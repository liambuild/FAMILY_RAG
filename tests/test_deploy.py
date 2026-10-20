"""Tests du déploiement : variables du compose (F9) et ordre de détection d'Ollama (F10)."""

import os
import stat
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent
ENTRYPOINT = ROOT / "app" / "entrypoint.sh"


def compose_environment() -> dict:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    entries = compose["services"]["family-rag"]["environment"]
    return dict(entry.split("=", 1) for entry in entries)


class TestCompose:
    def test_llm_settings_are_passed_to_the_container(self):
        """F9 : LLM_MODEL, TOP_K et TEMPERATURE de .env ne sont plus ignorés."""
        environment = compose_environment()
        assert environment["LLM_MODEL"] == "${LLM_MODEL:-}"
        assert environment["TOP_K"] == "${TOP_K:-12}"
        assert environment["TEMPERATURE"] == "${TEMPERATURE:-0.7}"

    def test_compose_defaults_match_the_application_defaults(self):
        from config import Settings

        defaults = Settings.model_fields
        environment = compose_environment()
        assert environment["TOP_K"] == f"${{TOP_K:-{defaults['top_k'].default}}}"
        assert environment["TEMPERATURE"] == f"${{TEMPERATURE:-{defaults['temperature'].default}}}"


def run_entrypoint(tmp_path: Path, ollama_host: str | None, reachable: set[str]) -> tuple[list[str], str]:
    """Lance entrypoint.sh avec un faux curl : renvoie les hôtes testés dans l'ordre, et OLLAMA_HOST final."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "tested.log"
    curl = bin_dir / "curl"
    curl.write_text(
        '#!/bin/bash\n'
        'url="${@: -1}"\n'
        'host="${url#http://}"; host="${host%%/*}"\n'
        'echo "$host" >> "$LOG"\n'
        'case " $REACHABLE " in *" $host "*) exit 0 ;; esac\n'
        'exit 1\n'
    )
    curl.chmod(curl.stat().st_mode | stat.S_IEXEC)
    env = {"PATH": f"{bin_dir}:{os.environ['PATH']}", "LOG": str(log), "REACHABLE": " ".join(reachable)}
    if ollama_host is not None:
        env["OLLAMA_HOST"] = ollama_host
    done = subprocess.run(["bash", str(ENTRYPOINT), "sh", "-c", 'echo "FINAL=$OLLAMA_HOST"'],
                          env=env, capture_output=True, text=True, timeout=30)
    assert done.returncode == 0, done.stderr
    tested = log.read_text().split() if log.exists() else []
    return tested, done.stdout.strip().splitlines()[-1].removeprefix("FINAL=")


class TestEntrypoint:
    def test_explicit_ollama_host_is_tested_first_and_wins(self, tmp_path):
        """F10 : une configuration explicite l'emporte sur host.docker.internal si elle répond."""
        tested, final = run_entrypoint(tmp_path, "mon-serveur:11434", {"mon-serveur:11434", "host.docker.internal:11434"})
        assert tested == ["mon-serveur:11434"]
        assert final == "mon-serveur:11434"

    def test_falls_back_to_the_other_candidates_without_duplicates(self, tmp_path):
        tested, final = run_entrypoint(tmp_path, "host.docker.internal:11434", {"localhost:11434"})
        assert tested == ["host.docker.internal:11434", "localhost:11434"]
        assert final == "localhost:11434"

    def test_keeps_the_configured_host_when_nothing_answers(self, tmp_path):
        tested, final = run_entrypoint(tmp_path, "mon-serveur:11434", set())
        assert tested[0] == "mon-serveur:11434"
        assert final == "mon-serveur:11434"

    def test_default_host_when_nothing_is_configured_and_nothing_answers(self, tmp_path):
        _, final = run_entrypoint(tmp_path, None, set())
        assert final == "host.docker.internal:11434"
