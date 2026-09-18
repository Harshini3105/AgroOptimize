"""
Fuzzy Uncertainty Modelling module (reference paper, Section III-C).

Converts the intrinsically imprecise agricultural inputs (rainfall
adequacy, water availability, soil fertility) into fuzzy linguistic sets
via triangular membership functions, runs them through a Mamdani-type
fuzzy inference engine with a hand-authored rule base, and defuzzifies
(centroid method, scikit-fuzzy's default) into two crisp scenario-weight
outputs:

  * yield_confidence  in [0, 1] - how much of the "book" yield the system
    expects to actually be realised this season, given current conditions.
  * irrigation_risk    in [0, 1] - how much extra irrigation pressure the
    season is likely to put on the farm (used to scale up the water
    objective / flag risk in the decision output).

These two scenario weights are what Section III-A calls "scenario-weighted
inputs for the multiple objective optimization module".
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np
import skfuzzy as fuzz
from skfuzzy import control as ctrl

from app import config


@dataclass
class UncertaintyAssessment:
    yield_confidence: float       # 0-1, higher = more confident of book yield
    irrigation_risk: float        # 0-1, higher = more irrigation pressure expected
    rainfall_label: str
    water_label: str
    soil_label: str


def _dominant_label(antecedent: ctrl.Antecedent, value: float) -> str:
    """Return the fuzzy set with the highest membership for `value`."""
    best_label, best_degree = "unknown", -1.0
    for label, mf in antecedent.terms.items():
        degree = fuzz.interp_membership(antecedent.universe, mf.mf, value)
        if degree > best_degree:
            best_label, best_degree = label, degree
    return best_label


@lru_cache(maxsize=1)
def _build_system() -> tuple[ctrl.ControlSystem, ctrl.Antecedent, ctrl.Antecedent, ctrl.Antecedent]:
    # --- Antecedents (inputs) ---
    rainfall_dev = ctrl.Antecedent(np.arange(-60, 60.1, 1), "rainfall_dev")
    water_storage = ctrl.Antecedent(np.arange(0, 100.1, 1), "water_storage")
    soil_fert = ctrl.Antecedent(np.arange(0, 100.1, 1), "soil_fert")

    # --- Consequents (outputs) ---
    yield_conf = ctrl.Consequent(np.arange(0, 100.1, 1), "yield_conf")
    irrigation_risk = ctrl.Consequent(np.arange(0, 100.1, 1), "irrigation_risk")

    rainfall_dev["deficit"] = fuzz.trimf(rainfall_dev.universe, [-60, -60, -5])
    rainfall_dev["normal"] = fuzz.trimf(rainfall_dev.universe, [-15, 0, 15])
    rainfall_dev["surplus"] = fuzz.trimf(rainfall_dev.universe, [5, 60, 60])

    water_storage["low"] = fuzz.trimf(water_storage.universe, [0, 0, 35])
    water_storage["medium"] = fuzz.trimf(water_storage.universe, [20, 50, 75])
    water_storage["high"] = fuzz.trimf(water_storage.universe, [60, 100, 100])

    soil_fert["poor"] = fuzz.trimf(soil_fert.universe, [0, 0, 40])
    soil_fert["medium"] = fuzz.trimf(soil_fert.universe, [25, 50, 75])
    soil_fert["good"] = fuzz.trimf(soil_fert.universe, [60, 100, 100])

    yield_conf["low"] = fuzz.trimf(yield_conf.universe, [0, 0, 45])
    yield_conf["medium"] = fuzz.trimf(yield_conf.universe, [30, 55, 75])
    yield_conf["high"] = fuzz.trimf(yield_conf.universe, [65, 100, 100])

    irrigation_risk["low"] = fuzz.trimf(irrigation_risk.universe, [0, 0, 35])
    irrigation_risk["medium"] = fuzz.trimf(irrigation_risk.universe, [25, 50, 75])
    irrigation_risk["high"] = fuzz.trimf(irrigation_risk.universe, [60, 100, 100])

    # --- Mamdani rule base (domain-expert-style heuristics) ---
    # Rules 1-14 below are the original 3x3 rainfall x water_storage grid
    # plus 5 soil-interaction rules. Rules 15-26 (added 2026-09-16, Task 3
    # of the panel-review prep list) extend the base to 26 rules, each tied
    # to a named agro-climatic scenario so the rule base reads as domain
    # reasoning, not an arbitrary grid search. They cover 3-way
    # rainfall x water x soil combinations the original 14 rules never
    # exercised (e.g. deficit+low-water+poor-soil as a single conjunction,
    # rather than relying on two separate 2-way rules to co-fire), plus two
    # agronomically real effects the original rule base didn't model at
    # all: (a) extreme rainfall surplus combined with poor soil drainage
    # should *cap* yield confidence via waterlogging/leaching risk instead
    # of always reading as good news, and (b) ample stored/canal water can
    # blunt irrigation risk even when soil or rainfall alone look
    # unfavourable.
    rules = [
        ctrl.Rule(rainfall_dev["deficit"] & water_storage["low"],
                  [irrigation_risk["high"], yield_conf["low"]]),
        ctrl.Rule(rainfall_dev["deficit"] & water_storage["medium"],
                  [irrigation_risk["medium"], yield_conf["medium"]]),
        ctrl.Rule(rainfall_dev["deficit"] & water_storage["high"],
                  [irrigation_risk["medium"], yield_conf["medium"]]),
        ctrl.Rule(rainfall_dev["normal"] & water_storage["low"],
                  [irrigation_risk["medium"], yield_conf["medium"]]),
        ctrl.Rule(rainfall_dev["normal"] & water_storage["medium"],
                  [irrigation_risk["low"], yield_conf["high"]]),
        ctrl.Rule(rainfall_dev["normal"] & water_storage["high"],
                  [irrigation_risk["low"], yield_conf["high"]]),
        ctrl.Rule(rainfall_dev["surplus"] & water_storage["low"],
                  [irrigation_risk["low"], yield_conf["medium"]]),
        ctrl.Rule(rainfall_dev["surplus"] & water_storage["medium"],
                  [irrigation_risk["low"], yield_conf["high"]]),
        ctrl.Rule(rainfall_dev["surplus"] & water_storage["high"],
                  [irrigation_risk["low"], yield_conf["high"]]),
        ctrl.Rule(soil_fert["good"], yield_conf["high"]),
        ctrl.Rule(soil_fert["poor"], yield_conf["low"]),
        ctrl.Rule(soil_fert["medium"] & rainfall_dev["normal"], yield_conf["medium"]),
        ctrl.Rule(water_storage["high"] & soil_fert["good"], yield_conf["high"]),
        ctrl.Rule(water_storage["low"] & soil_fert["poor"], [yield_conf["low"], irrigation_risk["high"]]),

        # 15. Severe/compound drought stress: deficit rainfall, low storage
        # AND poor soil all at once -- reinforces rule 1/14 with the full
        # 3-way conjunction so a genuine triple-stress season reads as
        # unambiguously worse than any single factor alone.
        ctrl.Rule(rainfall_dev["deficit"] & water_storage["low"] & soil_fert["poor"],
                  [yield_conf["low"], irrigation_risk["high"]]),

        # 16. Flood / waterlogging stress: extreme rainfall surplus with
        # high storage AND poor (poorly-draining) soil should NOT read as
        # good news the way plain surplus+high does elsewhere in the rule
        # base -- waterlogging and nutrient leaching cap yield confidence.
        ctrl.Rule(rainfall_dev["surplus"] & water_storage["high"] & soil_fert["poor"],
                  yield_conf["medium"]),

        # 17. Canal/reservoir irrigation advantage: ample stored water can
        # blunt irrigation risk even when soil fertility itself is poor
        # (the farmer isn't short of water, just soil quality).
        ctrl.Rule(water_storage["high"] & soil_fert["poor"], irrigation_risk["low"]),

        # 18. Groundwater depletion risk: low storage plus only medium soil
        # still signals real irrigation pressure, independent of the
        # current season's rainfall reading -- captures a farm running down
        # its groundwater/tank reserves over successive seasons.
        ctrl.Rule(water_storage["low"] & soil_fert["medium"], irrigation_risk["high"]),

        # 19. Post-monsoon Rabi transition: a rainfall deficit carried into
        # Rabi with only medium stored water isn't rescued to "high" yield
        # confidence just because the soil is good -- caps it at medium.
        ctrl.Rule(rainfall_dev["deficit"] & water_storage["medium"] & soil_fert["good"],
                  yield_conf["medium"]),

        # 20. Summer drought risk: rainfall deficit combined with poor soil
        # is a bad combination on its own, regardless of how much water is
        # currently in storage (elevated summer evapotranspiration can
        # outpace what stored water alone can offset).
        ctrl.Rule(rainfall_dev["deficit"] & soil_fert["poor"],
                  [yield_conf["low"], irrigation_risk["high"]]),

        # 21. Optimal combined conditions: the unambiguous best case
        # (normal rainfall, high storage, good soil) explicitly reinforced
        # as a 3-way conjunction rather than left to two 2-way rules.
        ctrl.Rule(rainfall_dev["normal"] & water_storage["high"] & soil_fert["good"],
                  [yield_conf["high"], irrigation_risk["low"]]),

        # 22. Semi-wet transitional zone (e.g. Erode-like conditions):
        # normal rainfall with only medium storage AND medium soil is a
        # genuinely middling case, distinct from the "normal+medium water"
        # 2-way rule (rule 5) which assumes soil isn't the limiting factor.
        ctrl.Rule(rainfall_dev["normal"] & water_storage["medium"] & soil_fert["medium"],
                  [yield_conf["medium"], irrigation_risk["medium"]]),

        # 23. Wet-zone transitional (e.g. Coimbatore/Pollachi-like
        # conditions): rainfall surplus doesn't guarantee a high outcome by
        # itself if both storage and soil are only medium -- reads as a
        # moderate, not optimal, season.
        ctrl.Rule(rainfall_dev["surplus"] & water_storage["medium"] & soil_fert["medium"],
                  yield_conf["medium"]),

        # 24. Canal irrigation advantage under deficit: even with a
        # rainfall deficit, high stored/canal water plus at least medium
        # soil keeps irrigation risk low and yield moderate rather than
        # falling to the generic "deficit+high water" 2-way rule's medium
        # risk reading.
        ctrl.Rule(rainfall_dev["deficit"] & water_storage["high"] & soil_fert["medium"],
                  [irrigation_risk["low"], yield_conf["medium"]]),

        # 25. Wet-zone optimal case (e.g. Coimbatore in a strong monsoon
        # year): rainfall surplus, high storage AND good soil together --
        # the clearest possible "very confident" reading.
        ctrl.Rule(rainfall_dev["surplus"] & water_storage["high"] & soil_fert["good"],
                  [yield_conf["high"], irrigation_risk["low"]]),

        # 26. Dry-zone marginal case (e.g. Salem in a weaker monsoon year):
        # rainfall deficit, only medium storage AND poor soil -- a real,
        # if less extreme than rule 15, stress combination.
        ctrl.Rule(rainfall_dev["deficit"] & water_storage["medium"] & soil_fert["poor"],
                  [yield_conf["low"], irrigation_risk["high"]]),
    ]

    system = ctrl.ControlSystem(rules)
    return system, rainfall_dev, water_storage, soil_fert


def evaluate_uncertainty(
    rainfall_deviation_percent: float,
    water_storage_percent: float,
    soil_fertility_index: float,
) -> UncertaintyAssessment:
    """Run the Mamdani fuzzy inference engine for one region/season snapshot.

    Inputs are clipped to the universes the membership functions were
    defined over, so extreme/out-of-range readings degrade gracefully
    instead of raising.
    """
    system, rainfall_dev, water_storage, soil_fert = _build_system()
    sim = ctrl.ControlSystemSimulation(system)

    r = float(np.clip(rainfall_deviation_percent, -60, 60))
    w = float(np.clip(water_storage_percent, 0, 100))
    s = float(np.clip(soil_fertility_index, 0, 100))

    sim.input["rainfall_dev"] = r
    sim.input["water_storage"] = w
    sim.input["soil_fert"] = s

    try:
        sim.compute()
        yield_conf = float(sim.output["yield_conf"]) / 100.0
        irr_risk = float(sim.output["irrigation_risk"]) / 100.0
    except (KeyError, ValueError):
        # No rule fired strongly enough (can happen at extreme universe
        # edges) -- fall back to a neutral, mildly cautious estimate.
        yield_conf, irr_risk = 0.5, 0.5

    return UncertaintyAssessment(
        yield_confidence=round(_clip01(yield_conf), 3),
        irrigation_risk=round(_clip01(irr_risk), 3),
        rainfall_label=_dominant_label(rainfall_dev, r),
        water_label=_dominant_label(water_storage, w),
        soil_label=_dominant_label(soil_fert, s),
    )


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, x))


def crop_yield_confidence(base_yield_confidence: float, irrigation_risk: float, rainfall_dependency: str) -> float:
    """Adjust the region-level yield confidence per crop, based on how
    rain-dependent that specific crop is (dataset column
    `Rainfall_Dependency`). A drip-irrigated, "Very Low" dependency crop
    barely feels a rainfall deficit; a rainfed "High" dependency crop feels
    it fully.
    """
    dep_factor = config.RAINFALL_DEPENDENCY_FACTOR.get(rainfall_dependency, 0.5)
    penalty = irrigation_risk * dep_factor * 0.4  # cap the max penalty at 40%
    return round(_clip01(base_yield_confidence * (1.0 - penalty)), 3)
