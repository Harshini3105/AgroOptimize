"""
Decision output & visualization support (reference paper, Section III-E).

NSGA-II hands back a *set* of non-dominated plans -- by definition none of
them is objectively "best". This module turns that Pareto front into the
"ranked decision table" the paper describes: each plan gets a composite
score via TOPSIS (driven by the farmer's stated preference), a
plain-language trade-off summary, and per-objective 0-1 "strength" scores
suitable for a radar/parallel-coordinates style chart on the future
frontend.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, List, Optional

import numpy as np

from app import config
from app.optimization.nsga2_runner import FarmPlan

Preference = str  # "balanced" | "max_yield" | "min_cost" | "min_water" | "min_env_impact"


def _round_percentages_to_100(fractions: List[float], decimals: int = 2) -> List[float]:
    """Round each `fraction * 100` to `decimals` places while guaranteeing
    the rounded values sum to exactly 100 (within float precision).

    Rounding each allocation fraction independently (the previous
    behaviour: `round(a * 100, 2)` per element) can drift the total a few
    hundredths away from 100 -- harmless for display, but it broke a test
    (`test_generate_farm_plans_end_to_end`'s `sum(allocation_percent) ==
    pytest.approx(100.0, abs=0.01)`) once Task 2/3's constant/rule changes
    shifted which chromosome NSGA-II/TOPSIS picks as the top plan and this
    latent rounding edge case got exercised. Uses the standard "largest
    remainder" method: round every value down, then hand the leftover
    (100 - sum of the rounded-down values, in units of the last decimal
    place) to the entries with the largest fractional remainder first.
    """
    if not fractions:
        return []
    scale = 10**decimals
    scaled = [f * 100 * scale for f in fractions]
    floored = [int(s // 1) for s in scaled]
    remainder = int(round(sum(scaled))) - sum(floored)
    order = sorted(range(len(scaled)), key=lambda i: (scaled[i] - floored[i]), reverse=True)
    for i in order[: max(remainder, 0)]:
        floored[i] += 1
    return [v / scale for v in floored]

_YIELD_GROUP_WEIGHT = 0.30  # see note below

_PREFERENCE_WEIGHTS: Dict[str, Dict[str, float]] = {
    # NOTE on "balanced": yield empirically correlates ~0.7-0.85 with cost,
    # water and env in this system (more land/inputs -> more of everything
    # at once, see notes/methodology_notes.md). A naive 0.25/0.25/0.25/0.25
    # split therefore lets the three correlated "footprint" objectives
    # outvote yield 3-to-1, and TOPSIS's #1 pick collapses to a
    # minimal-input corner plan. Weighting yield as its own criteria group,
    # roughly on par with the footprint group as a whole, was tuned to
    # reliably surface genuinely central, "good yield / fair cost" plans --
    # matching how the reference paper's own "Plan #1 (Best)" is a
    # deliberately balanced pick, not a corner of its Pareto set.
    "balanced": {
        "yield": _YIELD_GROUP_WEIGHT,
        "cost": (1 - _YIELD_GROUP_WEIGHT) / 3,
        "water": (1 - _YIELD_GROUP_WEIGHT) / 3,
        "env": (1 - _YIELD_GROUP_WEIGHT) / 3,
    },
    "max_yield": {"yield": 0.55, "cost": 0.15, "water": 0.15, "env": 0.15},
    "min_cost": {"yield": 0.15, "cost": 0.55, "water": 0.15, "env": 0.15},
    "min_water": {"yield": 0.15, "cost": 0.15, "water": 0.55, "env": 0.15},
    "min_env_impact": {"yield": 0.15, "cost": 0.15, "water": 0.15, "env": 0.55},
}


@dataclass
class RankedPlan:
    rank: int
    crop_names: List[str]
    allocation_percent: List[float]
    area_ha: List[float]
    irrigation_multiplier: List[float]
    fertilizer_multiplier: List[float]
    yield_tonnes: float
    cost_rs: float
    water_liters: float
    env_impact_score: float
    feasible: bool
    composite_score: float
    normalized_scores: Dict[str, float]   # yield/cost/water/env in [0,1], higher = better
    confidence_label: str
    trade_off_summary: str


def _minmax_norm(values: List[float], higher_is_better: bool) -> List[float]:
    """0-1 "goodness" score used for the composite ranking score, where
    1.0 always means "best in this plan set" regardless of objective."""
    lo, hi = min(values), max(values)
    if hi - lo < 1e-12:
        return [0.5 for _ in values]
    norm = [(v - lo) / (hi - lo) for v in values]
    return norm if higher_is_better else [1.0 - x for x in norm]


def _plain_minmax(values: List[float]) -> List[float]:
    """0-1 position of each value within the set's own range, with NO
    good/bad flip -- used only for wording the trade-off text so "High"
    always means "high raw quantity" (reader supplies the value judgement:
    high yield is good, high cost is bad)."""
    lo, hi = min(values), max(values)
    if hi - lo < 1e-12:
        return [0.5 for _ in values]
    return [(v - lo) / (hi - lo) for v in values]


def _bucket(x: float) -> str:
    if x >= 0.66:
        return "High"
    if x >= 0.33:
        return "Moderate"
    return "Low"


def filter_plans(
    plans: List[FarmPlan],
    max_cost: Optional[float] = None,
    max_water_liters: Optional[float] = None,
    min_yield_tonnes: Optional[float] = None,
    max_env_impact: Optional[float] = None,
) -> List[FarmPlan]:
    """Preference filters (Section III-E): narrow the Pareto set to plans
    that satisfy farmer-supplied hard limits."""
    out = plans
    if max_cost is not None:
        out = [p for p in out if p.cost_rs <= max_cost]
    if max_water_liters is not None:
        out = [p for p in out if p.water_liters <= max_water_liters]
    if min_yield_tonnes is not None:
        out = [p for p in out if p.yield_tonnes >= min_yield_tonnes]
    if max_env_impact is not None:
        out = [p for p in out if p.env_impact_score <= max_env_impact]
    return out


def rank_plans(
    plans: List[FarmPlan],
    crop_confidence_map: Dict[str, float],
    preference: Preference = "balanced",
    max_plans: int = config.MAX_RETURNED_PLANS,
) -> List[RankedPlan]:
    """Rank the Pareto front with TOPSIS (Technique for Order Preference by
    Similarity to Ideal Solution).

    A plain weighted sum of normalised objectives tends to hand the #1 spot
    to a corner solution that dominates on 3 objectives while being terrible
    on the 4th (e.g. a cheap, low-water monoculture with poor yield) -- that
    is *not* what "balanced" should mean. TOPSIS instead ranks each plan by
    how close it sits to the ideal point (best-in-set on every objective)
    relative to the worst point, which naturally favours well-rounded plans
    -- matching how the reference paper picks a single well-balanced
    recommendation (its "Plan #1 (Best)") out of its own Pareto set.
    """
    if not plans:
        return []

    weights = _PREFERENCE_WEIGHTS.get(preference, _PREFERENCE_WEIGHTS["balanced"])
    w = np.array([weights["yield"], weights["cost"], weights["water"], weights["env"]])

    yields = [p.yield_tonnes for p in plans]
    costs = [p.cost_rs for p in plans]
    waters = [p.water_liters for p in plans]
    envs = [p.env_impact_score for p in plans]

    yield_n = _minmax_norm(yields, higher_is_better=True)
    cost_n = _minmax_norm(costs, higher_is_better=False)
    water_n = _minmax_norm(waters, higher_is_better=False)
    env_n = _minmax_norm(envs, higher_is_better=False)

    # Raw-magnitude buckets (no good/bad flip) purely for wording the
    # plain-language trade-off sentence -- see _plain_minmax docstring.
    yield_raw = _plain_minmax(yields)
    cost_raw = _plain_minmax(costs)
    water_raw = _plain_minmax(waters)
    env_raw = _plain_minmax(envs)

    # ---- TOPSIS closeness coefficient ----
    # Weighted, normalised decision matrix; every column already points
    # "higher = better" thanks to _minmax_norm's good/bad flip above.
    M = np.column_stack([yield_n, cost_n, water_n, env_n]) * w
    ideal_best = M.max(axis=0)
    ideal_worst = M.min(axis=0)
    dist_best = np.sqrt(((M - ideal_best) ** 2).sum(axis=1))
    dist_worst = np.sqrt(((M - ideal_worst) ** 2).sum(axis=1))
    denom = dist_best + dist_worst
    closeness = np.divide(dist_worst, denom, out=np.full_like(denom, 0.5), where=denom > 1e-12)

    scored: List[RankedPlan] = []
    for i, p in enumerate(plans):
        ns = {"yield": round(yield_n[i], 3), "cost": round(cost_n[i], 3),
              "water": round(water_n[i], 3), "env": round(env_n[i], 3)}
        composite = float(closeness[i])

        # Land-weighted average crop confidence for this specific plan's mix.
        conf = sum(
            frac * crop_confidence_map.get(name, 0.7)
            for name, frac in zip(p.crop_names, p.allocation_fraction)
        )
        confidence_label = _bucket(conf)

        # Worded from the raw-magnitude buckets so "High cost" always means
        # "expensive" and never accidentally reads as "high goodness".
        summary = (
            f"{_bucket(yield_raw[i])} yield, {_bucket(cost_raw[i])} cost, "
            f"{_bucket(water_raw[i])} water use, {_bucket(env_raw[i])} environmental impact "
            f"(confidence: {confidence_label.lower()})"
        )

        scored.append(
            RankedPlan(
                rank=0,  # filled in after sort
                crop_names=p.crop_names,
                allocation_percent=_round_percentages_to_100(p.allocation_fraction),
                area_ha=[round(a, 3) for a in p.area_ha],
                irrigation_multiplier=[round(a, 3) for a in p.irrigation_multiplier],
                fertilizer_multiplier=[round(a, 3) for a in p.fertilizer_multiplier],
                yield_tonnes=p.yield_tonnes,
                cost_rs=p.cost_rs,
                water_liters=p.water_liters,
                env_impact_score=p.env_impact_score,
                feasible=p.feasible,
                composite_score=round(composite, 4),
                normalized_scores=ns,
                confidence_label=confidence_label,
                trade_off_summary=summary,
            )
        )

    scored.sort(key=lambda rp: rp.composite_score, reverse=True)
    scored = scored[:max_plans]
    for rank, rp in enumerate(scored, start=1):
        rp.rank = rank
    return scored


def to_dict_list(ranked: List[RankedPlan]) -> List[dict]:
    return [asdict(rp) for rp in ranked]
