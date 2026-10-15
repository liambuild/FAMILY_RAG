# Décisions de modernisation — 15 octobre 2026

Ce fichier consigne les réponses aux questions de la section 7 de [AUDIT.md](AUDIT.md) et leur impact sur le plan en lots. Le plan révisé complet se trouve en section 6 de l'audit.

## Contexte

- FamilyRAG est un **projet open source public**. L'objectif est un code fiable, à jour et **sûr par défaut** pour ses utilisateurs, sous Linux comme sous Docker Desktop (Mac/Windows). Le mainteneur ne déploie pas lui-même l'application.
- Point de départ : le tag **`v1-legacy`** (commit `97db240`), qui est l'état audité.
- Les utilisateurs existants ont un index construit par `v1-legacy`. C'est la contrainte de compatibilité qui structure le plan (D2).

## Synthèse

| # | Sujet | Décision | Impact sur le plan |
|---|---|---|---|
| D1 | Indexation sélective | Ajoute ou remplace, n'efface jamais le reste | Lot 9 confirmé ; F7 y est rapatrié (C2) |
| D2 | Index existants des utilisateurs | Jamais de suppression automatique ; détection d'incompatibilité ; doc de migration | **Lot 4b ajouté** ; S6 avancé au lot 2 (C3) ; regroupement des réindexations **supprimé** |
| D3 | Matériel de référence | Aucun : `NUM_CTX` configurable, budget de contexte calculé | Lot 7 modifié |
| D4 | Qualité contre latence | Re-ranking désactivé par défaut, activable ; mesure reproductible | **Lot 1b ajouté** (C4) ; lot 8 modifié |
| D5 | Fichiers homonymes | `source` = chemin relatif | F7 déplacé du lot 11 au lot 9 (C2) |
| D6 | Persistance des réglages | Persistés, l'interface l'emporte sur `.env` | **Lot 7b ajouté** |
| D7 | Réseau | Local par défaut ; override Linux en mode host sur 127.0.0.1 | **Lot 2b ajouté** ; SEC13 ajouté à l'audit |
| D8 | Python | 3.11, image épinglée au patch | Lot 4 confirmé |
| D9 | PDF scannés | Pas d'OCR de repli ; option documentée seulement | Lot 11 réduit |
| D10 | Méthode | Une branche et une PR par lot vers `modernisation`, pas de CI | Règle commune à tous les lots |
| D11 | Historique des conversations | Hors périmètre, évolution future | Aucun lot ; noté en fin de fichier |
| D12 | Sauvegarde | Remplacée par la protection des index existants | Prérequis bloquant du lot 5 redéfini |

Corrections de l'audit acceptées : **C2** (F7 au lot 9), **C3** (S6 au lot 2 ; le lot 7 n'impose pas de réindexation), **C4** (lot 1b de mesure), **C7** (sauvegarde), toutes adaptées au contexte open source.

---

## D1 — Indexation sélective : ajouter, jamais effacer

**Décision.** Cocher des fichiers les **ajoute** à l'index existant, ou **remplace** leurs chunks s'ils étaient déjà indexés. Le reste de l'index n'est jamais touché.

**Impact sur le plan.**
- **Lot 9** : indexation incrémentale par source (`delete` des chunks de la source, puis `add_documents`). C'est la correction de F1, le seul constat critique de l'audit.
- **Lot 9** : reçoit aussi F7, le passage au chemin relatif (voir C2 / D5). Il est indispensable : sans lui, remplacer `docs/facture.pdf` effacerait aussi `autres/facture.pdf`.
- **Lot 1** : un test de caractérisation fige le comportement actuel (remplacement complet), et un test `xfail(strict=True)` décrit le comportement voulu.

## D2 — Index des utilisateurs existants (remplace l'ancienne Q2 sur le corpus réel)

**Décision.** Il n'y a pas de « corpus réel » côté mainteneur. La contrainte porte sur l'index de chaque utilisateur, construit par `v1-legacy` :
- **ne jamais le supprimer automatiquement** ;
- **détecter un index incompatible**, c'est-à-dire un `index_meta.json` absent ou différent de ce qu'attend le code ;
- **afficher un message clair** qui demande une réindexation ;
- **documenter la migration** dans le README, section « Mettre à jour depuis v1-legacy ».

