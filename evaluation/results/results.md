# Évaluation comparative — extraction d'ordres

Golden set : 5 documents (CSV + PDF), 10 ordres attendus.

## Vue globale

| Modèle | F1 | Précision | Rappel | ISIN exact | Total déclaré | Latence p50 | p95 | Coût/doc (est.) | Erreurs |
|---|---|---|---|---|---|---|---|---|---|
| gemini-2.5-flash | 1.00 | 1.00 | 1.00 | 90% | 50% | 5.9s | 7.8s | $0.00037 | 0 |
| gemini-2.5-pro | 1.00 | 1.00 | 1.00 | 90% | 50% | 20.4s | 27.0s | $0.00146 | 0 |

## Exactitude ISIN par difficulté (corrects / appariés)

| Modèle | ISIN facile | ISIN moyen | ISIN difficile |
|---|---|---|---|
| gemini-2.5-flash | 4/4 | 2/2 | 3/4 |
| gemini-2.5-pro | 4/4 | 2/2 | 3/4 |

_Coût indicatif estimé à partir des tarifs du registre et d'une estimation de tokens (page PDF ≈ 258 tokens). Latence = horloge murale, dépend du réseau._
