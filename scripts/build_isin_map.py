#!/usr/bin/env python3
"""
Génère data/isin_map.json — le fichier de correspondance nom de fonds → code ISIN
utilisé par services/import_service.py pour compléter les ISIN manquants à l'import.

Source de vérité : la page profil justETF, dont le <title> a la forme
    « Nom complet du fonds | TICKER | ISIN »
On part d'une liste d'ISIN d'ETF courants (PEA + grands UCITS européens) et on
récupère le nom canonique depuis la source. Aucun nom n'est inventé : un ISIN
introuvable (le titre ne se termine pas par l'ISIN demandé) est simplement écarté.

Usage :
    ./venv/bin/python scripts/build_isin_map.py            # régénère data/isin_map.json
    ./venv/bin/python scripts/build_isin_map.py --csv      # écrit aussi data/isin_map.csv
    ISIN_EXTRA="IE00B4L5Y983,FR0011871128" ./venv/bin/python scripts/build_isin_map.py

Pour ajouter des ETF : complète CANDIDATE_ISINS ou passe-les via ISIN_EXTRA.
"""
import os
import re
import csv
import json
import time
import argparse
import logging

import requests

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("build_isin_map")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_JSON = os.path.join(ROOT, "data", "isin_map.json")
OUT_CSV = os.path.join(ROOT, "data", "isin_map.csv")

PROFILE_URL = "https://www.justetf.com/fr/etf-profile.html"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15) AppleWebKit/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}
ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")
TITLE_RE = re.compile(r"<title>(.*?)</title>", re.IGNORECASE | re.DOTALL)

# Liste d'ISIN d'ETF largement détenus par des investisseurs particuliers
# français (PEA Amundi + CTO iShares/Vanguard/Xtrackers/SPDR/Invesco/BNP...).
# Le nom est récupéré depuis justETF ; ces ISIN ne servent qu'à amorcer la
# recherche. Les entrées invalides sont automatiquement ignorées.
CANDIDATE_ISINS = [
    # --- World / All-World ---
    "LU1681043599",  # Amundi MSCI World (CW8)
    "IE00B4L5Y983",  # iShares Core MSCI World
    "IE00BK5BQT80",  # Vanguard FTSE All-World Acc
    "IE00B3RBWM25",  # Vanguard FTSE All-World Dist
    "IE00BFY0GT14",  # SPDR MSCI ACWI IMI
    "IE00B44Z5B48",  # SPDR MSCI ACWI
    "IE00BJ0KDQ92",  # Xtrackers MSCI World
    "LU0274208692",  # Xtrackers MSCI World Swap
    "IE00BFNM3P36",  # Amundi Prime Global
    "FR0011869353",  # Amundi PEA Monde (EWLD)
    "IE00BD4TYL27",  # iShares MSCI World ESG / SRI variants
    # --- S&P 500 / USA ---
    "FR0011871128",  # Amundi PEA S&P 500
    "IE00B5BMR087",  # iShares Core S&P 500
    "IE00BFMXXD54",  # Vanguard S&P 500 (Acc)
    "IE00B3XXRP09",  # Vanguard S&P 500 (Dist)
    "LU0496786574",  # Amundi S&P 500 (ex-Lyxor)
    "IE00BYML9W36",  # Invesco S&P 500
    "IE00B3YCGJ38",  # Invesco S&P 500 (variant)
    # --- Nasdaq / Tech ---
    "IE00B53SZB19",  # iShares Nasdaq 100
    "LU1681038243",  # Amundi Nasdaq-100
    "IE00BMC38736",  # Invesco Nasdaq-100 (EQQQ Acc)
    # --- Europe ---
    "IE00B4K48X80",  # iShares Core MSCI Europe
    "LU0908500753",  # Amundi Core STOXX Europe 600 (ex-Lyxor)
    "IE00BKX55T58",  # Vanguard FTSE Developed Europe
    "FR0010296061",  # Lyxor/Amundi CAC 40 (DR)
    "FR0011550185",  # Amundi PEA Europe
    "IE00B945VV12",  # Vanguard FTSE Developed Europe ex-UK
    # --- Émergents ---
    "IE00BKM4GZ66",  # iShares Core MSCI EM IMI
    "IE00B3VVMM84",  # Vanguard FTSE Emerging Markets
    "LU1681045370",  # Amundi MSCI Emerging Markets
    "FR0013412020",  # Amundi PEA Émergents (ESG)
    # --- World hors zones / facteurs / petites capi ---
    "IE00BF4RFH31",  # iShares MSCI World Small Cap
    "IE00BD45KH83",  # Vanguard ESG Global All Cap
    "IE00BFNM3J75",  # Amundi Prime All Country World
    # --- Obligations / autres classiques ---
    "IE00B4WXJJ64",  # iShares Core Global Aggregate Bond
    "IE00B3F81R35",  # iShares Core Euro Corporate Bond
    "LU1437016972",  # Amundi MSCI World ex-EMU / variantes
    # --- Sectoriels / thématiques très courants ---
    "IE00BYZK4552",  # iShares Automation & Robotics
    "IE00BGV5VN51",  # Xtrackers MSCI World Information Technology
    "IE00BM67HK77",  # Xtrackers MSCI World Health Care
]