Le regroupement des réindexations n'a plus d'objet : chaque lot réindexe librement le corpus de test.

**Impact sur le plan.**
- **Lot 2** : S6 corrigé (C3). Un index illisible est laissé en place et l'erreur est journalisée, plus aucun `rmtree`. Le comportement de `update_embedding_model` qui supprime l'index est neutralisé au lot 4b.
- **Lot 4b (nouveau, « Compatibilité d'index »)**, placé avant la migration LangChain :
  - `index_meta.json` écrit à chaque sauvegarde : version du format, modèle et dimension d'embedding, versions de `langchain-core` et `faiss-cpu`, date ;
  - au démarrage, si le fichier est absent ou différent, l'index n'est **ni chargé ni supprimé**, l'état « index incompatible, réindexez » est exposé par `/api/stats` et affiché dans l'interface, et les requêtes renvoient un message explicite au lieu d'une erreur ;
  - un changement de modèle d'embedding ne supprime plus l'index : il le rend incompatible (même message) jusqu'à la réindexation ;
  - README, section « Mettre à jour depuis v1-legacy » : pourquoi réindexer, sauvegarde conseillée du volume `family-rag-index`, étapes.
- Tout index `v1-legacy` (sans `index_meta.json`) sera déclaré incompatible. C'est voulu : la migration LangChain du lot 5 ne garantit pas la relecture du pickle.
- **Regroupement des réindexations : supprimé.**

## D3 — Pas de matériel de référence : `NUM_CTX` configurable

**Décision.** La fenêtre de contexte devient une variable d'environnement, avec une valeur par défaut documentée. Le budget de contexte (nombre et taille des extraits envoyés) se calcule à partir de cette valeur.

**Impact sur le plan.**
- **Lot 7** :
  - variable `NUM_CTX` transmise à `ChatOllama(num_ctx=...)`, et documentée dans `.env.example`, `docker-compose.yml` et le README ;
  - valeur par défaut proposée : **4096**, le défaut documenté par Ollama sous 24 Go de VRAM, donc sans hausse de mémoire pour les petites machines ;
  - budget = `NUM_CTX` moins une réserve pour le prompt système et la question, moins une réserve pour la réponse, converti en caractères par un ratio prudent. Les extraits en trop sont écartés, plutôt que de laisser Ollama tronquer sans le dire (F4).
- La valeur par défaut exacte sera validée avec le lot 1b sur au moins une machine.

## D4 — Qualité contre latence : re-ranking désactivé par défaut

**Décision.** ~~Objectif indicatif : une réponse en moins de 15 s.~~ *(révisé pendant le lot 1b)* L'objectif devient un **budget en tokens de prompt** par question, indépendant de la machine ; le temps de réponse mesuré est **seulement indicatif**. Sur la VM de mesure (3 cœurs, CPU seul, `gemma3:4b`), le traitement du prompt tourne autour de 9 tokens/s et domine la latence (une réponse dure de 10 s à plus de 150 s selon la taille du prompt) : un seuil en secondes n'a donc de sens que pour une machine donnée. Le script de mesure enregistre pour chaque question `prompt_eval_count`, `prompt_eval_duration` et `eval_duration` (renvoyés par Ollama), en plus du temps total. La valeur du budget sera fixée au lot 7, avec `NUM_CTX` (D3), à partir de ces mesures. Le re-ranking est **désactivé par défaut** et activable dans les réglages. La mesure de qualité doit être reproductible par quiconque dispose d'Ollama.

**Impact sur le plan.**
- **Lot 1b (nouveau, « Mesure de qualité »)**, placé après le lot 1 (correction C4) :
  - corpus de test fictif versionné dans `eval/corpus/` : PDF texte, DOCX avec tableau, e-mail `.eml`, image pour l'OCR, Markdown avec listes et tableau, et deux `facture.pdf` homonymes dans deux sous-dossiers ;
  - `eval/questions.yaml` : **15 questions**, chacune avec sa réponse attendue et sa ou ses sources attendues. Elles seront proposées dans la PR du lot 1b, pour validation ;
  - `eval/run_eval.py`, hors pytest et nécessitant Ollama : latence (p50/p95), source attendue retrouvée, éléments clés présents dans la réponse, citations valides ;
  - **mesure de référence** sur `v1-legacy`, enregistrée avec la machine et les modèles utilisés, puis nouvelle mesure après les lots 6, 7 et 8.
- **Lot 8** : `RERANKING_ENABLED=false` par défaut ; interrupteur dans les réglages (persisté via le lot 7b) ; vrai timeout ; plafond de candidats ; mesure avec et sans re-ranking.

## D5 — Fichiers homonymes : `source` = chemin relatif

**Décision.** `source` devient le chemin relatif à `/data` (par exemple `docs/facture.pdf`).

**Impact sur le plan.**
- **F7 déplacé du lot 11 au lot 9** (C2), avec le front : `selectedSources` utilise `file.path` au lieu de `file.name`.
- Les index `v1-legacy` utilisent des noms simples : ils sont déjà couverts par la détection d'incompatibilité (D2).

## D6 — Réglages persistants : l'interface l'emporte

**Décision.** `.env` fournit les valeurs par défaut. Les réglages faits dans l'interface sont **persistés** et **l'emportent**. Supprimer le fichier de réglages ramène aux valeurs du `.env`.

**Impact sur le plan.**
- **Lot 7b (nouveau, « Réglages persistants »)** :
  - fichier `settings.json` dans le volume `/app/index`, écrit de façon atomique ;
  - réglages concernés : modèle LLM, modèle d'embedding, température, `top_k`, re-ranking ;
  - `NUM_CTX` reste une variable d'environnement (D3) ;
  - le changement de modèle d'embedding passe par la détection d'incompatibilité du lot 4b ;
  - placé avant le lot 8 pour que l'interrupteur de re-ranking soit persisté dès son ajout.
- **Lot 2** : la transmission de `LLM_MODEL`, `TOP_K` et `TEMPERATURE` par `docker-compose.yml` (F9) reste nécessaire, car `.env` fournit les valeurs par défaut.
- Documentation : le README décrit l'ordre de priorité et la remise à zéro.

## D7 — Réseau : local par défaut, Linux et Docker Desktop

**Décision.** Option 1 de la discussion, adaptée :
- **Docker Desktop** (Mac/Windows) : comportement par défaut **inchangé** (mode bridge avec `host.docker.internal`, port lié à `127.0.0.1`).
- **Linux** : un override **`docker-compose.linux.yml`** passe en `network_mode: host`, avec uvicorn **et** Ollama sur `127.0.0.1`.
- L'adresse d'écoute d'uvicorn devient **configurable** par variable d'environnement.
- Le conseil d'activer `network_mode: host` est **retiré** du compose principal.
- SEC13 est conservé dans l'audit.

**Raison technique (déjà signalée).** Sous Linux en mode bridge, `host.docker.internal` pointe vers l'interface docker0. Un Ollama qui n'écoute que sur `127.0.0.1` y est injoignable, d'où le mode host pour l'override Linux. Sous Docker Desktop, joindre un Ollama limité à `127.0.0.1` via `host.docker.internal` fonctionne généralement, mais n'est **pas vérifié** : voir les points ouverts.

**Impact sur le plan.**
- **Lot 2b (nouveau, « Réseau local par défaut »)**, placé tôt car il corrige un défaut de sécurité documenté :
  - variable `APP_HOST`, transmise à uvicorn par l'entrypoint. Par défaut `0.0.0.0` *dans le conteneur*, ce qui est nécessaire en mode bridge : l'exposition reste limitée par le mappage `127.0.0.1:8000:8000`. L'override Linux la fixe à `127.0.0.1` ;
  - `docker-compose.linux.yml` : `network_mode: host`, `OLLAMA_HOST=127.0.0.1:11434`, `APP_HOST=127.0.0.1` ;
  - `docker-compose.yml` : retrait des commentaires `network_mode: host` (lignes 5-7 et 15) ;
  - `README.md:221,229` et `MANAGE.md:341` réécrits ; documentation de `docker compose -f docker-compose.yml -f docker-compose.linux.yml up` ;
  - `ollama-override.conf` (qui force `0.0.0.0`) retiré, puisqu'Ollama écoute sur `127.0.0.1` par défaut. Corrige SEC4 ;
  - la doc avertit qu'un `docker run -p 8000:8000` lancé hors compose expose l'application sur toutes les interfaces.
- **Lot 10** : `TrustedHostMiddleware` reste nécessaire. L'accès strictement local ne protège pas du DNS rebinding (SEC3).

## D8 — Python 3.11, image épinglée au patch

**Décision.** On reste en Python 3.11, avec une image épinglée au patch.

**Impact sur le plan.** **Lot 4** : `FROM python:3.11.17-slim-trixie`. Il faudra planifier une montée de version avant la fin de vie de la 3.11 (2027-10-31), hors de ce plan.

## D9 — PDF scannés : pas d'OCR de repli

**Décision.** L'OCR des PDF scannés reste une option du lot 11, documentée mais **non implémentée**.

**Impact sur le plan.**
- **Lot 11** : ne reçoit plus que F15, F16 (tableaux DOCX), F17, F18 et la factorisation du loader ; F7 est parti au lot 9. L'OCR de repli y est décrit comme option (dépendance nécessaire, coût d'indexation) sans code.
- **Lot 2** : `poppler-utils` est retiré du Dockerfile. Il sera réintroduit si l'option est un jour retenue.

