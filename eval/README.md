# Mesure de qualité (lot 1b)

Mesure reproductible de la qualité et de la latence du RAG, pour comparer le code avant/après un changement (re-ranking, splitter, préfixes d'embedding…). Ce dossier n'est pas une suite de tests : il nécessite Ollama et n'est jamais collecté par `pytest`.

## Contenu
- `corpus/` : documents fictifs de la famille « Martin » (PDF, DOCX avec tableau, `.eml`, image pour l'OCR, Markdown, deux `facture.pdf` homonymes). Régénérable avec `python eval/build_corpus.py`.
- `questions.yaml` : 15 questions, chacune avec réponse attendue, éléments clés et source(s) attendue(s). Les questions marquées `known_gap` correspondent à un défaut connu de l'audit (F16, F23, F24) ; leur échec n'est pas une régression.
- `run_eval.py` : le script de mesure.
- `results/` : mesures. Seules celles de référence (`v1-legacy*.json`) sont versionnées.

## Prérequis
- Ollama qui répond, avec le modèle d'embedding et un modèle de chat installés (`ollama pull <modele>`).
- Les dépendances de l'application (`app/requirements.txt`) ; PyYAML est fourni par LangChain.
- `tesseract` pour la question 7 (OCR) ; sans lui, elle est ignorée et signalée.

## Utilisation
```bash
python eval/run_eval.py --label lot-1b --llm gemma3:4b            # re-ranking désactivé
python eval/run_eval.py --label lot-1b --rerank both              # avec et sans re-ranking (long sur CPU)
python eval/run_eval.py --only 1 10                               # quelques questions seulement
python eval/run_eval.py --compare eval/results/a.json eval/results/b.json
```
Mesurer un autre code (par exemple le tag `v1-legacy`) :
```bash
git worktree add /tmp/v1-legacy v1-legacy
python eval/run_eval.py --label v1-legacy --app-dir /tmp/v1-legacy/app
```
Le fichier de sortie (`eval/results/<label>.json`) contient `meta` (commit, machine, versions Ollama et modèles, paramètres), les résultats par question et un `summary` par mode de re-ranking.

## Lecture
- `latency_*` : secondes par question, modèle déjà chargé (le chargement est mesuré à part, `warmup_s`).
- `source_found` : la ou les sources attendues figurent parmi les extraits retrouvés.
- `key_elements_complete` : tous les éléments clés sont dans la réponse (insensible à la casse et aux accents).
- `answers_with_citation` / `citations_valid` : réponses qui citent un fichier / fichiers cités qui font bien partie des extraits retrouvés. Heuristique sur les noms de fichiers.
- `good_abstentions` : à la question absente du corpus, le modèle avoue ne pas savoir (détection par formules). Lisez aussi les réponses dans le JSON.

La variabilité d'un run à l'autre est réelle (température du LLM) : comparez des ordres de grandeur, ou répétez la mesure.
