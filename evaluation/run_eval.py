"""Exécute l'évaluation comparative des modèles sur le golden set.

Pour chaque modèle disponible : extraction réelle de chaque document, mesure de
la latence (horloge murale) et estimation du coût, puis calcul des métriques
(précision/rappel/F1, exactitude ISIN, total déclaré). Produit un tableau
comparatif global + une vue « exactitude ISIN par difficulté » (qui isole le
cas difficile, là où la résolution sémantique fera la différence).

Usage :
  GOOGLE_CLOUD_PROJECT=... ./venv/bin/python -m evaluation.run_eval \
      --models gemini-2.5-flash,gemini-2.5-pro
"""
from __future__ import annotations

import os
import sys
import json
import time
import argparse
from collections import defaultdict
from typing import List, Dict, Any, Optional

from services import import_service as I
from evaluation import metrics as M

HERE = os.path.dirname(__file__)
GOLDEN_DIR = os.path.join(HERE, "golden")
RESULTS_DIR = os.path.join(HERE, "results")

GEMINI_PAGE_TOKENS = 258   # ordre de grandeur d'une page PDF / image pour Gemini


def _estimate_cost(spec: I.ModelSpec, content: bytes, mime: str, output_text: str) -> float:
    """Coût USD *indicatif* à partir des prix du registre et d'une estimation de tokens."""
    in_tokens = len(I.SYSTEM_PROMPT + I.USER_INSTRUCTION) / 4.0
    if mime.startswith("text"):
        in_tokens += len(content) / 4.0
    elif mime == "application/pdf":
        try:
            import fitz
            pages = fitz.open(stream=content, filetype="pdf").page_count
        except Exception:
            pages = 1
        in_tokens += pages * GEMINI_PAGE_TOKENS
    else:  # image
        in_tokens += GEMINI_PAGE_TOKENS
    out_tokens = len(output_text) / 4.0
    return in_tokens / 1e6 * spec.price_in + out_tokens / 1e6 * spec.price_out


def _load_manifest() -> List[Dict[str, Any]]:
    mpath = os.path.join(GOLDEN_DIR, "manifest.json")
    if not os.path.exists(mpath):
        sys.exit("Golden set absent. Lance d'abord : ./venv/bin/python -m evaluation.build_golden")
    with open(mpath, "r", encoding="utf-8") as f:
        return json.load(f)


def evaluate_model(model_key: str, manifest: List[Dict[str, Any]]) -> Dict[str, Any]:
    spec = I.resolve_model(model_key)
    cases: List[M.CaseMetrics] = []
    per_difficulty: Dict[str, List[M.CaseMetrics]] = defaultdict(list)

    for item in manifest:
        fpath = os.path.join(GOLDEN_DIR, item["file"])
        with open(fpath, "rb") as f:
            content = f.read()

        t0 = time.perf_counter()
        try:
            res = I.parse_orders_from_file(item["file"], content, item["mime"], model_key=model_key)
            latency = time.perf_counter() - t0
            cm = M.score_case(
                item["id"],
                predicted=res["orders"],
                expected=item["expected_orders"],
                declared_pred=res.get("declared_total_eur"),
                declared_exp=item.get("declared_total_eur"),
            )
            cm.latency_s = latency
            cm.est_cost_usd = _estimate_cost(spec, content, item["mime"], json.dumps(res["orders"]))
        except Exception as e:  # noqa: BLE001
            cm = M.CaseMetrics(case=item["id"], error=str(e))
            cm.latency_s = time.perf_counter() - t0
        cases.append(cm)
        per_difficulty[item["difficulty"]].append(cm)

    agg = M.aggregate(spec.key, cases)
    diff_isin = {
        d: (sum(c.isin_correct for c in cs), sum(c.tp for c in cs))
        for d, cs in per_difficulty.items()
    }
    return {"spec": spec, "agg": agg, "cases": cases, "diff_isin": diff_isin}


