# Fuzzy Rules Documentation

**Author:** Vennela Harshini (CB.SC.U4CSE23455)
**Module:** `app/fuzzy/engine.py`
**Type:** Mamdani Fuzzy Inference System (built with `scikit-fuzzy`)

This documents the fuzzy engine exactly as implemented in
`app/fuzzy/engine.py` -- every set, rule and constant below is taken
directly from `_build_system()` / `evaluate_uncertainty()` /
`crop_yield_confidence()`, not from the reference paper's more general
description. See `notes/methodology_notes.md` Section 5 for the narrative
write-up and `tests/test_fuzzy.py` for the tests that check this behaviour.

---

## Overview

The fuzzy uncertainty module converts three crisp, region-level readings
(rainfall deviation, water storage, soil fertility) into two scenario-weight
outputs -- `yield_confidence` and `irrigation_risk` -- which the NSGA-II
stage consumes via `crop_yield_confidence()` to scale each candidate crop's
expected yield (objective f1 in `app/optimization/problem.py`).

```
rainfall_dev  ┐
water_storage ├─ Mamdani FIS ─→ yield_conf ──/100──→ yield_confidence  [0,1]
soil_fert     ┘               → irrigation_risk ──/100──→ irrigation_risk [0,1]
```

## Input variables (3)

### 1. `rainfall_dev` -- universe **[-60, 60]**
`Deviation_Percent` from `rainfall.csv`, averaged over the season's months
(`RegionSeasonProfile.rainfall.avg_deviation_percent`).

| Label | Type | Parameters (a, b, c) |
|---|---|---|
| `deficit` | Triangular | (-60, -60, -5) |
| `normal` | Triangular | (-15, 0, 15) |
| `surplus` | Triangular | (5, 60, 60) |

### 2. `water_storage` -- universe **[0, 100]**
`Storage_Percent` from `water_availability.csv`, averaged over the season's
months (`RegionSeasonProfile.water.avg_storage_percent`).

| Label | Type | Parameters (a, b, c) |
|---|---|---|
| `low` | Triangular | (0, 0, 35) |
| `medium` | Triangular | (20, 50, 75) |
| `high` | Triangular | (60, 100, 100) |

### 3. `soil_fert` -- universe **[0, 100]**
The composite soil fertility index computed in
`app/data/preprocessing.py::compute_soil_fertility_index` (0.3×pH score +
0.3×organic-carbon score + 0.4×NPK score).

| Label | Type | Parameters (a, b, c) |
|---|---|---|
| `poor` | Triangular | (0, 0, 40) |
| `medium` | Triangular | (25, 50, 75) |
| `good` | Triangular | (60, 100, 100) |

## Output variables (2)

Both are defined on **[0, 100]** and divided by 100 before being returned
(`UncertaintyAssessment.yield_confidence` / `.irrigation_risk` are in
`[0, 1]`).

### 1. `yield_conf`
| Label | Type | Parameters (a, b, c) |
|---|---|---|
| `low` | Triangular | (0, 0, 45) |
| `medium` | Triangular | (30, 55, 75) |
| `high` | Triangular | (65, 100, 100) |

### 2. `irrigation_risk`
| Label | Type | Parameters (a, b, c) |
|---|---|---|
| `low` | Triangular | (0, 0, 35) |
| `medium` | Triangular | (25, 50, 75) |
| `high` | Triangular | (60, 100, 100) |

---

## Rule base (14 rules)

Mamdani AND = minimum of antecedent memberships (scikit-fuzzy
`ControlSystemSimulation` default); rules sharing an output are combined
with maximum; defuzzification is the **centroid** method (scikit-fuzzy's
default).

| # | IF `rainfall_dev` | IF `water_storage` | IF `soil_fert` | THEN `irrigation_risk` | THEN `yield_conf` |
|---|---|---|---|---|---|
| R1 | deficit | low | -- | high | low |
| R2 | deficit | medium | -- | medium | medium |
| R3 | deficit | high | -- | medium | medium |
| R4 | normal | low | -- | medium | medium |
| R5 | normal | medium | -- | low | high |
| R6 | normal | high | -- | low | high |
| R7 | surplus | low | -- | low | medium |
| R8 | surplus | medium | -- | low | high |
| R9 | surplus | high | -- | low | high |
| R10 | -- | -- | good | -- | high |
| R11 | -- | -- | poor | -- | low |
| R12 | normal | -- | medium | -- | medium |
| R13 | -- | high | good | -- | high |
| R14 | -- | low | poor | high | low |

R1-R9 form the full 3×3 cross of `rainfall_dev` × `water_storage`; R10-R14
layer `soil_fert` on top (R12-R14 combine soil with rainfall/water). A cell
with `--` means that antecedent isn't part of the rule.

If no rule fires strongly enough at extreme universe edges,
`evaluate_uncertainty` falls back to a neutral `(0.5, 0.5)` rather than
raising (`except (KeyError, ValueError)` in `engine.py`).

---

## Per-crop adjustment (`crop_yield_confidence`)

The region-level `yield_confidence` is the same for every crop in a
season, but a drip-irrigated crop and a rainfed one don't feel a rainfall
deficit equally. Each candidate crop's confidence is scaled down by its own
`Rainfall_Dependency` column (`crop.csv`):

```
dependency_factor = {"Very Low": 0.1, "Low": 0.3, "Medium": 0.6, "High": 1.0}.get(dep, 0.5)
penalty = irrigation_risk * dependency_factor * 0.4     # capped at 40% of base
crop_confidence = round(base_yield_confidence * (1 - penalty), 3)
```

At the worst case (`irrigation_risk = 1.0`, `"High"` dependency), a crop
retains at least 60% of the region's base confidence -- it is never zeroed
out entirely.

---

## Real regional outputs (2023 saved runs, `results/`)

These are the actual `fuzzy_assessment` values from saved runs in this
repo (not hand-picked illustrative numbers) -- see
`docs/results/coimbatore_erode.md` and `docs/results/salem_pollachi.md`
for the full write-up. Seasons differ per run because each is that
location's existing saved result; they are not a controlled same-season
comparison.

| Region | Season | Yield Confidence | Irrigation Risk | Rainfall / Water / Soil labels |
|---|---|---|---|---|
| Coimbatore | Kharif 2023 | 0.775 | 0.118 | normal / high / good |
| Erode | Rabi 2023 | 0.711 | 0.158 | normal / high / good |
| Salem | Kharif 2023 | 0.742 | 0.120 | normal / high / medium |
| Pollachi | Summer 2023 | 0.860 | 0.140 | normal / high / good |

All four 2023 runs landed in the "normal rainfall / high water storage /
good-or-medium soil" region of the input space, so confidence is
consistently mid-to-high and risk consistently low across all four
districts for these specific seasons -- there wasn't a drought-conditions
run in the currently-saved set. `tests/test_fuzzy.py::TestFuzzyRuleBaseBehaviour`
exercises the low-confidence/high-risk corner of the rule base directly
(deficit rainfall + low storage) since none of the saved real runs land
there.

---

## Defuzzification

Method: centroid (scikit-fuzzy default) --
`output = Σ(x · μ_aggregated(x)) / Σ(μ_aggregated(x))` over the aggregated
output membership function, where `μ_aggregated` is the point-wise maximum
of every rule's clipped consequent membership function.
