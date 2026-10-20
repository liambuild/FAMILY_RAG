"""Tests du déploiement : variables du compose (F9), détection d'Ollama (F10), réseau local par défaut (D7)."""

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


def run_entrypoint(tmp_path: Path, ollama_host: str | None, reachable: set[str],
                   app_host: str | None = None, show: str = "OLLAMA_HOST") -> tuple[list[str], str]:
    """Lance entrypoint.sh avec un faux curl : renvoie les hôtes testés dans l'ordre, et la variable `show` finale."""
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
    if app_host is not None:
        env["APP_HOST"] = app_host
    done = subprocess.run(["bash", str(ENTRYPOINT), "sh", "-c", f'echo "FINAL=${show}"'],
                          env=env, capture_output=True, text=True, timeout=30)
    assert done.returncode == 0, done.stderr
    tested = log.read_text().split() if log.exists() else []
    return tested, done.stdout.strip().splitlines()[-1].removeprefix("FINAL=")


def merged_with_linux_override() -> dict:
    """Fusion simplifiée de docker-compose.yml et docker-compose.linux.yml (environment fusionné par variable)."""
    class Loader(yaml.SafeLoader):
        pass

    Loader.add_constructor("!reset", lambda loader, node: None)
    base = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))["services"]["family-rag"]
    override = yaml.load((ROOT / "docker-compose.linux.yml").read_text(encoding="utf-8"), Loader)["services"]["family-rag"]
    environment = dict(e.split("=", 1) for e in base["environment"])
    environment.update(e.split("=", 1) for e in override["environment"])
    return {**base, **override, "environment": environment}


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


class TestLocalNetwork:
    """D7 / SEC13 / SEC4 : local par défaut, Linux en mode host sur 127.0.0.1."""

    def test_main_compose_does_not_use_host_network_and_binds_loopback(self):
        compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))["services"]["family-rag"]
        assert "network_mode" not in compose
        assert compose["ports"] == ["127.0.0.1:8000:8000"]
        assert "network_mode: host" not in (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    def test_main_compose_does_not_let_env_change_the_listen_address(self):
        """APP_HOST=127.0.0.1 dans .env casserait le mappage en mode bridge : il n'est pas transmis."""
        assert "APP_HOST" not in compose_environment()

    def test_linux_override_uses_host_network_on_loopback_only(self):
        merged = merged_with_linux_override()
        assert merged["network_mode"] == "host"
        assert merged["environment"]["OLLAMA_HOST"] == "127.0.0.1:11434"
        assert merged["environment"]["APP_HOST"] == "127.0.0.1"
        assert merged["ports"] is None  # !reset : plus de publication de port

    def test_ollama_override_that_exposed_ollama_on_all_interfaces_is_gone(self):
        assert not (ROOT / "ollama-override.conf").exists()

    def test_dockerfile_does_not_hardcode_the_listen_address(self):
        cmd = [l for l in (ROOT / "Dockerfile").read_text(encoding="utf-8").splitlines() if l.startswith("CMD")]
        assert len(cmd) == 1 and "--host" not in cmd[0]

    def test_listen_address_defaults_to_all_interfaces_inside_the_container(self, tmp_path):
        _, host = run_entrypoint(tmp_path, None, set(), show="UVICORN_HOST")
        assert host == "0.0.0.0"

    def test_app_host_is_passed_to_uvicorn(self, tmp_path):
        _, host = run_entrypoint(tmp_path, None, set(), app_host="127.0.0.1", show="UVICORN_HOST")
        assert host == "127.0.0.1"
