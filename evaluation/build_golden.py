"""Génère le golden set d'évaluation (documents + labels) de façon reproductible.

Trois niveaux de difficulté, pensés pour rendre mesurable le gain de chaque
amélioration :
  - FACILE   : ISIN présent dans le document (le modèle doit juste bien lire).
  - MOYEN    : nom exact du fonds, sans ISIN (teste la résolution nom→ISIN).
  - DIFFICILE: nom approximatif/réordonné/abrégé, sans ISIN (teste la robustesse
               de la résolution — là où les embeddings battent le TF-IDF).

On y mêle systématiquement des lignes « bruit » (dividendes, ventes, virements,
frais) qui DOIVENT être exclues : elles mesurent la précision (non-hallucination).

Usage :  ./venv/bin/python -m evaluation.build_golden
"""
from __future__ import annotations

import os
import json
from typing import List, Dict, Any

HERE = os.path.dirname(__file__)
GOLDEN_DIR = os.path.join(HERE, "golden")


def _order(name: str, isin: str, qty: float, pu: float, side: str = "buy") -> Dict[str, Any]:
    return {"name": name, "isin": isin, "quantity": qty, "unit_price_eur": pu,
            "total_eur": round(qty * pu, 2), "side": side}


# ---------------------------------------------------------------------------
# Définition des cas : (id, difficulté, format, lignes document, labels attendus,
# total déclaré attendu). Les `expected` ne contiennent QUE les achats, avec
# l'ISIN *vrai* (vérité terrain), indépendamment de ce que le pipeline trouvera.
# ---------------------------------------------------------------------------

CASES: List[Dict[str, Any]] = [
    {
        "id": "c01_csv_isin",
        "difficulty": "facile",
        "format": "csv",
        "rows": [
            ("2024-03-04", "ACHAT", "iShares Core MSCI World UCITS ETF", "IE00B4L5Y983", 3, 89.50),
            ("2024-03-04", "ACHAT", "Vanguard FTSE All-World UCITS ETF", "IE00BK5BQT80", 2, 105.20),
            ("2024-03-05", "DIVIDENDE", "iShares Core MSCI World", "IE00B4L5Y983", "", 4.20),
            ("2024-03-06", "VIREMENT", "Alimentation compte", "", "", 500.00),
            ("2024-03-31", "TOTAL", "Total investi du mois", "", "", 478.90),
        ],
        "expected": [
            _order("iShares Core MSCI World UCITS ETF", "IE00B4L5Y983", 3, 89.50),
            _order("Vanguard FTSE All-World UCITS ETF", "IE00BK5BQT80", 2, 105.20),
        ],
        "declared_total_eur": 478.90,
    },
    {
        "id": "c02_csv_names",
        "difficulty": "moyen",
        "format": "csv",
        "rows": [
            ("2024-02-01", "ACHAT", "Amundi Index MSCI World UCITS ETF DR (C)", "", 5, 23.10),
            ("2024-02-02", "ACHAT", "Amundi Core S&P 500 Swap UCITS ETF EUR Dist", "", 4, 41.80),
            ("2024-02-03", "VENTE", "Amundi Index MSCI World UCITS ETF DR (C)", "", 1, 23.40),
        ],
        "expected": [
            _order("Amundi Index MSCI World UCITS ETF DR (C)", "LU1437016972", 5, 23.10),
            _order("Amundi Core S&P 500 Swap UCITS ETF EUR Dist", "LU0496786574", 4, 41.80),
        ],
        "declared_total_eur": None,
    },
    {
        "id": "c03_csv_fuzzy",
        "difficulty": "difficile",
        "format": "csv",
        "rows": [
            # Noms réordonnés / abrégés volontairement (cas réels de screenshots).
            ("2024-01-10", "ACHAT", "MSCI World Amundi DR cap", "", 7, 23.05),
            ("2024-01-11", "ACHAT", "Amundi Nasdaq 100", "", 1, 510.00),
            ("2024-01-12", "FRAIS", "Frais de courtage", "", "", 1.90),
        ],
        "expected": [
            _order("Amundi Index MSCI World UCITS ETF DR (C)", "LU1437016972", 7, 23.05),
            _order("Amundi Core Nasdaq-100 Swap UCITS ETF Acc", "LU1829221024", 1, 510.00),
        ],
        "declared_total_eur": None,
    },
    {
        "id": "c04_pdf_isin",
        "difficulty": "facile",
        "format": "pdf",
        "rows": [
            ("2024-04-02", "ACHAT", "Amundi MSCI All Country World UCITS ETF EUR Acc", "LU1829220216", 6, 28.40),
            ("2024-04-02", "ACHAT", "Amundi CAC 40 UCITS ETF Dist", "FR0007052782", 10, 19.95),
            ("2024-04-03", "DIVIDENDE", "Amundi CAC 40", "FR0007052782", "", 6.10),
            ("2024-04-04", "VENTE", "Amundi MSCI All Country World", "LU1829220216", 2, 28.60),
            ("2024-04-05", "VIREMENT", "Virement entrant", "", "", 400.00),
            ("2024-04-30", "TOTAL", "Total investi du mois", "", "", 369.90),
        ],
        "expected": [
            _order("Amundi MSCI All Country World UCITS ETF EUR Acc", "LU1829220216", 6, 28.40),
            _order("Amundi CAC 40 UCITS ETF Dist", "FR0007052782", 10, 19.95),
        ],
        "declared_total_eur": 369.90,
    },
    {
        "id": "c05_pdf_fuzzy",
        "difficulty": "difficile",
        "format": "pdf",
        "rows": [
            ("2024-05-06", "ACHAT", "Amundi Stoxx Europe 600", "", 3, 215.30),
            ("2024-05-06", "ACHAT", "All Country World Amundi acc", "", 8, 28.50),
            ("2024-05-07", "VIREMENT", "Alimentation", "", "", 300.00),
        ],
        "expected": [
            _order("Amundi Core Stoxx Europe 600 UCITS ETF Acc", "LU0908500753", 3, 215.30),
            _order("Amundi MSCI All Country World UCITS ETF EUR Acc", "LU1829220216", 8, 28.50),
        ],
        "declared_total_eur": None,
    },
]


