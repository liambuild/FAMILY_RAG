# Audit FamilyRAG — 15 octobre 2026

Branche auditée : `modernisation` (commit `97db240`, identique au tag `v1-legacy`). Aucun fichier de code n'a été modifié.

**Contexte.** FamilyRAG est un projet open source public. L'objectif est un code fiable, à jour et sûr par défaut pour ses utilisateurs, sous Linux comme sous Docker Desktop. Les gravités évaluent donc ce que subit un utilisateur qui suit la documentation.

**Révision du 15/10/2026.** Contexte précisé, constat SEC13 ajouté, correction sur la réindexation (§5) et plan révisé (§6) à la suite des décisions consignées dans [DECISIONS.md](DECISIONS.md).

**Méthode**
- Lecture intégrale de `app/*.py`, `app/templates/index.html` (logique JS), `Dockerfile`, `docker-compose.yml`, `entrypoint.sh`, `.env.example` et des tests.
- Exécution de la suite de tests existante dans un venv Python 3.11 isolé (hors du dépôt) avec les versions exactes de `requirements.txt` : **40 tests passent en 5,3 s**, avec 3 avertissements de dépréciation.
- Bugs suspectés reproduits avec des scripts minimaux (marqués « vérifié » ci-dessous).
- Versions vérifiées le 15/10/2026 sur des sources en ligne : API JSON de PyPI, API GitHub Releases, endoflife.date, sources.debian.org, Docker Hub, docs.ollama.com. Les vulnérabilités viennent de l'API OSV (osv.dev), interrogée pour chaque version épinglée.

**Échelle de gravité** : **Critique** (perte de données ou compromission probable) · **Haute** (résultat faux ou blocage dans un usage normal) · **Moyenne** (dégradation réelle dans des conditions plausibles) · **Basse** (dette, cas limite) · **Info**.

---

## Résumé

L'application tient debout et la surface d'attaque est limitée, puisque le port est lié à `127.0.0.1`. Quatre problèmes touchent directement la qualité des réponses ou la fiabilité au quotidien :

1. **L'indexation sélective efface tout le reste de l'index.** `FAISS.from_documents` reconstruit l'index à partir des seuls fichiers cochés.
2. **Le LLM n'a jamais le nom des fichiers dans son contexte**, alors que le prompt exige des citations `[nom_fichier]`. Les citations sont donc devinées ou inventées.
3. **Le splitter duplique les listes et les tableaux** (bug de `re.split` avec deux groupes capturants, vérifié).
4. **Le re-ranking est séquentiel et son timeout ne fonctionne pas** (vérifié). Une question coûte de 24 à 48 appels LLM, et un Ollama figé bloque la requête indéfiniment.

Côté dépendances : la pile LangChain 0.3 utilise des chemins d'import supprimés en 1.x, et **pypdf 5.1.0 cumule 49 avis de sécurité** (déni de service par PDF piégé).

Côté déploiement : la consigne Linux du README (`network_mode: host`) **expose l'application et tous les documents au réseau local, sans authentification** (SEC13).

---

## 1. Architecture — pipeline RAG de bout en bout

```
 Navigateur (Alpine.js, app/templates/index.html)
   │  POST /api/index {selected_files}          POST /api/query {question, top_k, selected_sources}
   ▼                                            ▼
 FastAPI app/main.py ───────────────────────────────────────────────────────────────
   │ (synchrone, bloque l'event loop)           │ run_in_threadpool
   ▼                                            ▼
 RAGEngine.index_documents                     RAGEngine.query
   │                                            │
 ① INGESTION  app/document_loader.py            ⑤ RECHERCHE  FAISS.similarity_search_with_score(k×2 ou k×4)
   pdf → pypdf (texte natif, pas d'OCR)            │  + filtre « source » appliqué APRÈS la recherche
   txt/md → chardet                                ▼
   docx → python-docx (paragraphes)            ⑥ RE-RANKING LLM  _rerank_chunks (1 appel ChatOllama par chunk)
   eml → email stdlib (text/plain)                 │
   jpg/png → Tesseract fra+eng                     ▼
   + métadonnées heuristiques (date, année,    ⑦ GÉNÉRATION  ChatPromptTemplate | ChatOllama
     type, auteur) ; source = nom de fichier        contexte = contenus des chunks joints par « --- »
   │                                                (sans nom de source)
 ② DÉCOUPAGE  app/structure_aware_splitter.py      │
   sections > listes > tableaux > Recursive        ▼
   puis re-découpage forcé > 1500 caractères    JSON {answer, sources, chunks_preview, metrics}
   (rag_engine.py)
   │
 ③ EMBEDDINGS  OllamaEmbeddings (nomic-embed-text par défaut)
   │
 ④ STOCKAGE  FAISS.from_documents → save_local(/app/index/faiss_index)
             index.faiss + index.pkl (pickle) dans un volume Docker

 Parallèle : vision  POST /api/vision et /api/vision/base64 → Ollama /api/chat avec images (ministral-3, llava, moondream)
```

