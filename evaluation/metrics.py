"""Métriques d'évaluation de l'extraction d'ordres — pures, sans I/O réseau.

Le cœur est l'appariement (matching) entre ordres *prédits* et ordres *attendus* :
on score chaque paire sur plusieurs signaux (quantité, ISIN, recouvrement de nom)
pour rester robuste si le modèle se trompe sur un champ isolé. À partir de
l'appariement on dérive précision/rappel/F1 (a-t-on extrait le bon ENSEMBLE
d'achats, sans inventer ni rater ?) et l'exactitude ISIN sur les paires appariées.
"""
from __future__ import annotations

import unicodedata
import re
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple

QTY_TOL = 1e-6          # tolérance d'égalité des quantités
DECLARED_TOL = 0.02     # tolérance relative sur le total déclaré


def _norm_name(name: Optional[str]) -> str:
    if not name:
        return ""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii").lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _name_tokens(name: Optional[str]) -> set:
    return set(_norm_name(name).split())


def _pair_score(exp: Dict[str, Any], pred: Dict[str, Any]) -> float:
    """Score d'appariement entre un ordre attendu et un ordre prédit.

    Quantité identique = signal fort (3) ; ISIN identique = (2) ; recouvrement
    de tokens du nom = (jusqu'à 2). Un score nul interdit l'appariement.
    """
    score = 0.0
    eq, pq = exp.get("quantity"), pred.get("quantity")
    if eq is not None and pq is not None and abs(eq - pq) <= max(QTY_TOL, 1e-4 * abs(eq)):
        score += 3.0
    ei, pi = (exp.get("isin") or "").upper(), (pred.get("isin") or "").upper()
    if ei and pi and ei == pi:
        score += 2.0
    et, pt = _name_tokens(exp.get("name")), _name_tokens(pred.get("name"))
    if et and pt:
        jac = len(et & pt) / len(et | pt)
        score += 2.0 * jac
    return score


@dataclass
class CaseMetrics:
    case: str
    tp: int = 0
    fp: int = 0
    fn: int = 0
    isin_correct: int = 0     # ISIN exact parmi les paires appariées
    declared_ok: Optional[bool] = None
    latency_s: float = 0.0
    est_cost_usd: float = 0.0
    error: Optional[str] = None

    @property
    def precision(self) -> float:
        d = self.tp + self.fp
        return self.tp / d if d else 1.0

    @property
    def recall(self) -> float:
        d = self.tp + self.fn
        return self.tp / d if d else 1.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    @property
    def isin_acc(self) -> float:
        return self.isin_correct / self.tp if self.tp else 1.0


def score_case(
    case: str,
    predicted: List[Dict[str, Any]],
    expected: List[Dict[str, Any]],
    declared_pred: Optional[float] = None,
    declared_exp: Optional[float] = None,
) -> CaseMetrics:
    """Apparie prédits/attendus (glouton sur le meilleur score) et calcule les compteurs."""
    m = CaseMetrics(case=case)

    # Appariement glouton : on traite les meilleures paires d'abord.
    candidates: List[Tuple[float, int, int]] = []
    for ei, e in enumerate(expected):
        for pi, p in enumerate(predicted):
            s = _pair_score(e, p)
            if s > 0:
                candidates.append((s, ei, pi))
    candidates.sort(reverse=True)

    used_exp, used_pred = set(), set()
    for s, ei, pi in candidates:
        if ei in used_exp or pi in used_pred:
            continue
        used_exp.add(ei)
        used_pred.add(pi)
        m.tp += 1
        if (expected[ei].get("isin") or "").upper() == (predicted[pi].get("isin") or "").upper():
            m.isin_correct += 1

    m.fn = len(expected) - len(used_exp)
    m.fp = len(predicted) - len(used_pred)

    if declared_exp is not None:
        if declared_pred is None:
            m.declared_ok = False
        else:
            m.declared_ok = abs(declared_pred - declared_exp) <= DECLARED_TOL * max(1.0, abs(declared_exp))

    return m


@dataclass
class Aggregate:
    model: str
    n_cases: int
    tp: int
    fp: int
    fn: int
    isin_correct: int
    declared_ok: int
    declared_total: int
    latencies: List[float]
    est_cost_usd: float
    errors: int

    @property
    def precision(self) -> float:
        d = self.tp + self.fp
        return self.tp / d if d else 1.0

    @property
    def recall(self) -> float:
        d = self.tp + self.fn
        return self.tp / d if d else 1.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    @property
    def isin_acc(self) -> float:
        return self.isin_correct / self.tp if self.tp else 1.0

    @property
    def declared_acc(self) -> float:
        return self.declared_ok / self.declared_total if self.declared_total else 1.0

    @property
    def latency_p50(self) -> float:
        return _percentile(self.latencies, 50)

    @property
    def latency_p95(self) -> float:
        return _percentile(self.latencies, 95)


def aggregate(model: str, cases: List[CaseMetrics]) -> Aggregate:
    return Aggregate(
        model=model,
        n_cases=len(cases),
        tp=sum(c.tp for c in cases),
        fp=sum(c.fp for c in cases),
        fn=sum(c.fn for c in cases),
        isin_correct=sum(c.isin_correct for c in cases),
        declared_ok=sum(1 for c in cases if c.declared_ok is True),
        declared_total=sum(1 for c in cases if c.declared_ok is not None),
        latencies=[c.latency_s for c in cases if c.error is None],
        est_cost_usd=sum(c.est_cost_usd for c in cases),
        errors=sum(1 for c in cases if c.error is not None),
    )


def _percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * pct / 100.0
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)
