# Changelog

Toutes les modifications notables de ce projet sont documentées dans ce fichier.

Format basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/),
versionnage selon [Semantic Versioning](https://semver.org/lang/fr/).

---

## [Unreleased]

### Ajouté
- `.gitignore` — exclusion des secrets, caches Python et index vectoriel
- `.dockerignore` — réduction du contexte de build Docker
- `.env.example` — gabarit documenté de toutes les variables d'environnement
- `CHANGELOG.md` — journal des modifications (ce fichier)

### Modifié
- `docker-compose.yml` — binding du port 8000 restreint à `127.0.0.1` (accès local uniquement)
- `docker-compose.yml` — transmet `LLM_MODEL`, `TOP_K` et `TEMPERATURE` au conteneur ; ils étaient jusqu'ici ignorés (F9)
- `app/entrypoint.sh` — `OLLAMA_HOST` est testé en premier, sans doublon (F10)
- `app/rag_engine.py` — un index illisible n'est plus supprimé au chargement : l'erreur est journalisée (S6)
- `app/config.py`, `app/main.py` — `model_config` et `TemplateResponse(request, ...)` (plus d'avertissements de dépréciation)

- `app/entrypoint.sh`, `Dockerfile` — adresse d'écoute d'uvicorn pilotée par `APP_HOST` (défaut `0.0.0.0` dans le conteneur) au lieu d'être figée dans le `CMD`
- `README.md`, `MANAGE.md`, `docker-compose.yml`, `.env.example` — retrait du conseil `network_mode: host`, qui exposait l'application au réseau local (SEC13) ; aucune authentification n'existe

- `app/requirements.txt` — correctifs de sécurité (lot 3) : pypdf 5.1.0 → 6.20.1, Pillow 11.1.0 → 12.3.0, jinja2 3.1.5 → 3.1.6, python-docx 1.1.2 → 1.2.0, psutil 6.1.1 → 7.2.2. Aucun avis OSV connu sur ces versions (le 20/10/2026) ; pypdf 5.1.0 et Pillow 11.1.0 en cumulaient respectivement 97 et 34. Format d'index inchangé.

- `app/requirements.txt`, `Dockerfile` — lot 4 : fastapi 0.115.6 → 0.143.1, starlette 0.41.3 → 1.8.0 (désormais épinglé explicitement), uvicorn 0.34.0 → 0.54.0, pydantic 2.10.4 → 2.14.1, pydantic-settings 2.7.1 → 2.16.0, image `python:3.11-slim` → `python:3.11.17-slim-trixie`. Corrige les 7 avis de sécurité de starlette 0.41.3 (SEC8). Aucun avis OSV connu sur les nouvelles versions (20/10/2026). Format d'index inchangé.

### Ajouté (lot 2b)
- `docker-compose.linux.yml` — override Linux : `network_mode: host`, Ollama et application sur `127.0.0.1`

### Supprimé
- `ollama-override.conf` — il faisait écouter Ollama sur `0.0.0.0` (SEC4)
- Dépendances inutilisées `python-multipart`, `python-magic`, `aiofiles` et paquets système `libmagic1`, `poppler-utils`
