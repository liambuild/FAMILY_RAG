<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python"/>
  <img src="https://img.shields.io/badge/FastAPI-0.115-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI"/>
  <img src="https://img.shields.io/badge/Docker-24.0-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Docker"/>
  <img src="https://img.shields.io/badge/Ollama-0.13+-000000?style=for-the-badge&logo=ollama&logoColor=white" alt="Ollama"/>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/LangChain-0.3-1C3C3C?style=for-the-badge&logo=langchain&logoColor=white" alt="LangChain"/>
  <img src="https://img.shields.io/badge/FAISS-Vector_DB-0467DF?style=for-the-badge&logo=meta&logoColor=white" alt="FAISS"/>
  <img src="https://img.shields.io/badge/Ministral_3-Vision-FF6B6B?style=for-the-badge&logo=mistral&logoColor=white" alt="Ministral 3"/>
  <img src="https://img.shields.io/badge/Tesseract-OCR-5A5A5A?style=for-the-badge&logo=google&logoColor=white" alt="Tesseract"/>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Apple_Silicon-M1%2FM2%2FM3-000000?style=for-the-badge&logo=apple&logoColor=white" alt="Apple Silicon"/>
  <img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License"/>
</p>

---

<h1 align="center">📚 FamilyRAG 2.7</h1>

<h3 align="center">
  <em>Votre bibliothèque numérique privée — dernière release 2025</em>
</h3>

<p align="center">
  Posez des questions à vos documents en langage naturel.<br/>
  Sans cloud. Sans abonnement. Sans compromis sur la vie privée.
</p>

---

## 🏠 Qu'est-ce que FamilyRAG ?

**FamilyRAG** est un système RAG (Retrieval-Augmented Generation) entièrement local, conçu pour les familles qui souhaitent exploiter la puissance de l'IA générative tout en gardant le contrôle total sur leurs données.

Imaginez pouvoir interroger en langage naturel :
- 📄 Les documents administratifs de la famille
- 📖 Les recettes de grand-mère numérisées
- 🖼️ Les photos de documents et textes scannés (OCR + Vision IA)
- 📝 Les cours et devoirs des enfants
- 📧 Les archives emails importantes
- 📚 Votre bibliothèque personnelle de livres et articles

**Le tout sans qu'une seule donnée ne quitte votre domicile.**

---

## ✨ Nouveautés v2.7

### 📊 Dashboard système en temps réel

- **Monitoring live** — CPU, RAM et disque affichés directement dans l'interface
- **Statistiques de précision** — Score de confiance et probabilité des résultats pour chaque réponse
- **Endpoint dédié** — `/api/system/metrics` pour surveiller les ressources

### 🎨 3 nouveaux thèmes premium

Refonte graphique complète avec 3 thèmes plus poussés remplaçant les 6 précédents :

- **Midnight** — Bleu nuit profond, design épuré et professionnel
- **Cyber** — Noir intense avec accents cyan néon, ambiance futuriste
- **Tactical** — Vert militaire avec accents rouges, style opérationnel

### 📁 Indexation sélective

- **Choix précis des fichiers** — Sélectionnez exactement quels documents indexer
- **Barre de progression intelligente** — Suivi en temps réel de l'avancement de l'indexation
- **Contrôle granulaire** — Plus besoin d'indexer l'intégralité du dossier

### 💬 Gestion avancée des conversations

- **Onglet dédié** — Interface complète pour gérer l'historique des conversations
- **Sélection de sources par conversation** — Limitez la recherche à des documents spécifiques pour chaque discussion
- **Persistance** — Reprenez vos conversations là où vous les avez laissées

### 🔒 Sécurité & Qualité (post-audit)

- **Gardes LFI** — Toute tentative de path traversal (`../../etc/passwd`) est bloquée avec HTTP 403 sur les endpoints `/api/index` et `/api/vision`
- **Interface 100 % hors-ligne** — Tailwind CSS et Alpine.js servis localement (`/static/`) ; aucune requête CDN externe
- **Suite de tests** — 40 tests pytest couvrant les routes API, les gardes de sécurité et les scénarios d'erreur
- **Logs structurés** — Tous les `print()` remplacés par `logging` avec niveaux INFO / WARNING / ERROR

