"""Banc d'essai de la résolution nom→ISIN — TF-IDF vs embeddings vs hybrid.

N'appelle PAS le LLM : on teste uniquement la brique de résolution sur un jeu de
noms volontairement « bruités » (réordonnés, abrégés, traduits en français), ce
qui isole la variable mesurée et coûte une poignée d'embeddings (quasi gratuit).

Chaque requête est conçue pour pointer vers UN fonds (fournisseur + indice +
classe de part identifiables), même si le wording diffère du nom canonique.

Usage :
  GOOGLE_CLOUD_PROJECT=... ./venv/bin/python -m evaluation.bench_isin
"""
from __future__ import annotations

import os
from typing import List, Tuple

from services import import_service as I

# (requête bruitée, ISIN attendu, étiquette de difficulté)
DATASET: List[Tuple[str, str, str]] = [
    # Contrôles quasi exacts
    ("Amundi MSCI All Country World UCITS ETF EUR Acc", "LU1829220216", "facile"),
    ("Amundi Core S&P 500 Swap UCITS ETF EUR Dist", "LU0496786574", "facile"),
    # Réordonnés / abrégés
    ("All Country World Amundi acc", "LU1829220216", "moyen"),
    ("Amundi Core Nasdaq 100 acc", "LU1829221024", "moyen"),
    ("Amundi Core Stoxx 600 Europe", "LU0908500753", "moyen"),
    ("S&P 500 Amundi Core swap dist", "LU0496786574", "moyen"),
    ("Amundi world MSCI DR cap", "LU1437016972", "moyen"),
    ("iShares Nasdaq 100 acc", "IE00B53SZB19", "moyen"),
    # Classe de part en français (TF-IDF aveugle, embeddings multilingues OK)
    ("MSCI World Amundi DR distribuant", "LU1737652237", "difficile"),
    ("Vanguard S&P 500 distribuant", "IE00B3XXRP09", "difficile"),
]


def _run(strategy: str) -> List[bool]:
    I.ISIN_RESOLVER = strategy
    results = []
    for query, expected, _ in DATASET:
        got = I.resolve_isin(query)
        results.append(got == expected)
    return results


def main() -> None:
    strategies = ["tfidf", "embeddings", "hybrid"]
    # Vérifie la dispo de l'index embeddings.
    if I._load_isin_embeddings() is None:
        print("⚠️  Index d'embeddings absent : lance d'abord "
              "`./venv/bin/python -m scripts.build_isin_embeddings`.\n"
              "   → seul TF-IDF sera évalué.")
        strategies = ["tfidf"]

    per_strategy = {s: _run(s) for s in strategies}

    # Tableau récapitulatif
    print("\n# Banc d'essai résolution ISIN\n")
    print("| Stratégie | Exactitude | Corrects |")
    print("|---|---|---|")
    for s in strategies:
        ok = sum(per_strategy[s])
        n = len(DATASET)
        print(f"| {s} | {ok / n:.0%} | {ok}/{n} |")

    # Détail par requête (montre où embeddings rattrape le TF-IDF)
    print("\n## Détail par requête\n")
    header = "| Requête | Attendu | " + " | ".join(strategies) + " |"
    print(header)
    print("|" + "---|" * (len(strategies) + 2))
    for idx, (query, expected, diff) in enumerate(DATASET):
        cells = []
        for s in strategies:
            cells.append("✅" if per_strategy[s][idx] else "❌")
        q = query if len(query) <= 38 else query[:35] + "…"
        print(f"| {q} ({diff}) | {expected} | " + " | ".join(cells) + " |")


if __name__ == "__main__":
    main()
