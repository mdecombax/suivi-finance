"""Pré-calcule l'index d'embeddings des noms de fonds (résolution ISIN sémantique).

Embede une seule fois chaque nom de data/isin_map.json via Vertex AI
(text-multilingual-embedding-002, task_type=RETRIEVAL_DOCUMENT) et écrit
data/isin_embeddings.json : [{name, isin, embedding}, ...].

Coût : une seule passe sur ~140 noms (~quelques milliers de tokens) → fraction
de centime. À relancer uniquement quand la map ISIN change.

Usage :
  GOOGLE_CLOUD_PROJECT=... ./venv/bin/python -m scripts.build_isin_embeddings
"""
from __future__ import annotations

import os
import sys
import json
from typing import List, Dict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ISIN_MAP_PATH = os.path.join(ROOT, "data", "isin_map.json")
OUT_PATH = os.path.join(ROOT, "data", "isin_embeddings.json")
EMBED_MODEL = os.environ.get("ISIN_EMBED_MODEL", "text-multilingual-embedding-002")
BATCH = 100   # marge sous la limite d'instances par requête


def _load_map() -> List[Dict[str, str]]:
    with open(ISIN_MAP_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)
    if isinstance(raw, dict):
        items = list(raw.items())
    else:
        items = [(d.get("name"), d.get("isin")) for d in raw if isinstance(d, dict)]
    out = []
    for name, isin in items:
        name = (name or "").strip()
        isin = (isin or "").strip().upper()
        if name and isin:
            out.append({"name": name, "isin": isin})
    return out


def main() -> None:
    project = (os.environ.get("VERTEX_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT")
               or os.environ.get("GCLOUD_PROJECT"))
    if not project:
        sys.exit("Projet Vertex absent : définis GOOGLE_CLOUD_PROJECT et authentifie-toi (ADC).")
    location = (os.environ.get("VERTEX_LOCATION") or os.environ.get("GOOGLE_CLOUD_LOCATION")
                or "europe-west1")

    from google import genai
    from google.genai import types
    client = genai.Client(vertexai=True, project=project, location=location)

    entries = _load_map()
    if not entries:
        sys.exit(f"Aucune entrée exploitable dans {ISIN_MAP_PATH}.")
    print(f"Embedding de {len(entries)} noms via {EMBED_MODEL}…")

    vectors: List[List[float]] = []
    for i in range(0, len(entries), BATCH):
        chunk = entries[i:i + BATCH]
        resp = client.models.embed_content(
            model=EMBED_MODEL,
            contents=[e["name"] for e in chunk],
            config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT"),
        )
        vectors.extend(list(emb.values) for emb in resp.embeddings)
        print(f"  {min(i + BATCH, len(entries))}/{len(entries)}")

    if len(vectors) != len(entries):
        sys.exit(f"Incohérence : {len(vectors)} vecteurs pour {len(entries)} noms.")

    out = [{"name": e["name"], "isin": e["isin"], "embedding": v}
           for e, v in zip(entries, vectors)]
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    dim = len(vectors[0]) if vectors else 0
    print(f"Index écrit → {OUT_PATH} ({len(out)} entrées, dim {dim}).")


if __name__ == "__main__":
    main()