## D10 — Méthode : une branche et une PR par lot

**Décision.** Chaque lot a sa branche, créée depuis `modernisation` à jour, et sa PR vers `modernisation`. Pas de CI pour l'instant.

**Impact sur le plan.**
- Nommage (aligné sur CLAUDE.md) : `lot-1`, `lot-1b`, `lot-2`, `lot-2b`, et ainsi de suite (voir AUDIT.md §6).
- Les lots s'enchaînent : chaque branche part de `modernisation` **après** la fusion de la précédente.
- Sans CI, chaque PR cite la commande de test lancée et son résultat. Les lots 6, 7 et 8 citent aussi le résultat de `eval/run_eval.py`.

## D11 — Historique des conversations : hors périmètre

**Décision.** Ce n'est pas implémenté. C'est noté comme évolution future (voir plus bas).

**Impact sur le plan.** Aucun lot. Le constat F22 de l'audit reste « Info ».

## D12 — Sauvegarde : remplacée par la protection des index existants

**Décision initiale.** Une sauvegarde devait être faite avant le lot 5, comme prérequis bloquant.

**Décision révisée** (contexte open source, correction C7 adaptée). Il n'y a pas d'index réel à sauvegarder côté mainteneur. La protection porte sur les index des utilisateurs, via D2.