def _write_csv(path: str, rows: List[tuple]) -> None:
    lines = ["Date,Operation,Libelle,ISIN,Quantite,Montant_EUR"]
    for d, op, lib, isin, qte, montant in rows:
        lines.append(f"{d},{op},{lib},{isin},{qte},{montant}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _write_pdf(path: str, case_id: str, rows: List[tuple]) -> None:
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    header = f"RELEVE DE COMPTE TITRES  -  {case_id}\n\n"
    header += f"{'Date':<12}{'Operation':<12}{'Libelle':<46}{'Qte':>5}{'Montant(EUR)':>14}\n"
    header += "-" * 90 + "\n"
    body = ""
    for d, op, lib, isin, qte, montant in rows:
        q = "" if qte == "" else str(qte)
        ref = f" [{isin}]" if isin else ""
        body += f"{d:<12}{op:<12}{(lib + ref):<46}{q:>5}{montant:>14}\n"
    page.insert_text((36, 50), header + body, fontsize=8, fontname="cour")
    doc.save(path)
    doc.close()


def build() -> str:
    os.makedirs(GOLDEN_DIR, exist_ok=True)
    manifest: List[Dict[str, Any]] = []
    for case in CASES:
        fmt = case["format"]
        fname = f"{case['id']}.{fmt}"
        fpath = os.path.join(GOLDEN_DIR, fname)
        if fmt == "csv":
            _write_csv(fpath, case["rows"])
            mime = "text/csv"
        elif fmt == "pdf":
            _write_pdf(fpath, case["id"], case["rows"])
            mime = "application/pdf"
        else:
            raise ValueError(f"format inconnu: {fmt}")
        manifest.append({
            "id": case["id"],
            "difficulty": case["difficulty"],
            "file": fname,
            "mime": mime,
            "expected_orders": case["expected"],
            "declared_total_eur": case["declared_total_eur"],
        })
    mpath = os.path.join(GOLDEN_DIR, "manifest.json")
    with open(mpath, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    return mpath


if __name__ == "__main__":
    path = build()
    print(f"Golden set généré → {path}")
    print(f"{len(CASES)} cas, {sum(len(c['expected']) for c in CASES)} ordres attendus.")