| Étape | Fichiers / symboles | Remarques |
|---|---|---|
| Configuration | `app/config.py` (`Settings`, `get_settings` en `lru_cache`) | Singleton **muté à chaud** par `RAGEngine.update_settings`. Rien n'est persisté. |
| Démarrage | `app/entrypoint.sh` (détection de l'hôte Ollama), `main.py:26-30` (`lifespan`), `rag_engine.py:50-100` (détection du LLM) | Appel réseau bloquant au démarrage. |
| Ingestion | `document_loader.py:43-58` (`list_files`), `:178-216` (`load_all`), `:218-284` (`load_specific`), `:286-390` (parseurs) | Code dupliqué entre `load_all` et `load_specific`. |
| Métadonnées | `document_loader.py:60-176` | Regex et mots-clés. Le filtre ne les exploite que via `source`. |
| Découpage | `structure_aware_splitter.py` + `rag_engine.py:154-183` | `chunk_size` est ignoré dans les chemins structurés, qui utilisent `max_chunk_size=1500`. |
| Embeddings | `rag_engine.py:62-65`, `:550-586` | Modèle modifiable à chaud ; l'index est alors supprimé. |
| Stockage | `rag_engine.py:102-128`, `:193-196` | Reconstruction complète à chaque indexation. Écriture non atomique. |
| Recherche | `rag_engine.py:359-439` | Filtrage manuel en Python après le top-k. |
| Re-ranking | `rag_engine.py:255-331` | Note LLM de 0 à 10 par chunk. |
| Génération | `rag_engine.py:441-499` | `num_ctx` non défini. Aucun timeout. |
| Vision | `rag_engine.py:588-736`, `main.py:370-388` | Appels httpx directs à Ollama. |
| Interface | `templates/index.html` (1 339 lignes), `static/alpine.min.js` 3.14.1, `static/tailwind.cdn.js` 3.4.17 (Play CDN) | Conversations stockées dans `localStorage`, **historique non envoyé au LLM**. |
| Déploiement | `Dockerfile`, `docker-compose.yml`, `ollama-override.conf` | Image `python:3.11-slim` (Debian trixie aujourd'hui), exécutée en root. |

---

## 2. Stack — versions du projet et dernières versions stables

Vérification du 15/10/2026. « Transitif » = version effectivement résolue par `pip` à partir des épinglages actuels.

### Dépendances Python (`app/requirements.txt`)

| Paquet | Projet | Dernière stable (date) | Écart | Avis OSV sur la version du projet | Utilisé ? |
|---|---|---|---|---|---|
| fastapi | 0.115.6 | **0.143.1** (2026-10-14) | 28 mineures | aucun | oui |
| starlette *(transitif)* | 0.41.3 | **1.8.0** (2026-10-13) | majeure | 7 (dont DoS Range sur `StaticFiles`, validation du `Host`) | oui |
| uvicorn[standard] | 0.34.0 | **0.54.0** (2026-09-25) | 20 mineures | aucun | oui |
| python-multipart | 0.0.20 | **0.0.32** (2026-06-04) | — | 7 CVE (DoS, smuggling) | **non** (aucun `Form`/`UploadFile`) |
| langchain | 0.3.14 | **1.4.6** (2026-10-14) | majeure | 2 (fonctionnalités non utilisées ici) | seulement pour 3 imports dépréciés |
| langchain-core *(transitif)* | 0.3.63 | **1.6.10** (2026-10-12) | majeure | — | oui (indirectement) |
| langchain-text-splitters *(transitif)* | 0.3.8 | **1.1.3** (2026-10-02) | majeure | — | oui (`RecursiveCharacterTextSplitter`) |
| langchain-community | 0.3.14 | **0.4.2** (2026-05-22) | mineure (tire `langchain-classic`, SQLAlchemy, aiohttp) | 1 (XXE, chargeur non utilisé) | oui (FAISS uniquement) |
| langchain-ollama | 0.2.2 | **1.1.0** (2026-04-07) | majeure | aucun | oui |
| faiss-cpu | 1.9.0.post1 | **1.15.1** (2026-09-16) | 6 mineures | aucun | oui |
| numpy *(transitif)* | 1.26.4 | — (faiss 1.15 accepte ≥ 1.25) | — | — | oui |
| pypdf | 5.1.0 | **6.20.1** (2026-10-12) | majeure | **49 avis** (boucles infinies, épuisement RAM) | oui |
| python-docx | 1.1.2 | **1.2.0** (2025-06-16) | mineure | aucun | oui |
| python-magic | 0.4.27 | 0.4.27 (2022-06-07) | à jour, projet inactif | aucun | **non** |
| chardet | 5.2.0 | **7.6.0** (2026-08-14) | 2 majeures | aucun | oui |
| pytesseract | 0.3.13 | 0.3.13 (2024-08-16) | à jour | aucun | oui |
| Pillow | 11.1.0 | **12.3.0** (2026-07-01) | majeure | **17 avis** (dont écritures hors limites PSD, bombes de décompression) | oui |
| pydantic | 2.10.4 | **2.14.1** (2026-10-11) | 4 mineures | aucun | oui |
| pydantic-settings | 2.7.1 | **2.16.0** (2026-10-14, requiert Python ≥ 3.11) | 9 mineures | aucun | oui |
| jinja2 | 3.1.5 | **3.1.6** (2025-03-05) | patch | 1 (sandbox, non exploitable ici) | oui |
| aiofiles | 24.1.0 | 25.1.0 (2025-10-09) | — | aucun | **non** |
| httpx | 0.28.1 | 0.28.1 (2024-12-06) | à jour | aucun | oui |
| psutil | 6.1.1 | **7.2.2** (2026-01-28) | majeure | aucun | oui |
| pytest *(absent des requirements)* | — | 9.1.1 (2026-06-19) | — | — | tests |

### Hors PyPI

| Composant | Projet | Dernière stable | Source |
|---|---|---|---|
| Python (image Docker) | 3.11 (`python:3.11-slim`, non épinglé au patch) | 3.14.8. La branche 3.11 en est à 3.11.17 et sa fin de vie est fixée au 2027-10-31 | endoflife.date, Docker Hub |
| Debian de l'image | trixie (alias actuel de `3.11-slim`) | trixie | Docker Hub |
| Tesseract | 5.5.0 (paquet Debian trixie) | 5.5.3 en amont (2026-07-24) | sources.debian.org, GitHub |
| Ollama (externe) | « 0.13.1+ » d'après `MANAGE.md` | **v0.40.4** (2026-10-12) | GitHub |
| Alpine.js (vendorisé) | 3.14.1 | 3.17.4 (2026-09-21) | GitHub |
| Tailwind (Play CDN vendorisé) | 3.4.17 | 3.4.19 en v3 ; **4.3.3** en v4 | GitHub |

**Lecture de l'écart.** Les mises à jour qui comptent pour la sécurité sont pypdf, Pillow et starlette (via fastapi). Celle qui compte pour la pérennité est LangChain : les imports `langchain.text_splitter`, `langchain.schema` et `langchain.prompts` n'existent plus en 1.x. Tout le reste relève de l'entretien.

---

## 3. Problèmes par catégorie

### 3.1 Stabilité

| ID | Gravité | Emplacement | Problème |
|---|---|---|---|
| S1 | **Haute** | `app/rag_engine.py:300-306` | **Le timeout de 30 s du re-ranking est inopérant (vérifié).** La sortie du `with ThreadPoolExecutor(...)` appelle `shutdown(wait=True)`, qui attend la fin de la tâche. Test : un timeout de 0,5 s a bloqué 3,0 s. Un Ollama figé bloque donc la requête sans limite. |
| S2 | **Haute** | `app/main.py:119` | `rag_engine.index_documents` est appelé **en synchrone** dans un handler `async`. Pendant toute l'indexation (OCR, embeddings : plusieurs minutes), l'event loop est gelé : interface, `/health` (et donc le healthcheck Docker) et requêtes ne répondent plus. |
| S3 | Haute | `app/rag_engine.py:489`, `:69-73` | `chain.invoke` sans timeout et `ChatOllama` sans `timeout` : un modèle qui ne répond pas bloque un thread du pool indéfiniment. |
| S4 | Moyenne | `app/rag_engine.py:195-196`, `:523-548`, `:565-583` | Aucune exclusion mutuelle. Une indexation concurrente d'une requête remplace `self.vectorstore` en cours de route. Deux indexations simultanées écrivent le même dossier. Les paramètres sont mutés sans verrou sur le singleton `Settings` partagé. |
| S5 | Moyenne | `app/rag_engine.py:128` | Sauvegarde non atomique (`save_local` écrit directement `index.faiss` et `index.pkl`). Un arrêt pendant l'écriture laisse un index corrompu… |
| S6 | Moyenne | `app/rag_engine.py:114-121` | … qui est **supprimé automatiquement** (`shutil.rmtree`) à la moindre exception de chargement. C'est aussi ce qui se passera si une montée de version rend le pickle illisible. Risque direct pendant la migration LangChain. |
| S7 | Moyenne | `app/rag_engine.py:692`, `:657-681` | `analyze_image_base64` est `async` mais appelle `_detect_vision_model`, qui fait un `httpx.get` synchrone (jusqu'à 5 s) : l'event loop est bloqué. |
| S8 | Moyenne | `rag_engine.py:15,18,19` ; `document_loader.py:13` ; `structure_aware_splitter.py:5-6` ; `config.py:31-32` ; `main.py:76` | APIs dépréciées ou supprimées : imports `langchain.*` (retirés en 1.x), `class Config` Pydantic (avertissement émis, retrait prévu en v3), `TemplateResponse(name, {...})` (avertissement émis). |
| S9 | Basse | `app/rag_engine.py:58-59` | Le LLM n'est détecté qu'au démarrage. Si Ollama démarre après le conteneur, aucun modèle n'est actif tant que l'utilisateur n'en choisit pas un à la main. |
| S10 | Basse | `.gitignore:1` | Ligne parasite « Update readme » (sans effet, mais signe de commit accidentel). |

### 3.2 Fiabilité (justesse des résultats)

| ID | Gravité | Emplacement | Problème |
|---|---|---|---|
| F1 | **Critique** | `app/rag_engine.py:139-141` + `:195` ; `index.html:1218-1220` | **L'indexation sélective remplace tout l'index.** `FAISS.from_documents` crée un index neuf avec les seuls fichiers cochés : tout ce qui était indexé auparavant disparaît sans avertissement. Le README présente pourtant la fonction comme un moyen de ne pas réindexer tout le dossier. |
| F2 | **Haute** | `app/structure_aware_splitter.py:168`, `:215` | **Les listes et les tableaux sont dupliqués (vérifié).** `re.split(f'({pattern})')` alors que le motif contient déjà un groupe capturant : chaque bloc apparaît deux fois dans `parts` et donc deux fois dans les chunks. Cela gonfle l'index, biaise le classement et gaspille du contexte. |
| F3 | **Haute** | `app/rag_engine.py:445-453` vs `:463` | Le prompt exige `[nom_fichier]`, mais le contexte ne contient **que** `page_content`, sans nom de source. Les citations affichées sont inventées par le modèle. |
| F4 | **Haute** (à confirmer sur votre matériel) | `app/rag_engine.py:69-73`, `:441-453` | `num_ctx` n'est pas défini. D'après la doc Ollama, la fenêtre par défaut est de **4k tokens sous 24 Go de VRAM**. Le contexte envoyé atteint 12 chunks × ~1 500 caractères (~5 000 tokens en français) plus le prompt, donc il dépasse : Ollama tronque sans erreur, et les instructions ou une partie des extraits disparaissent. |
| F5 | **Haute** | `app/rag_engine.py:365-417` | Le filtre par sources est appliqué **après** une recherche globale limitée à `4×k` (48) résultats. Si les documents sélectionnés ne figurent pas dans ce top 48, la réponse est « Aucun document trouvé correspondant aux critères », alors qu'ils sont bien indexés. FAISS (langchain-community) accepte nativement `filter=` + `fetch_k=`. |
| F6 | Moyenne | `rag_engine.py:318,325,433-439,449` ; `index.html:1077-1080` | Les scores mélangent deux échelles : distance L2 FAISS (plus bas = mieux, non bornée) quand il n'y a pas de re-ranking (`len ≤ k`), note LLM entre 0 et 1 sinon, et `1/(1+d)` en cas d'échec. La « confiance % » de l'interface fait la moyenne de ces valeurs : elle n'a aucun sens et peut dépasser 100 %. |
| F7 | Moyenne | `document_loader.py:195,262` ; `index.html:359,1004` | `source` = nom de fichier seul. Deux fichiers `facture.pdf` dans deux sous-dossiers se confondent pour le filtre, l'affichage et les statistiques. |
| F8 | Moyenne | `rag_engine.py:550-586` ; `config.py:12` | Le changement de modèle d'embedding n'est pas persisté. Après un redémarrage, le modèle de `.env` est réutilisé avec un index construit par un autre modèle : erreur de dimension ou résultats absurdes. De plus, l'index est supprimé **avant** que la réindexation n'ait réussi. Le modèle utilisé n'est pas enregistré à côté de l'index. |
| F9 | Moyenne | `docker-compose.yml:15-20` vs `.env.example:16,20,23` | `LLM_MODEL`, `TOP_K` et `TEMPERATURE` sont documentés dans `.env.example` mais **non transmis** au conteneur : ils sont ignorés. |
| F10 | Moyenne | `app/entrypoint.sh:7-12` | `OLLAMA_HOST` défini par l'utilisateur est testé **en dernier**. Si `host.docker.internal` répond, il l'emporte sur la configuration explicite. |
| F11 | Moyenne | `rag_engine.py:88-95` vs `main.py:237-243,282-288` | La détection automatique du LLM prend le premier modèle « non embedding » d'une liste incomplète, qui diffère de celle de `main.py`. Elle peut retenir `bge-m3`, `qwen3-embedding` ou un modèle vision. |
| F12 | Moyenne | `structure_aware_splitter.py:127-130`, `:147-150`, `:143` | Métadonnée `section` erronée : un chunk sauvegardé reçoit le titre de la section **suivante**, et le dernier chunk n'en reçoit aucun. |
| F13 | Basse | `structure_aware_splitter.py:72,76` | `^\d+\.\s+[A-Z]` combiné à `IGNORECASE` reconnaît toute ligne « 1. texte » comme un titre : la plupart des listes numérotées partent dans le chemin « sections ». Un titre suivi d'un autre titre est perdu (`:119-120`). |
| F14 | Basse | `structure_aware_splitter.py:125,177,244` | `chunk_size` (configurable) est ignoré dans les chemins structurés, qui utilisent `max_chunk_size` codé en dur à 1 500 (`rag_engine.py:160,169`). |
| F15 | Basse | `document_loader.py:372-381` | E-mails HTML seuls : corps vide *(précisé au lot 1 : seulement pour un e-mail multipart sans partie `text/plain` ; un e-mail non multipart en `text/html` est lu brut, balises comprises)*. Charset inconnu : `LookupError`, et tout le fichier est rejeté. |
| F16 | Basse | `document_loader.py:347` ; `:327-335` | DOCX : les tableaux sont ignorés. PDF scannés : aucun texte (pas d'OCR de repli, alors que `poppler-utils` est installé). |
| F17 | Basse | `document_loader.py:93-96`, `:137` | Dates extraites du contenu non normalisées (formats mélangés). Classification par sous-chaînes naïve (`ml` trouve « html », `four` trouve « fournisseur »). |
| F18 | Basse | `document_loader.py:186` | `load_all` ignore les fichiers en erreur sans rien journaliser, contrairement à `load_specific`. |
| F19 | Basse | `rag_engine.py:518` | `total_documents` compte les fichiers présents dans `/data`, pas les fichiers indexés. |
| F20 | Basse | `main.py:126-133` | Une exception d'indexation renvoie HTTP **200** avec `success:false`, contre 400 pour l'autre chemin d'erreur. Les tests figent ce comportement (`test_api.py:224-232`). |
| F21 | Basse | `index.html:1191-1215` | Barre de progression simulée (aléatoire). « Suspendre » coupe la requête côté navigateur mais l'indexation continue sur le serveur. |
| F22 | Info | `main.py:50` ; `index.html` | `QueryRequest.image_data` n'est jamais utilisé. Les « conversations » n'envoient pas l'historique : chaque question est traitée isolément. |
| F23 | Basse | `document_loader.py:358-359` | E-mails : l'en-tête `Subject` encodé (RFC 2047, par exemple `=?utf-8?q?D=C3=AEner?=`) est recopié tel quel dans « Sujet: » : `msg['subject']` n'est pas décodé. *Repéré au lot 1, non corrigé ; corrigé au lot 11 (`xfail` : `test_loader.py::test_eml_encoded_subject_is_decoded`).* |
| F24 | **Haute** | `document_loader.py:337-342` | Fichiers texte : `chardet` classe en ISO-8859-1 (confiance 0,73) un fichier UTF-8 court qui contient peu de caractères accentués, et « à » devient « Ã  » dans l'index. Vérifié avec la version installée (`Bonjour à tous, voici une note.`). Gravité relevée : pour un corpus majoritairement français, la corruption des accents dégrade directement la recherche. *Repéré au lot 1, non corrigé ; corrigé au lot 11 (`xfail` : `test_loader.py::test_txt_short_utf8_is_not_misdetected_as_latin1`).* |

### 3.3 Performance

| ID | Gravité | Emplacement | Problème |
|---|---|---|---|
| P1 | **Haute** | `rag_engine.py:293-306`, `:365-368`, `:433` | Re-ranking = **un appel LLM séquentiel par chunk** : 24 par question (k=12), 48 avec un filtre de sources. Sur un LLM local, comptez de quelques secondes à plusieurs minutes par question. Le pool de threads est recréé à chaque chunk. |
| P2 | Moyenne | `rag_engine.py:195` | Chaque indexation recalcule tous les embeddings et refait tout l'OCR, même pour un seul fichier ajouté. |
| P3 | Basse | `main.py:325` ; `index.html:870` | `psutil.cpu_percent(interval=0.1)` bloque l'event loop 100 ms, toutes les 2 s, pour chaque onglet ouvert. |
| P4 | Basse | `index.html:7` | Le Play CDN de Tailwind compile le CSS dans le navigateur (407 Ko de JS). Tailwind le déconseille en production. |
| P5 | Basse | `document_loader.py:340` | `chardet.detect` porte sur le fichier entier : lent sur un gros `.txt`. |

### 3.4 Sécurité

Contexte : projet open source sans comptes utilisateurs ; le compose principal lie le port à `127.0.0.1`. Les gravités évaluent ce que subit un utilisateur qui suit la documentation.

| ID | Gravité | Emplacement | Problème |
|---|---|---|---|
| SEC1 | **Haute** | `requirements.txt:11` ; `document_loader.py:329` | pypdf 5.1.0 : 49 avis OSV (boucles infinies, épuisement mémoire). Un PDF piégé déposé dans `/data` (pièce jointe reçue par e-mail par exemple) suffit à bloquer ou à tuer l'indexation. Corrigé en 6.19.0+, dernière version 6.20.1. |
| SEC13 | **Haute** | `README.md:229` ; `docker-compose.yml:5-7,15` ; `Dockerfile:34` ; `MANAGE.md:341` | *(ajouté à la révision)* Pour Linux, le README et le compose conseillent `network_mode: host`. Dans ce mode, le mappage `127.0.0.1:8000:8000` est ignoré et uvicorn écoute sur `0.0.0.0` (CMD du Dockerfile) : l'application, donc tous les documents, devient accessible depuis le réseau local sans authentification. `MANAGE.md:341` entretient la confusion. |
| SEC2 | Moyenne | `requirements.txt:19` ; `document_loader.py:387` | Pillow 11.1.0 : 17 avis, dont des écritures hors limites (PSD). `Image.open` choisit le décodeur d'après le **contenu**, pas l'extension : un fichier `.png` qui est en réalité un PSD est décodé comme tel. Corrigé en 12.3.0. |
| SEC3 | Moyenne | `main.py:33` (aucun middleware) | Pas de validation de l'en-tête `Host` ni d'authentification : un site malveillant ouvert dans le navigateur peut, par **DNS rebinding**, lire `/api/files` et `/api/query` (vos documents) via `127.0.0.1:8000`. Parade simple : `TrustedHostMiddleware`. |
| SEC4 | Moyenne | `ollama-override.conf:3` | Expose Ollama sur `0.0.0.0` sans authentification : n'importe quel appareil du réseau local (Wi-Fi invité compris) peut l'utiliser, télécharger ou supprimer des modèles. |
| SEC5 | Moyenne | `main.py:49,55-56,67` | Aucune borne sur les entrées. `top_k=1000` déclenche 2 000 appels LLM (déni de service), `temperature` n'est pas bornée, `image_data` base64 n'a pas de limite de taille (mémoire). |
| SEC6 | Basse | `rag_engine.py:107-111` | `allow_dangerous_deserialization=True` (pickle). Quiconque peut écrire dans le volume d'index obtient une exécution de code. Exposition faible (volume Docker local). |
| SEC7 | Basse | `Dockerfile` (pas de `USER`) ; `docker-compose.yml:10` | Le conteneur tourne en root et `/data` est monté en lecture-écriture, alors que l'application ne fait que lire : `:ro` suffit. |
| SEC8 | Basse | starlette 0.41.3 (transitif) | 7 avis, dont un DoS par en-tête `Range` sur `StaticFiles` (servi ici sous `/static`) et l'injection d'en-tête `Host` (CVE-2026-48710). |
| SEC9 | Basse | `main.py:130,272,316,366` ; `rag_engine.py:212,652,733` | Messages d'exception bruts renvoyés au client (chemins, URL internes). |
| SEC10 | Info | `requirements.txt:4` | python-multipart 0.0.20 a 7 CVE, mais le paquet n'est pas utilisé : il suffit de le retirer. |
| SEC11 | Info | jinja2 3.1.5, langchain 0.3.14, langchain-community 0.3.14 | CVE non exploitables ici (sandbox Jinja, middleware de recherche de fichiers, chargeurs XML non utilisés). À corriger en passant, sans urgence. |
| SEC12 | Info | `rag_engine.py:456-485` | Injection de prompt par le contenu des documents (un e-mail peut contenir des instructions). Risque inhérent au RAG, acceptable sur un corpus familial. |

---

## 4. Tests existants

**État mesuré** : 40 tests, tous verts en 5,3 s (Python 3.11, versions épinglées). `pytest` ne figure dans aucun fichier de dépendances, et il n'y a ni CI ni `pytest.ini`.

### Ce qui est couvert

| Fichier | Tests | Couverture réelle |
|---|---|---|
| `tests/test_api.py` | 27 | **Forme** des réponses JSON de chaque route, avec un `RAGEngine` entièrement remplacé par un `MagicMock` : validation de la question vide, transmission de `selected_sources` vers `filter_metadata`, codes 400/200 de `/api/index`, transmission des paramètres. |
| `tests/test_security.py` | 13 | Gardes de traversée de chemin (`..`, chemin absolu, symlink) sur `load_specific` et `analyze_image_with_vision`, et chargement d'un `.txt` valide. |

### Ce qui n'est pas couvert

- **Découpage** (`structure_aware_splitter.py`) : 0 test. C'est là que se trouvent F2, F12, F13 et F14.
- **Parseurs** : seul `.txt` est testé. Rien sur PDF, DOCX, EML, OCR d'image, ni sur l'extraction de métadonnées (date, année, type, auteur).
- **Moteur** (`rag_engine.py`) : 0 test sur `index_documents`, `query` (filtre, re-ranking, scores, contexte et prompt), `_save_index`/`_load_index` (aller-retour, suppression en cas de corruption), `update_settings`, `update_embedding_model`, `_detect_llm_model`, `_detect_vision_model`, `analyze_image_base64`.
- **Contrat API ↔ moteur** : le mock renvoie ce qu'on lui dit, donc une dérive de signature côté moteur passerait inaperçue.
- **Config et déploiement** : `Settings` (variables d'environnement), `entrypoint.sh`, transmission des variables par `docker-compose`.
- **Interface** : rien. C'est acceptable vu la taille du projet.

### Faiblesses des tests actuels

- `TestHealth` et `TestOllamaModels` (`test_api.py:109-122`, `:308-325`) font **de vrais appels réseau** et acceptent 200 ou 503 : leur résultat dépend de la machine.
- `test_index_exception_returns_json_not_500` (`:224-232`) fige le comportement discutable F20.
- `test_valid_image_passes_guard` passe uniquement parce que la détection du modèle vision est mockée.

---

## 5. Décisions par composant

Principe : **stabilité d'abord**. Je ne propose un remplacement que lorsqu'il retire du risque sans rien ajouter de neuf. Les coûts sont estimés pour une personne qui connaît le code, tests du lot 1 en place.

| Composant | Décision | Justification | Coût de migration |
|---|---|---|---|
| **FastAPI + uvicorn** (et starlette) | METTRE À JOUR → 0.143.1 / 0.54.0 | Corrige 7 avis starlette. Changements attendus : signature de `TemplateResponse`, dépréciations du `TestClient`. | 1–2 h, dans un lot dédié |
| **python-multipart** | RETIRER | Non utilisé ; 7 CVE. | 5 min |
| **aiofiles** | RETIRER | Non utilisé. | 5 min |
| **python-magic** + `libmagic1` (Dockerfile) | RETIRER | Non utilisé. | 5 min |
| **poppler-utils** (Dockerfile) | RETIRER, sauf si vous voulez l'OCR des PDF scannés (Q9) | Non utilisé aujourd'hui. | 5 min |
| **langchain** (méta-paquet) | **REMPLACER** par `langchain-core` + `langchain-text-splitters` | Gain net : il ne sert qu'à 3 imports dépréciés, et la 1.x tire `langgraph` sans aucune utilité ici. Le code ne change que par ses imports (5 lignes, 3 fichiers). | 1 h |
| **langchain-community** (FAISS) | METTRE À JOUR → 0.4.2 | `FAISS` y est toujours (vérifié dans le wheel 0.4.2 : `filter`, `fetch_k`, `add_documents`, `delete` présents). Inconvénient : tire `langchain-classic`, SQLAlchemy et aiohttp. | 1–2 h, plus une réindexation par sécurité |
| *Alternative* : petit wrapper FAISS maison (faiss + docstore JSON) | Pas maintenant | Supprimerait le pickle (SEC6) et ~10 dépendances transitives, mais c'est du code neuf. À reconsidérer seulement si la 0.4.x pose problème. | 1–2 sessions + réindexation |
| **langchain-ollama** | METTRE À JOUR → 1.1.0 | Nécessaire avec langchain-core 1.x. Donne accès aux paramètres `num_ctx` et `keep_alive`. | inclus dans le lot LangChain |
| **faiss-cpu** | METTRE À JOUR → 1.15.1 | Compatible numpy 2. Le format binaire FAISS est stable, mais **réindexer** reste plus sûr que se fier au pickle. | inclus, plus réindexation |
| **Embedding `nomic-embed-text`** | GARDER | Les préfixes `search_query:` / `search_document:` recommandés par Nomic pourraient améliorer la recherche, mais imposent une réindexation et une évaluation. Optionnel (Q4). | — |
| **pypdf** | METTRE À JOUR → 6.20.1 (**prioritaire**) | 49 avis. L'API utilisée (`PdfReader`, `extract_text`) est inchangée. | 30 min |
| **Pillow** | METTRE À JOUR → 12.3.0 | 17 avis. API utilisée minimale (`Image.open`). | 30 min |
| **jinja2** | METTRE À JOUR → 3.1.6 | Patch. | 5 min |
| **python-docx** | METTRE À JOUR → 1.2.0 | Mineure. | 10 min |
| **pydantic / pydantic-settings** | METTRE À JOUR → 2.14.1 / 2.16.0 | Mineures ; migrer `class Config` vers `model_config`. | 30 min |
| **chardet** | GARDER 5.2.0 | Aucune CVE. La 7.x est une double majeure sans gain ici. | — |
| **pytesseract / Tesseract 5.5.0** | GARDER | À jour pour Debian trixie. | — |
| **httpx** | GARDER | Dernière version. | — |
| **psutil** | METTRE À JOUR → 7.2.2 (faible priorité) | Usage trivial. | 10 min |
| **Python 3.11** | GARDER (épingler `python:3.11.17-slim-trixie`) | Supporté jusqu'au 2027-10-31. Une montée en 3.12 ou 3.13 n'apporte rien d'urgent : à planifier avant l'été 2027. | 10 min (épinglage) |
| **StructureAwareSplitter** | METTRE À JOUR (corriger) | Le concept est bon ; les bugs F2, F12, F13 et F14 sont locaux. | 1 session + réindexation |
| **DocumentLoader** | METTRE À JOUR | Factoriser `load_all`/`load_specific`, `source` = chemin relatif, EML HTML, tableaux DOCX. | 1 session + réindexation |
| **Cycle de vie de l'index** | METTRE À JOUR | Indexation incrémentale par source, verrou, sauvegarde atomique, plus de suppression automatique, modèle d'embedding enregistré avec l'index. | 1–2 sessions |
| **Re-ranking LLM** | METTRE À JOUR, désactivé par défaut (D4) | Vrai timeout, plafond de candidats, désactivable, voire une seule requête de notation groupée. Un cross-encoder (sentence-transformers + torch, ~2 Go) serait plus précis mais ajoute une pile lourde : pas de gain net pour ce projet. | 1 session |
| **Alpine.js** | GARDER (3.17.4 en option) | Aucun problème constaté. | 15 min |
| **Tailwind Play CDN** | GARDER pour l'instant | Le remplacer par un CSS précompilé (CLI autonome v3.4.19) est plus propre mais ajoute une étape de build. Gain modeste pour un outil local. | 1–2 h si souhaité |
| **Ollama** (externe) | GARDER ; mettre à jour la version minimale documentée | Rien dans le code ne dépend d'une version récente, mais `MANAGE.md` mentionne 0.13.1. | doc |

**Réindexation** *(corrigé à la révision)* : les lots 5 (par précaution), 6, 9 et 11 changent le contenu ou le format de l'index. Le lot 7 **ne l'impose pas** : la première version de cet audit l'incluait à tort. Chaque lot réindexe librement le corpus de test. Pour les index des utilisateurs, la règle est fixée par DECISIONS.md (D2) : jamais de suppression automatique, détection d'un index incompatible, réindexation demandée par un message clair.

---

## 6. Plan en lots (révisé)

> **Révisé le 15/10/2026** d'après [DECISIONS.md](DECISIONS.md). Par rapport à la première version :
> - lots **1b**, **2b**, **4b** et **7b** ajoutés ;
> - F7 déplacé du lot 11 au lot 9, S6 déplacé du lot 9 au lot 2 ;
> - le regroupement des réindexations est abandonné ;
> - le prérequis bloquant du lot 5 est redéfini.

**Règles communes (D10).**
- Chaque lot a sa branche `lot-<n>`, créée depuis `modernisation` **après la fusion du lot précédent**, et sa PR vers `modernisation`.
- Les tests sont verts à la fin de chaque lot et le corpus de test est réindexé librement.
- Sans CI, chaque PR cite la commande de test et son résultat ; les lots 6, 7 et 8 citent aussi le résultat de `eval/run_eval.py`.
- Les tests de caractérisation du lot 1 qui figent un comportement corrigé plus tard sont mis à jour dans le lot qui le corrige, explicitement.

| Lot | Branche | Objet | Prérequis | Effort |
|---|---|---|---|---|
| 1 ✅ | `lot-1` | Tests qui protègent le comportement actuel | — | 1 session |
| 1b ✅ | `lot-1b` | Corpus de test, 15 questions, script de mesure (la référence `v1-legacy` reste à produire, voir point ouvert) | 1 | 1 session |
| 2 ✅ | `lot-2` | Dépendances mortes, configuration, entrypoint, **plus de suppression automatique d'index** | 1 | 1–2 h |
| 2b ✅ | `lot-2b` | Réseau local par défaut, override Linux (SEC13, SEC4) | 2 | 1–2 h |
| 3 ✅ | `lot-3` | pypdf, Pillow, jinja2, python-docx, psutil | 2 | 1 h |
| 4 ✅ | `lot-4` | fastapi, starlette, uvicorn, pydantic, image `python:3.11.17-slim-trixie` | 3 | 1–2 h |
| 4b ✅ | `lot-4b` | `index_meta.json`, détection d'incompatibilité, README « Mettre à jour depuis v1-legacy » | 4 | 1 session |
| 5 | `lot-5` | Migration LangChain 1.x | **⛔ 4b fusionné** | 1 session |
| 6 | `lot-6` | F2, F12, F13, F14 | 5 | 1 session |
| 7 | `lot-7` | F3, F4 (`NUM_CTX`), F5, F6 | 6 | 1 session |
| 7b | `lot-7b` | `settings.json`, l'interface l'emporte sur `.env` | 4b | 1 session |
| 8 | `lot-8` | Re-ranking désactivé par défaut, timeout réel (S1, S3, P1) | 7, 7b | 1 session |
| 9 | `lot-9` | F1, **F7**, S2, S4, S5, P2 | 4b, 5 | 1–2 sessions |
| 10 | `lot-10` | SEC3, SEC5, SEC7, SEC9, S7, F11, F20 | 4 | 1 session |
| 11 | `lot-11` | F15, F16 (tableaux DOCX), F17, F18, **F23, F24** ; OCR des PDF scannés documenté comme option | 9 | 1 session |
| 12 | `lot-12` | Documentation, progression réelle, Alpine, CSS Tailwind (optionnel) | — | variable |

### Lot 1 — Filet de sécurité : tests de caractérisation *(aucun changement de code applicatif)* ✅ Fait
- Ajouter `requirements-dev.txt` (pytest épinglé) et `pytest.ini`. Rendre déterministes les tests `/health` et `/api/ollama/*` en mockant httpx.
- **Splitter** : tests « golden » sur des textes types, qui figent la sortie actuelle. Les bugs connus (F2, F12) sont décrits par des tests `xfail(strict=True)` exprimant le comportement attendu.
- **Loader** : un fichier minimal par format, généré dans `tmp_path`, plus les métadonnées.
- **Moteur** sans Ollama (`DeterministicFakeEmbedding` et un faux chat model de `langchain_core`) : aller-retour sauvegarde/chargement, `query` (filtre, re-ranking, retours anticipés), forme du contexte, `update_embedding_model`, F1 (caractérisation plus `xfail` du comportement voulu, D1), S6 (suppression actuelle de l'index illisible).
- **Contrat API ↔ moteur** : quelques tests de bout en bout sur un vrai `RAGEngine` avec les faux modèles.
- *Fini quand* : tous les tests passent sur `v1-legacy`, sans réseau, en moins de 30 s.

**Résultat (lot 1).** `.venv/bin/python -m pytest -q` : 139 tests passent et 11 `xfail(strict=True)` échouent comme prévu, en environ 3 s. La suite passe aussi sur le tag `v1-legacy` (`app/` est inchangé). Une garde dans `conftest.py` refuse toute connexion sortante. `requirements-dev.txt` contient `pytest==9.1.1` seul (version vérifiée sur PyPI).

Chaque `xfail` devient un test normal dans le lot indiqué, qui retire alors le marqueur (`xfail_strict` fait échouer la suite sinon) :

| Test `xfail` | Constat | Décision | Lot |
|---|---|---|---|
| `test_splitter.py::test_table_chunk_appears_once`, `::test_list_block_appears_once` | F2 | — | 6 |
| `test_splitter.py::test_section_metadata_is_the_chunk_own_title` | F12 | — | 6 |
| `test_engine_index.py::test_unreadable_index_is_left_in_place` | S6 | D2, D12 | 2 |
| `test_engine_index.py::test_new_model_asks_for_reindexing_but_keeps_the_index` (ex-xfail) | F8 | D2 | 4b ✅ |
| `test_engine_query.py::test_each_extract_is_prefixed_with_its_source` | F3 | — | 7 |
| `test_engine_query.py::test_selected_source_is_found_wherever_it_ranks` | F5 | — | 7 |
| `test_loader.py::test_source_is_the_relative_path` | F7 | D5 | 9 |
| `test_loader.py::test_eml_encoded_subject_is_decoded` | F23 | — | 11 |
| `test_loader.py::test_txt_short_utf8_is_not_misdetected_as_latin1` | F24 | — | 11 |
| `test_engine_index.py::test_selective_indexing_adds_to_the_existing_index` | F1 | D1 | 9 |

Les tests de caractérisation qui figent un comportement corrigé plus tard portent la mention du constat et du lot dans leur docstring (F6, F7, F8, F13, F14, F15, F16, F17, F18, F19). Les lots concernés les mettent à jour explicitement.

### Lot 1b — Mesure de qualité reproductible *(nouveau, D4)* ✅ Fait (outil livré)
- `eval/corpus/` : documents fictifs versionnés (PDF texte, DOCX avec tableau, `.eml`, image pour l'OCR, Markdown avec listes et tableau, deux `facture.pdf` homonymes dans deux sous-dossiers) et 48 documents distracteurs (`distracteurs/`), pour dépasser 4 × `top_k` extraits indexés.
- `eval/questions.yaml` : 15 questions avec réponse et source(s) attendues, proposées dans la PR pour validation.
- `eval/run_eval.py` (hors pytest, Ollama requis) : latence p50/p95, source attendue retrouvée, éléments clés présents dans la réponse, citations valides, source attendue citée (F3). Mode `--retrieval-only` : rang des sources attendues et recall@k, sans génération.
- `tests/test_eval.py` : tests de la partie sans Ollama (corpus, éléments clés, abstention, recall@k, citations).
- Le re-ranking activé n'est pas mesurable tant que S1 n'est pas corrigé (lot 8) ; le script le signale.
- **Point ouvert — mesure de référence non produite.** Aucune mesure n'a été exécutée pendant ce lot. Elle reste à produire sur une machine disposant d'Ollama (`v1-legacy` puis branche courante, procédure dans `eval/README.md`) et à ranger dans `eval/results/v1-legacy*.json`. En attendant, les lots 6 à 9 se valident par leurs tests et leurs `xfail` (DECISIONS.md, D4).

### Lot 2 — Hygiène sans risque ✅ Fait
- Retirer `python-multipart`, `aiofiles`, `python-magic`, `libmagic1` et `poppler-utils` (D9).
- Nettoyer `.gitignore:1` ; migrer `class Config` → `model_config` ; passer `TemplateResponse(request, "index.html")`.
- Transmettre `LLM_MODEL`, `TOP_K` et `TEMPERATURE` dans `docker-compose.yml` (F9) ; tester `OLLAMA_HOST` en premier dans `entrypoint.sh` (F10).
- **S6** *(déplacé depuis le lot 9)* : un index illisible est laissé en place, l'erreur est journalisée, plus aucun `rmtree` au chargement.
- *Note de fin de lot.* Un index illisible laissé en place est remplacé par `save_local` à la prochaine indexation demandée par l'utilisateur (jamais automatiquement) ; l'état « index incompatible » arrive au lot 4b. `update_embedding_model` supprime encore l'index (F8, lot 4b) : non touché ici.

### Lot 2b — Réseau local par défaut *(nouveau, D7)* ✅ Fait
- Variable `APP_HOST` pour l'adresse d'écoute d'uvicorn. Par défaut `0.0.0.0` dans le conteneur, ce qu'exige le mode bridge, l'exposition restant limitée par le mappage `127.0.0.1:8000:8000`.
- `docker-compose.linux.yml` : `network_mode: host`, `OLLAMA_HOST=127.0.0.1:11434`, `APP_HOST=127.0.0.1`.
- Docker Desktop : comportement inchangé (bridge + `host.docker.internal`). Accès à un Ollama limité à `127.0.0.1` à vérifier sur Mac et Windows.
- Retirer le conseil `network_mode: host` du compose principal ; réécrire `README.md:221,229` et `MANAGE.md:341` ; retirer `ollama-override.conf` (SEC4).
- *Note de fin de lot.* Non vérifié : l'override Linux n'a pas été lancé de bout en bout (seul `docker compose config` a validé la fusion) ; Docker Desktop (Mac et Windows) avec un Ollama limité à `127.0.0.1` reste à tester par quelqu'un qui dispose de ces plateformes. L'override exige Docker Compose ≥ 2.24.4 (`!reset`).

### Lot 3 — Correctifs de sécurité des dépendances ✅ Fait
- pypdf 6.20.1, Pillow 12.3.0, jinja2 3.1.6, python-docx 1.2.0, psutil 7.2.2.
- *Note de fin de lot (versions revérifiées le 20/10/2026 sur PyPI et OSV).* Zéro avis OSV sur chacune de ces versions. Deux versions plus récentes existent depuis l'audit : pypdf 6.21.1 (17/10) et **Pillow 13.0.0** (16/10, majeure). Elles n'ont pas été retenues : correctifs de sécurité seulement dans ce lot, et une majeure vieille de quatre jours n'a pas sa place dans une montée « sans risque ». À reconsidérer plus tard. Vérifié : suite de tests, `pip check`, build de l'image, et dans l'image l'OCR (Pillow 12.3.0 + Tesseract) sur `eval/corpus/recette_scan.png`, la lecture d'un PDF et d'un DOCX.

### Lot 4 — FastAPI / Starlette / Uvicorn / Pydantic ✅ Fait
- fastapi 0.143.1 (starlette 1.x), uvicorn 0.54.0, pydantic 2.14.1, pydantic-settings 2.16.0.
- Image `python:3.11.17-slim-trixie` (D8).
- *Note de fin de lot (versions revérifiées le 20/10/2026 sur PyPI, OSV et Docker Hub).* 0 avis OSV sur chaque version. `starlette==1.8.0` est épinglé dans `requirements.txt` : fastapi n'exige que `starlette>=0.46`, sans cet épinglage le correctif de SEC8 ne serait pas garanti et le build ne serait pas reproductible. Plus récents que le plan : fastapi 0.151.0 (20/10) et starlette 1.9.0 (18/10), non retenus (publiés depuis quelques jours). Vérifié : tests, `pip check`, build de l'image, et dans le conteneur démarrage, `/`, `/health`, `/static/…`, `/api/files`, OCR Tesseract.
- **Hors lot, à proposer.** `starlette.testclient` signale que l'usage de `httpx` est déprécié au profit de `httpx2` : un avertissement dans les tests seulement. Le changer ajouterait une dépendance de test : à décider, non fait.

### Lot 4b — Compatibilité d'index *(nouveau, D2)* ✅ Fait
- `index_meta.json` écrit à chaque sauvegarde : version du format, modèle et dimension d'embedding, versions de `langchain-core` et `faiss-cpu`, date.
- Si le fichier est absent ou différent : l'index n'est ni chargé ni supprimé, l'état « index incompatible » est exposé par l'API et affiché dans l'interface, et les requêtes renvoient un message demandant de réindexer.
- `update_embedding_model` ne supprime plus l'index (F8) : il le rend incompatible jusqu'à la réindexation.
- README : section « Mettre à jour depuis v1-legacy » (sauvegarde conseillée du volume `family-rag-index`, réindexation).
- *Note de fin de lot.* Choix : l'égalité des versions de `langchain-core` et de `faiss-cpu` est **exacte** (D2 : « différent de ce qu'attend le code ») ; tout changement de ces paquets, y compris un patch, rend les index existants incompatibles. Le lot 5 les change donc : les index créés au lot 4b devront être reconstruits une fois de plus. Les noms de modèles sont comparés sans le tag implicite `:latest`. F8 reste ouvert pour sa seconde moitié (modèle choisi non persisté après redémarrage, lot 7b). Tests : `tests/test_index_compat.py`. Non vérifié dans un navigateur : le bandeau de l'interface (HTML Alpine) n'est couvert que par les tests de l'API qui l'alimente.

### Lot 5 — Migration LangChain 1.x
- **⛔ Prérequis bloquant : lot 4b fusionné dans `modernisation`** (DECISIONS.md, D12).
- Imports `langchain_core.documents`, `langchain_core.prompts` et `langchain_text_splitters` ; retrait de `langchain` ; langchain-community 0.4.2, langchain-ollama 1.1.0, faiss-cpu 1.15.1.
- Un index `v1-legacy` est signalé incompatible, jamais supprimé.

### Lot 6 — Corrections du splitter
- F2, F12, F13, F14. Les `xfail` correspondants du lot 1 passent au vert. Mesure via le lot 1b.

### Lot 7 — Justesse de la recherche et de la génération *(sans réindexation)*
- Chaque extrait est préfixé par `[source]` (F3) ; filtre FAISS natif `filter=` + `fetch_k=` (F5) ; une seule échelle de score, et la « confiance » de l'interface alignée dessus (F6).
- **`NUM_CTX`** (D3) : variable d'environnement, défaut documenté (4096 proposé), transmise à `ChatOllama`. Le budget de contexte est calculé depuis cette valeur ; les extraits en trop sont écartés au lieu d'être tronqués par Ollama (F4).
- Mesure via le lot 1b.

### Lot 7b — Réglages persistants *(nouveau, D6)*
- `settings.json` dans le volume `/app/index`, écrit de façon atomique. `.env` fournit les défauts ; l'interface l'emporte ; supprimer le fichier ramène au `.env`.
- Réglages : modèle LLM, modèle d'embedding, température, `top_k`, re-ranking. `NUM_CTX` reste une variable d'environnement.

### Lot 8 — Re-ranking maîtrisé
- `RERANKING_ENABLED=false` par défaut, interrupteur dans les réglages (persisté via 7b).
- Vrai timeout (côté `ChatOllama`/httpx), plafond de candidats, timeout sur la génération (S1, S3, P1).
- Mesure via le lot 1b, avec et sans re-ranking, au regard du budget en tokens de prompt (D4, révisé ; le temps mesuré reste indicatif).

### Lot 9 — Index incrémental et robuste
- Indexation **incrémentale** : cocher des fichiers les ajoute ou remplace leurs chunks, sans jamais effacer le reste (F1, D1) ; suppression des fichiers disparus.
- **F7** *(déplacé depuis le lot 11)* : `source` = chemin relatif, y compris dans le front (`selectedSources` par `file.path`). Indispensable au remplacement par source.
- Indexation hors event loop, sous verrou (S2, S4) ; sauvegarde atomique (S5) ; ré-embedding limité aux fichiers modifiés (P2).

### Lot 10 — Durcissement
- Bornes Pydantic sur `top_k`, `temperature` et `image_data` ; `TrustedHostMiddleware` contre le DNS rebinding, même en accès strictement local (SEC3, SEC5).
- Utilisateur non root, `/data:ro` (SEC7) ; messages d'erreur génériques (SEC9) ; détection vision asynchrone (S7) ; liste unique des modèles d'embedding (F11) ; codes HTTP cohérents (F20).

### Lot 11 — Ingestion
- E-mails HTML et charsets inconnus (F15), tableaux DOCX (F16), dates normalisées et classification (F17), journalisation et factorisation de `load_all`/`load_specific` (F18).
- **F23** *(repéré au lot 1)* : décoder l'en-tête `Subject` encodé (RFC 2047). **F24** *(repéré au lot 1, gravité Haute)* : détection d'encodage des fichiers texte (essayer UTF-8 strict avant `chardet`). Les deux `xfail` du lot 1 passent alors au vert.
- OCR de repli pour les PDF scannés : **décrit comme option, non implémenté** (D9).

### Lot 12 — Finitions *(optionnel)*
- README (badges, versions, Ollama minimal, ordre de priorité des réglages), progression réelle de l'indexation, Alpine 3.17.4, CSS Tailwind précompilé.
- Section « Évolutions futures » : historique des conversations (D11), OCR des PDF scannés (D9).

---

## 7. Questions avant de commencer

> **Répondues le 15/10/2026.** Les réponses et leur impact sur le plan sont consignés dans [DECISIONS.md](DECISIONS.md). Les questions sont conservées ci-dessous pour mémoire.

1. **Indexation sélective** : quand vous cochez quelques fichiers, voulez-vous **ajouter** ces fichiers à l'index existant (mon hypothèse, F1), ou bien remplacer l'index par ce sous-ensemble ?
2. **Réindexation** : quelle taille fait votre corpus (nombre de fichiers, volume, part d'images ou de scans) ? Une réindexation complète est-elle acceptable plusieurs fois, ou faut-il regrouper les lots 5, 6, 7 et 9 pour n'en faire qu'une ?
3. **Matériel et modèles** : quelle machine (RAM/VRAM, Apple Silicon ?), quelle version d'Ollama, et quels modèles utilisez-vous réellement (LLM, embedding, vision) ? Cela fixe `num_ctx` (F4) et le budget de re-ranking.
4. **Qualité contre latence** : quel temps de réponse jugez-vous acceptable ? Le re-ranking LLM doit-il rester activé par défaut ? Avez-vous 10 à 20 questions de référence, avec leurs réponses attendues, pour mesurer l'effet des changements (préfixes Nomic, re-ranking, splitter) ?
5. **Noms de fichiers en double** dans des sous-dossiers différents : est-ce le cas chez vous ? Si oui, `source` devient le chemin relatif (F7), ce qui change l'affichage.
6. **Persistance des réglages** (modèle LLM, embedding, température, top_k choisis dans l'interface) : doivent-ils survivre à un redémarrage ?
7. **Accès réseau** : l'application doit-elle rester strictement locale (`127.0.0.1`), ou être consultée depuis d'autres appareils de la maison ? Dans le second cas, il faut une authentification, ce qui change le lot 10. Et Ollama doit-il vraiment écouter sur `0.0.0.0` (SEC4) ?
8. **Version de Python** : rester en 3.11 jusqu'en 2027 (ma recommandation), ou passer dès maintenant en 3.12 ou 3.13 ?
9. **PDF scannés** : en avez-vous ? L'OCR de repli ajoute une dépendance (`pdf2image` ou équivalent) et allonge fortement l'indexation.
10. **Méthode de travail** : un commit par lot sur `modernisation`, avec ou sans PR par lot ? Souhaitez-vous une CI (GitHub Actions) qui lance les tests ?
11. **Conversations** : l'historique doit-il être envoyé au LLM pour permettre les questions de suivi (F22) ? C'est une fonctionnalité nouvelle, hors du périmètre « stabilité » ; je ne la ferais que sur demande.
12. **Sauvegarde** : avez-vous une copie du volume `family-rag-index` et de vos réglages avant que je touche à l'index ?