### ⛔ Prérequis bloquant du lot 5 (migration LangChain)

Le lot 5 ne commence pas tant que **le lot 4b n'est pas fusionné dans `modernisation`**, c'est-à-dire :
1. aucune suppression automatique d'index (lot 2) ;
2. `index_meta.json` écrit et vérifié, index incompatible signalé sans être supprimé (lot 4b) ;
3. section README « Mettre à jour depuis v1-legacy » publiée, qui **conseille aux utilisateurs de sauvegarder le volume `family-rag-index`** avant de mettre à jour (lot 4b).

---

## Points ouverts

| Sujet | À trancher dans | Détail |
|---|---|---|
| Docker Desktop et Ollama sur `127.0.0.1` | Lot 2b | À vérifier sur Mac **et** Windows (je n'ai que Linux). Si cela échoue, documenter l'alternative pour ces plateformes. |
| Valeur par défaut de `NUM_CTX` | Lot 7 | 4096 proposé ; à confirmer par une mesure du lot 1b. |
| 15 questions de référence | Lot 1b | Proposées dans la PR, à valider. |
| Budget en tokens de prompt (remplace le seuil de 15 s) | Lots 7 et 8 | Valeur à fixer d'après les champs `prompt_eval_*` du lot 1b ; le temps mesuré reste indicatif. |

## Évolutions futures (hors plan)

- **Historique des conversations envoyé au LLM** (D11, constat F22) : permettrait les questions de suivi.
- **OCR de repli pour les PDF scannés** (D9) : nécessite une dépendance de rendu PDF en image et allonge l'indexation.
- **Montée de version Python** au-delà de 3.11, avant 2027-10-31 (D8).