---

## 🎯 Rappel v2.6 — Précision RAG +65%

La v2.6 avait apporté une refonte majeure du pipeline de recherche :

- **Re-ranking LLM** — Chaque chunk réévalué sémantiquement, éliminant les faux positifs
- **Métadonnées enrichies** — Date, année, type de document et auteur extraits automatiquement
- **Chunking intelligent** — Préserve la structure (articles, listes, tableaux)
- **Citations obligatoires** — Chaque réponse cite ses sources `[document.pdf]`
- **Sélection des modèles** — LLM et embedding modifiables en un clic depuis l'interface
- **Debug chunks** — Visualisation des passages récupérés et leurs scores

### 📊 Gains de précision v2.5 → v2.6

| Métrique | v2.5 | v2.6+ |
|----------|------|-------|
| Chunks récupérés | 4 | 12 |
| Réponses avec citations | ~30% | ~85% |
| Faux positifs | ~40% | ~10% |
| **Précision globale** | **~45%** | **~75%** |

---

## 🗂️ Formats supportés

<p align="center">
  <img src="https://img.shields.io/badge/PDF-Documents-EC1C24?style=for-the-badge&logo=adobe-acrobat-reader&logoColor=white" alt="PDF"/>
  <img src="https://img.shields.io/badge/TXT-Texte-4A4A4A?style=for-the-badge&logo=textpattern&logoColor=white" alt="TXT"/>
  <img src="https://img.shields.io/badge/MD-Markdown-000000?style=for-the-badge&logo=markdown&logoColor=white" alt="MD"/>
  <img src="https://img.shields.io/badge/DOCX-Word-2B579A?style=for-the-badge&logo=microsoft-word&logoColor=white" alt="DOCX"/>
  <img src="https://img.shields.io/badge/EML-Email-005FF9?style=for-the-badge&logo=mail.ru&logoColor=white" alt="EML"/>
  <img src="https://img.shields.io/badge/JPG-Image-FFD700?style=for-the-badge&logo=image&logoColor=black" alt="JPG"/>
  <img src="https://img.shields.io/badge/PNG-Image-FFD700?style=for-the-badge&logo=image&logoColor=black" alt="PNG"/>
</p>

**Images** : OCR Tesseract (indexation) + Vision Ministral 3 (analyse à la demande)

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      Votre machine (Mac/Linux/Windows)          │
│                                                                 │
│  ┌─────────────────┐        ┌────────────────────────────────┐  │
│  │     Ollama      │◄──────►│     Docker Container           │  │
│  │    (natif)      │  API   │                                │  │
│  │                 │        │  ┌──────────────────────────┐  │  │
│  │ • ministral-3   │        │  │  FastAPI + FAISS         │  │  │
│  │ • nomic-embed   │        │  │  + LangChain + Tesseract │  │  │
│  │                 │        │  └──────────────────────────┘  │  │
│  └─────────────────┘        │                                │  │
│          │                  │  ┌──────────────────────────┐  │  │
│          │ GPU              │  │  WebUI (3 thèmes)        │  │  │
│          ▼                  │  │  + Dashboard metrics     │  │  │
│  ┌─────────────────┐        │  └──────────────────────────┘  │  │
│  │  Apple Silicon  │        │                                │  │
│  │   M1/M2/M3      │        │   127.0.0.1:8000 (local only)  │  │
│  └─────────────────┘        └────────────────────────────────┘  │
│                                        ▲                        │
│  ┌─────────────────┐                   │                        │
│  │  📁 Vos Docs    │───────────────────┘                        │
│  │  (RAG folder)   │  volume mount                              │
│  └─────────────────┘                                            │
└─────────────────────────────────────────────────────────────────┘
```

Par défaut, le port 8000 est lié à `127.0.0.1` — l'application n'est accessible que depuis la machine hôte. Pour l'exposer sur le réseau local, modifiez `docker-compose.yml` (voir [Guide d'administration](https://github.com/Liamdbav/FAMILY_RAG/blob/main/MANAGE.md)).

---

## Prérequis

- **Ollama 0.13.1+** (requis pour Ministral 3)
- Docker Desktop

```bash
# Vérifier la version Ollama
ollama --version
```

---

## Installation

### 1. Cloner et configurer

```bash
git clone https://github.com/Liamdbav/FAMILY_RAG.git
cd FAMILY_RAG
cp .env.example .env
```

Éditer `.env` pour définir le chemin vers vos documents :

```bash
nano .env
# Modifier HOST_DATA_PATH=/chemin/vers/vos/documents
```

### 2. Installer les modèles Ollama

```bash
# Modèle de génération + vision (recommandé)
ollama pull ministral-3:latest

