# Mesure de qualité (lot 1b)

Mesure reproductible de la qualité et de la latence du RAG, pour comparer le code avant/après un changement (re-ranking, splitter, préfixes d'embedding…). Ce dossier n'est pas une suite de tests : il nécessite Ollama et n'est jamais collecté par `pytest`. Les parties qui n'en ont pas besoin (construction du corpus, notation, recall@k) sont testées dans `tests/test_eval.py`.

## Contenu
- `corpus/` : documents fictifs de la famille « Martin » (PDF, DOCX avec tableau, `.eml`, image pour l'OCR, Markdown, deux `facture.pdf` homonymes) et un dossier `distracteurs/` de 48 petites notes sans rapport avec les questions. Les distracteurs portent l'index à plus de 4 × `top_k` extraits : sans eux, la recherche renverrait presque tout et ne mesurerait rien. Régénérable avec `python eval/build_corpus.py`.
- `questions.yaml` : 15 questions, chacune avec réponse attendue, éléments clés et source(s) attendue(s). Les questions marquées `known_gap` correspondent à un défaut connu de l'audit (F16, F23, F24) ; leur échec n'est pas une régression.
- `run_eval.py` : le script de mesure.
- `results/` : mesures. Seules celles de référence (`v1-legacy*.json`) sont versionnées.

## Prérequis
- Ollama qui répond, avec le modèle d'embedding et un modèle de chat installés :
  ```bash
  ollama pull nomic-embed-text   # embedding (défaut de l'application)
  ollama pull gemma3:4b          # chat (n'importe quel modèle de chat convient : --llm <modele>)
  ```
  Le mode `--retrieval-only` n'a besoin que du modèle d'embedding.
- Les dépendances de l'application (`app/requirements.txt`) ; PyYAML est fourni par LangChain.
- `tesseract` pour la question 7 (OCR) ; sans lui, elle est ignorée et signalée.

## Produire la mesure de référence
À faire sur une machine disposant d'Ollama, avec les **mêmes modèles et le même `--top-k`** pour les deux mesures. Le re-ranking reste désactivé (voir plus bas).

1. Mesurer `v1-legacy`, le code d'avant la modernisation, dans un worktree :
   ```bash
   git worktree add ../v1-legacy-worktree v1-legacy
   python eval/run_eval.py --label v1-legacy --llm gemma3:4b --app-dir ../v1-legacy-worktree/app
   python eval/run_eval.py --label v1-legacy-retrieval --retrieval-only --app-dir ../v1-legacy-worktree/app
   ```
2. Mesurer la branche courante :
   ```bash
   python eval/run_eval.py --label lot-N --llm gemma3:4b
   python eval/run_eval.py --label lot-N-retrieval --retrieval-only
   ```
3. Comparer :
   ```bash
   python eval/run_eval.py --compare eval/results/v1-legacy.json eval/results/lot-N.json
   ```

**Où ranger les résultats.** Le script écrit `eval/results/<label>.json`. Les fichiers `v1-legacy*.json` sont les mesures de référence : ils sont versionnés (committez-les, par exemple dans une PR dédiée). Les autres mesures (`lot-*.json`, etc.) sont ignorées par git. Chaque fichier enregistre dans `meta` le commit, la machine, les versions d'Ollama et des modèles et les paramètres : relevez-les avant de comparer deux mesures.

## Utilisation
```bash
python eval/run_eval.py --label essai --llm gemma3:4b             # génération complète, re-ranking désactivé
python eval/run_eval.py --label essai --retrieval-only            # recherche seule : rang des sources, recall@k
python eval/run_eval.py --retrieval-only --top-k 5                # autre nombre d'extraits
python eval/run_eval.py --only 1 10                               # quelques questions seulement
python eval/run_eval.py --compare eval/results/a.json eval/results/b.json
```
Le fichier de sortie contient `meta`, les résultats par question et un `summary` par mode (`rerank_off`, `rerank_on`, `retrieval`).

## Re-ranking
`--rerank on|both` reste disponible, mais le résultat n'est **pas exploitable tant que S1 n'est pas corrigé** (AUDIT.md, lot 8) : le timeout du re-ranking est inopérant, et une question peut durer sans limite, voire bloquer. Le script le signale au lancement. Mesurer uniquement `--rerank off` (le défaut) jusqu'au lot 8.

## Lecture
- `latency_*` : secondes par question, modèle déjà chargé (le chargement est mesuré à part, `warmup_s`). Indicatif : il dépend de la machine.
- `source_found` : la ou les sources attendues figurent parmi les extraits retrouvés.
- `recall_at_k` (mode `--retrieval-only`) : part des sources attendues retrouvées parmi les `top_k` extraits, moyennée sur les questions qui en attendent. Une question multi-sources (Q14) compte 0,5 si une seule est retrouvée.
- `key_elements_complete` : tous les éléments clés sont dans la réponse (insensible à la casse et aux accents ; une sous-liste donne des variantes équivalentes).
- `answers_with_citation` / `citations_valid` : réponses qui citent un fichier / fichiers cités qui font bien partie des extraits retrouvés. Heuristique sur les noms de fichiers.
- `cites_expected_source` (F3) : la réponse cite au moins une des sources attendues. Sous `v1-legacy`, qui ne connaît que des noms de fichiers, la comparaison se fait sur le nom de base.
- `good_abstentions` : à la question absente du corpus (Q15), le modèle avoue ne pas savoir. C'est une détection par formules d'ignorance (« je ne sais pas », « pas mentionné »…) dans la réponse normalisée ; lisez aussi les réponses dans le JSON.

La variabilité d'un run à l'autre est réelle (température du LLM) : comparez des ordres de grandeur, ou répétez la mesure.