def fetch_name(isin: str, session: requests.Session) -> str | None:
    """Renvoie le nom canonique justETF pour un ISIN, ou None si introuvable."""
    try:
        resp = session.get(
            PROFILE_URL, params={"isin": isin}, headers=HEADERS, timeout=10
        )
        resp.raise_for_status()
    except Exception as e:  # noqa: BLE001
        log.warning("  ✗ %s — requête échouée : %s", isin, e)
        return None

    m = TITLE_RE.search(resp.text)
    if not m:
        log.warning("  ✗ %s — pas de <title>", isin)
        return None

    title = re.sub(r"\s+", " ", m.group(1)).strip()
    parts = [p.strip() for p in title.split("|")]
    # Format attendu : « Nom | TICKER | ISIN ». On valide que l'ISIN correspond.
    if len(parts) < 2 or parts[-1].upper() != isin.upper():
        log.warning("  ✗ %s — titre inattendu : %r", isin, title)
        return None

    name = parts[0].strip()
    if not name:
        log.warning("  ✗ %s — nom vide", isin)
        return None
    return name


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", action="store_true", help="écrit aussi data/isin_map.csv")
    parser.add_argument("--delay", type=float, default=0.4, help="délai entre requêtes (s)")
    args = parser.parse_args()

    isins = list(dict.fromkeys(i.strip().upper() for i in CANDIDATE_ISINS))
    extra = os.environ.get("ISIN_EXTRA", "")
    for i in extra.split(","):
        i = i.strip().upper()
        if i and i not in isins:
            isins.append(i)

    invalid = [i for i in isins if not ISIN_RE.match(i)]
    if invalid:
        log.warning("ISIN mal formés ignorés : %s", ", ".join(invalid))
    isins = [i for i in isins if ISIN_RE.match(i)]

    log.info("Résolution de %d ISIN via justETF…", len(isins))
    session = requests.Session()
    mapping: dict[str, str] = {}
    for idx, isin in enumerate(isins, 1):
        name = fetch_name(isin, session)
        if name:
            mapping[name] = isin
            log.info("  ✓ %s → %s", isin, name)
        if args.delay and idx < len(isins):
            time.sleep(args.delay)

    mapping = dict(sorted(mapping.items(), key=lambda kv: kv[0].lower()))

    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)
        f.write("\n")
    log.info("→ %d entrées écrites dans %s", len(mapping), OUT_JSON)

    if args.csv:
        with open(OUT_CSV, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["isin", "name"])
            for name, isin in mapping.items():
                w.writerow([isin, name])
        log.info("→ CSV écrit dans %s", OUT_CSV)


if __name__ == "__main__":
    main()