# Ou autres modèles de génération
ollama pull qwen2.5:7b
ollama pull mistral:latest

# Modèle d'embedding (obligatoire)
ollama pull nomic-embed-text
```

### 3. Lancer

**Mac / Windows (Docker Desktop)** :

```bash
docker compose up -d --build
```

**Linux** : ajoutez le fichier `docker-compose.linux.yml`. L'application partage alors le réseau de l'hôte, joint Ollama sur `127.0.0.1:11434` et n'écoute elle-même que sur `127.0.0.1` (Docker Compose 2.24.4 ou plus récent requis).

```bash
docker compose -f docker-compose.yml -f docker-compose.linux.yml up -d --build
```

Ollama n'a besoin d'aucun réglage réseau : il écoute sur `127.0.0.1` par défaut.

### 4. C'est prêt !

Ouvrez **http://localhost:8000** 🎉

---

## ⚙️ Variables d'environnement

Toutes les variables sont déclarées dans `.env` (copié depuis `.env.example`).

| Variable | Défaut | Obligatoire | Description |
|----------|--------|:-----------:|-------------|
| `HOST_DATA_PATH` | — | ✅ | Chemin absolu vers le dossier de documents sur l'hôte |
| `OLLAMA_HOST` | `host.docker.internal:11434` | | Adresse du serveur Ollama (`host:port`) ; sous Linux, `docker-compose.linux.yml` la fixe à `127.0.0.1:11434` |
| `EMBEDDING_MODEL` | `nomic-embed-text` | | Modèle Ollama utilisé pour la vectorisation des documents |
| `LLM_MODEL` | _(auto-détecté)_ | | Modèle de génération Ollama ; si vide, le premier modèle disponible est sélectionné automatiquement |
| `CHUNK_SIZE` | `1200` | | Taille maximale d'un chunk en caractères |
| `CHUNK_OVERLAP` | `300` | | Chevauchement entre chunks consécutifs (en caractères) |
| `TOP_K` | `12` | | Nombre de chunks récupérés par requête RAG avant re-ranking |
| `TEMPERATURE` | `0.7` | | Créativité du LLM (`0` = précis et factuel, `1` = créatif) |

> **Accès réseau** : l'application n'a pas d'authentification. Le port est lié à `127.0.0.1` : seule la machine qui l'héberge y accède. Ne le publiez pas sur le réseau local. Un `docker run -p 8000:8000` lancé hors compose l'exposerait sur toutes les interfaces ; utilisez `-p 127.0.0.1:8000:8000`.

### Mise à jour depuis une version précédente (lots 2 et 2b)

Si vous avez déjà une installation, vérifiez ces points avant de reconstruire l'image (`docker compose up --build`) :

- **`LLM_MODEL`, `TOP_K` et `TEMPERATURE` sont désormais pris en compte.** Jusqu'ici, `docker-compose.yml` ne les transmettait pas au conteneur : leurs valeurs dans `.env` étaient ignorées. Relisez-les : si elles diffèrent des défauts (modèle auto-détecté, `12`, `0.7`), le comportement de l'application changera.
- **`OLLAMA_HOST` est testé en premier** au démarrage. Avant, `host.docker.internal` l'emportait s'il répondait, même si vous aviez choisi une autre adresse.
- **Un index illisible n'est plus supprimé au démarrage.** Il reste sur le volume `family-rag-index` et l'erreur est écrite dans les journaux. Sauvegardez le volume avant de réindexer ; la prochaine indexation que vous demandez remplace son contenu.
- L'image n'embarque plus `libmagic1` ni `poppler-utils`, qui n'étaient pas utilisés.
- **Réseau (lot 2b).** L'ancienne consigne Linux (décommenter `network_mode: host` dans `docker-compose.yml`) rendait l'application et tous vos documents accessibles à tout le réseau local, sans authentification. Elle est retirée. Si vous l'aviez suivie, remettez `docker-compose.yml` dans son état d'origine (`git checkout docker-compose.yml`) et lancez avec `-f docker-compose.yml -f docker-compose.linux.yml`.
- **`ollama-override.conf` est supprimé** : il faisait écouter Ollama sur `0.0.0.0`, donc sur tout le réseau. Si vous l'aviez installé (`/etc/systemd/system/ollama.service.d/`), supprimez-le puis `sudo systemctl daemon-reload && sudo systemctl restart ollama`. Les modèles et vos index ne sont pas touchés.
- **Dépendances (lot 3).** pypdf, Pillow, jinja2, python-docx et psutil passent à des versions corrigées (pypdf et Pillow cumulaient des dizaines d'avis de sécurité, dont des dénis de service par PDF ou image piégés). Reconstruisez l'image (`docker compose up -d --build`). Le format de l'index ne change pas : pas de réindexation à faire.
- **Serveur web (lot 4).** FastAPI, Starlette, Uvicorn et Pydantic passent à des versions corrigées (Starlette 0.41.3 cumulait 7 avis de sécurité), et l'image repose désormais sur `python:3.11.17-slim-trixie` au lieu de `python:3.11-slim`. Reconstruisez l'image (`docker compose up -d --build`). Le format de l'index ne change pas : pas de réindexation à faire. L'API et l'interface sont inchangées.
- L'adresse d'écoute de l'application est la variable `APP_HOST` (défaut `0.0.0.0` dans le conteneur, ce qui est nécessaire en mode bridge ; l'exposition reste limitée par `127.0.0.1:8000:8000`). Docker Desktop : rien à changer.

---

## 🧪 Tests

Les tests nécessitent `pytest` et les dépendances applicatives :

```bash
pip install pytest
# Depuis la racine du projet
pytest tests/ -v
```

Les tests ne requièrent **ni Ollama ni FAISS** — le moteur RAG est entièrement simulé.

| Fichier | Couverture |
|---------|------------|
| `tests/test_security.py` | Traversées de répertoire (LFI) sur `DocumentLoader` et `RAGEngine` — 13 tests |
| `tests/test_api.py` | Routes FastAPI principales + gestion des erreurs — 27 tests |

---

## 📏 Mesurer la qualité des réponses

`eval/` contient un petit corpus fictif, 15 questions de référence et un script de mesure (latence, source retrouvée, recall@k, éléments clés, citations). Il nécessite Ollama et n'est **pas** lancé par `pytest`. Il travaille sur un index temporaire : votre index et vos documents ne sont jamais touchés.

```bash
python eval/run_eval.py --label ma-machine --llm <votre-modele-de-chat>
```

Voir [eval/README.md](eval/README.md). Cet ajout ne change ni le comportement de l'application ni le format de l'index.

---

## 📖 Documentation

| Guide | Description |
|-------|-------------|
| [Administration](https://github.com/Liamdbav/FAMILY_RAG/blob/main/MANAGE.md) | Gestion, diagnostic et maintenance |
| [Changelog](CHANGELOG.md) | Historique complet des versions |

---

<div align="center">

Fait avec soin par **Liam** - License MIT — voir [LICENSE](LICENSE)

</div>