def _fmt_table(results: List[Dict[str, Any]]) -> str:
    head = ("| Modèle | F1 | Précision | Rappel | ISIN exact | Total déclaré | "
            "Latence p50 | p95 | Coût/doc (est.) | Erreurs |")
    sep = "|" + "---|" * 10
    lines = [head, sep]
    for r in results:
        a: M.Aggregate = r["agg"]
        n = max(a.n_cases, 1)
        lines.append(
            f"| {a.model} | {a.f1:.2f} | {a.precision:.2f} | {a.recall:.2f} | "
            f"{a.isin_acc:.0%} | {a.declared_acc:.0%} | {a.latency_p50:.1f}s | "
            f"{a.latency_p95:.1f}s | ${a.est_cost_usd / n:.5f} | {a.errors} |"
        )
    return "\n".join(lines)


def _fmt_difficulty(results: List[Dict[str, Any]]) -> str:
    diffs = ["facile", "moyen", "difficile"]
    lines = ["| Modèle | " + " | ".join(f"ISIN {d}" for d in diffs) + " |",
             "|" + "---|" * (len(diffs) + 1)]
    for r in results:
        cells = []
        for d in diffs:
            corr, tot = r["diff_isin"].get(d, (0, 0))
            cells.append(f"{corr}/{tot}" if tot else "—")
        lines.append(f"| {r['agg'].model} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="gemini-2.5-flash",
                    help="clés modèles séparées par des virgules")
    args = ap.parse_args()

    manifest = _load_manifest()
    keys = [k.strip() for k in args.models.split(",") if k.strip()]

    results = []
    for key in keys:
        spec = I.resolve_model(key)
        if not spec.has_credentials():
            print(f"⏭️  {key} : indisponible (identifiants absents) — ignoré.")
            continue
        print(f"▶️  Évaluation de {spec.key} sur {len(manifest)} cas…")
        results.append(evaluate_model(key, manifest))

    if not results:
        sys.exit("Aucun modèle évaluable. Vérifie l'auth Vertex / les clés API.")

    table = _fmt_table(results)
    diff_table = _fmt_difficulty(results)
    report = (
        "# Évaluation comparative — extraction d'ordres\n\n"
        f"Golden set : {len(manifest)} documents (CSV + PDF), "
        f"{sum(len(m['expected_orders']) for m in manifest)} ordres attendus.\n\n"
        "## Vue globale\n\n" + table + "\n\n"
        "## Exactitude ISIN par difficulté (corrects / appariés)\n\n" + diff_table + "\n\n"
        "_Coût indicatif estimé à partir des tarifs du registre et d'une estimation "
        "de tokens (page PDF ≈ 258 tokens). Latence = horloge murale, dépend du réseau._\n"
    )

    print("\n" + report)

    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(os.path.join(RESULTS_DIR, "results.md"), "w", encoding="utf-8") as f:
        f.write(report)
    serializable = [{
        "model": r["agg"].model,
        "f1": r["agg"].f1, "precision": r["agg"].precision, "recall": r["agg"].recall,
        "isin_acc": r["agg"].isin_acc, "declared_acc": r["agg"].declared_acc,
        "latency_p50": r["agg"].latency_p50, "latency_p95": r["agg"].latency_p95,
        "est_cost_total_usd": r["agg"].est_cost_usd, "errors": r["agg"].errors,
        "diff_isin": r["diff_isin"],
        "cases": [{"case": c.case, "tp": c.tp, "fp": c.fp, "fn": c.fn,
                   "isin_correct": c.isin_correct, "declared_ok": c.declared_ok,
                   "latency_s": round(c.latency_s, 3), "error": c.error} for c in r["cases"]],
    } for r in results]
    with open(os.path.join(RESULTS_DIR, "results.json"), "w", encoding="utf-8") as f:
        json.dump(serializable, f, ensure_ascii=False, indent=2)
    print(f"\n📄 Rapport écrit dans {RESULTS_DIR}/results.md et results.json")


if __name__ == "__main__":
    main()
