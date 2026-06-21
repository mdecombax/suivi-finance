# Import d'ordres par IA — sur Vertex AI

Extraction d'ordres d'achat (ETF/actions/fonds) depuis des documents hétérogènes
(CSV, captures d'écran, PDF de relevés) vers des transactions structurées, prêtes
à être enregistrées dans le portefeuille.

Ce document décrit la version **Vertex AI** : pourquoi Vertex, l'architecture, les
décisions techniques, et surtout **les résultats mesurés** qui justifient ces
choix par des chiffres.

---

## 1. Problème

Un utilisateur veut importer son historique d'achats depuis son courtier. Les
sources sont hétérogènes : export CSV propre, **capture d'écran** d'appli mobile,
**PDF** de relevé scanné. Il faut :

- ne garder que les **achats** (exclure dividendes, ventes, virements, frais) ;
- normaliser dates et montants ;
- **compléter l'ISIN** quand il est absent (cas fréquent des screenshots), à
  partir du seul nom du fonds — souvent abrégé, réordonné ou en français.

## 2. Pourquoi Vertex AI

| Besoin | Réponse Vertex | Bénéfice |
|---|---|---|
| Sécurité prod | Auth **ADC / IAM** (compte de service, `roles/aiplatform.user`) | Zéro clé API à stocker/rotationner |
| Fiabilité du format | **Génération contrôlée** (`response_schema` Pydantic) | JSON conforme garanti par la plateforme, pas de prompt « réponds en JSON » |
| Documents | **PDF natif** (Gemini ingère le PDF brut) | Pas de rasterisation, texte vectoriel préservé, moins de tokens |
| Résolution sémantique | **Embeddings** `text-multilingual-embedding-002` | Noms approximatifs / multilingues |
| Mesure | Harness d'éval maison (cf. §5) | Choix de modèle justifié par des métriques |
| Cohérence infra | Même projet GCP que Cloud Run (`suivi-finance-472610`, `europe-west1`) | Résidence des données UE, un seul périmètre |

## 3. Architecture

```
                  ┌────────────────────────────────────────────┐
  Document  ──►   │  _build_parts()                            │
 (CSV/IMG/PDF)    │   • CSV/texte → texte                      │
                  │   • image → bytes                          │
                  │   • PDF → bytes natifs (Gemini) ┐          │
                  │           ou rasterisation PNG  │ (autres) │
                  └───────────────┬────────────────┘──────────┘
                                  ▼
        ┌─────────────────────────────────────────────────────┐
        │  Registre multi-fournisseur (MODEL_REGISTRY)         │
        │  • vertex  : Gemini 2.5 Flash / Pro   ← citoyen 1re classe
        │  • anthropic : Claude                                │
        │  • openai_compatible : Qwen / GPT / MiniMax / DeepSeek
        └───────────────┬─────────────────────────────────────┘
                        ▼  génération contrôlée (response_schema = ImportResult)
                 ImportResult { orders[], declared_total_eur, currency_warning }
                        ▼
        ┌─────────────────────────────────────────────────────┐
        │  _postprocess()                                      │
        │   • filtre : achats uniquement                       │
        │   • résolution ISIN : resolve_isin()                 │
        │       tfidf | embeddings | hybrid (cost-aware)       │
        └─────────────────────────────────────────────────────┘
```

Ajouter un modèle = une entrée dans `MODEL_REGISTRY`. Les fournisseurs sont
interchangeables, ce qui permet de **tous les comparer sur le même golden set**.

## 4. Décisions techniques notables

- **Auth sans clé.** En local : `gcloud auth application-default login`. En prod :
  le compte de service Cloud Run reçoit `roles/aiplatform.user`. Aucune clé dans
  le code ni dans Secret Manager pour Vertex.
- **`temperature=0`** pour une extraction déterministe.
- **Résolution ISIN hybride et *cost-aware*** : on tente d'abord le TF-IDF
  (local, gratuit) ; on n'appelle l'embedding Vertex (payant) **que** si le
  TF-IDF n'est pas assez confiant (score < `ISIN_HYBRID_TRUST`). L'index des 141
  noms est pré-calculé une fois et mis en cache.

## 5. Résultats mesurés

### 5.1 Comparatif de modèles (golden set : 5 documents CSV+PDF, 10 ordres)

| Modèle | F1 | Précision | Rappel | ISIN exact | Latence p50 | p95 | Coût/doc (est.) |
|---|---|---|---|---|---|---|---|
| **gemini-2.5-flash** | 1.00 | 1.00 | 1.00 | 90 % | ~6 s | ~8 s | **$0.0004** |
| gemini-2.5-pro | 1.00 | 1.00 | 1.00 | 90 % | ~20 s | ~27 s | $0.0015 |

> **Conclusion** : Flash égale Pro en qualité sur cette tâche, pour **~4× moins
> cher et ~3× plus rapide**. → On recommande **Flash** par défaut, et on garde Pro
> en repli pour les documents difficiles signalés par une `confidence` basse.

Reproduire : `./venv/bin/python -m evaluation.run_eval --models gemini-2.5-flash,gemini-2.5-pro`

### 5.2 Résolution ISIN — TF-IDF vs embeddings vs hybrid (10 noms bruités)

| Stratégie | Exactitude |
|---|---|
| tfidf | 80 % |
| embeddings | 80 % |
| **hybrid (confiance)** | **90 %** |

> **Ce que la mesure a révélé** : un `hybrid` naïf (« TF-IDF sinon embeddings »)
> n'améliorait rien, car le TF-IDF renvoyait parfois une réponse *fausse mais
> confiante* — le repli ne se déclenchait jamais. En **routant selon la confiance**
> du TF-IDF, le hybrid récupère le cas multilingue (« Vanguard S&P 500
> *distribuant* ») que seuls les embeddings résolvent, sans régresser ailleurs —
> tout en n'appelant la sémantique payante que sur 2 requêtes sur 10.
>
> Limite restante : la désambiguïsation fine de **classe de part** (acc vs dist)
> n'est bien tranchée par aucune des deux approches → *next step* : re-ranking par
> classe de part sur les candidats sémantiques.

Reproduire : `./venv/bin/python -m evaluation.bench_isin`

## 6. Coûts

Tout est facturé à l'usage (tokens). Ordres de grandeur :

- **Génération** : Flash ≈ $0.0004/doc, Pro ≈ $0.0015/doc.
- **Embeddings** : index des 141 noms = one-time, fraction de centime ; requête =
  ~10 tokens, ~100× moins cher que la génération.
- Garde-fous : `MAX_FILE_SIZE` (10 Mo), `MAX_PDF_PAGES` (15), caches (`lru_cache`),
  seuils de similarité, et **hybrid cost-aware** qui évite l'embedding quand le
  TF-IDF suffit.

## 7. Mise en route

```bash
# 1. Auth Vertex (une fois)
gcloud services enable aiplatform.googleapis.com --project=suivi-finance-472610
gcloud auth application-default login
gcloud auth application-default set-quota-project suivi-finance-472610

# 2. Variables (.env local)
#   GOOGLE_CLOUD_PROJECT=suivi-finance-472610
#   VERTEX_LOCATION=europe-west1
#   IMPORT_MODEL=gemini-2.5-flash
#   ISIN_RESOLVER=hybrid        # tfidf (défaut) | embeddings | hybrid

# 3. Index d'embeddings (si ISIN_RESOLVER != tfidf)
GOOGLE_CLOUD_PROJECT=suivi-finance-472610 ./venv/bin/python -m scripts.build_isin_embeddings

# 4. Évaluations
./venv/bin/python -m evaluation.build_golden
GOOGLE_CLOUD_PROJECT=suivi-finance-472610 ./venv/bin/python -m evaluation.run_eval --models gemini-2.5-flash,gemini-2.5-pro
GOOGLE_CLOUD_PROJECT=suivi-finance-472610 ./venv/bin/python -m evaluation.bench_isin

# Prod (Cloud Run) : autoriser le compte de service, sans clé
gcloud projects add-iam-policy-binding suivi-finance-472610 \
  --member="serviceAccount:969609849752-compute@developer.gserviceaccount.com" \
  --role="roles/aiplatform.user"
```

## 8. Fichiers

| Fichier | Rôle |
|---|---|
| `services/import_service.py` | Pipeline : parts → modèle → post-traitement ; providers ; résolution ISIN |
| `scripts/build_isin_embeddings.py` | Pré-calcul de l'index d'embeddings (one-time) |
| `evaluation/build_golden.py` | Génère le golden set (docs + labels) |
| `evaluation/metrics.py` | Métriques pures (appariement, précision/rappel/F1) |
| `evaluation/run_eval.py` | Comparatif de modèles |
| `evaluation/bench_isin.py` | Comparatif des stratégies de résolution ISIN |

---

## 9. Récit d'entretien (≈ 6 min)

1. **Problème (30 s)** — importer des relevés/captures de courtiers hétérogènes
   en ordres structurés exploitables.
2. **Pourquoi Vertex (1 min)** — jugement plateforme : auth IAM sans clé,
   génération contrôlée, PDF natif, embeddings, le tout dans un seul projet GCP
   déjà en prod sur Cloud Run.
3. **Architecture (1 min)** — abstraction multi-fournisseur où Gemini est
   first-class ; les autres modèles servent de banc d'essai.
4. **Mesure (1,5 min — le cœur)** — « je ne déploie pas un modèle, je le
   justifie » : Flash = Pro en qualité pour 4× moins cher → Flash + garde-fou
   `confidence`.
5. **Un arbitrage subtil (1 min)** — l'histoire du hybrid : la mesure a montré
   qu'un repli naïf n'aidait pas ; le routage à base de confiance, lui, récupère
   les cas multilingues sans régression et sans surcoût.
6. **Production & next steps (1 min)** — auth IAM, garde-fous coût/latence,
   re-ranking par classe de part, monitoring, boucle de feedback (corrections
   utilisateur → ré-éval).

**Phrase d'ancrage** : *« Mon rôle, ce n'est pas de faire marcher un appel modèle —
c'est de pouvoir dire* pourquoi *ce modèle, à* quel *coût, avec* quelle *fiabilité,
et comment le garder sous contrôle en prod. »*
