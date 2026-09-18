# System Architecture

**Author:** Garudammagari Sreenithya (CB.SC.U4CSE23061)
**Project:** AgroOptimize -- Team 52, Amrita Vishwa Vidyapeetham (23CSE498 Project Phase II)
**Guide:** Dr. G. Jeyakumar

This describes the backend exactly as implemented (verified against the
actual modules under `app/`, not the reference paper's higher-level
description -- see `notes/methodology_notes.md` for the full narrative
write-up this summarises).

---

## Overview

AgroOptimize is a 5-stage backend pipeline that turns raw Tamil Nadu
district agricultural data into ranked, Pareto-optimal farm plans, using a
Mamdani fuzzy inference layer for uncertainty and a custom NSGA-II for
multi-objective optimisation. It is currently **backend-only**; the
frontend is deliberately deferred until the UI is finalised (see
`docs/future_work.md`).

## Pipeline

```
data/raw/*.csv  (16 files: 4 districts x 4 kinds)
      |
      v
Stage 1  app/data/loader.py + app/data/preprocessing.py
         -> RegionSeasonProfile (soil, rainfall, water, candidate crops)
      |
      v
Stage 2  app/fuzzy/engine.py
         -> UncertaintyAssessment (yield_confidence, irrigation_risk)
      |
      v
Stage 3  app/optimization/{problem,operators,nsga2_runner}.py
         -> Pareto front (NSGA-II, 4 objectives)
      |
      v
Stage 4  app/decision/ranking.py
         -> TOPSIS-ranked, filtered, trade-off-annotated plans
      |
      v
Stage 5  app/services/results_store.py
         -> results/<run_id>.json + _plans.csv + _convergence.{csv,png}
      |
      v
app/main.py (FastAPI) -> JSON response / Swagger UI
```

`app/services/plan_service.py::generate_farm_plans()` is the single
function wiring all five stages together; both the API (`app/main.py`) and
the CLI demo (`run_demo.py`) call into it.

---

## Stage 1 -- Data collection & preprocessing (`app/data/`)

| File | Responsibility |
|---|---|
| `loader.py` | Loads and `lru_cache`s the 16 raw CSVs, concatenated per kind across all 4 locations |
| `preprocessing.py` | Builds a `RegionSeasonProfile` (soil, rainfall, water, candidate crops) for one (location, season, year) |

Covers 4 districts (Coimbatore, Erode, Salem, Pollachi) x 4 data kinds
(crop, land, rainfall, water availability) x 2020-2023 -- see
`docs/dataset_description.md` for the full column reference.

Key derived quantities:
- **Soil fertility index** (0-100): `0.3*pH_score + 0.3*organic_carbon_score + 0.4*NPK_score`.
- **Effective rainfall**: `avg_monthly_rainfall_mm * months_in_season * 0.7` (the 0.7 offsets runoff/percolation/evaporation losses).
- **Candidate crops**: top `DEFAULT_MAX_CANDIDATE_CROPS` (6) by historical `Revenue_Rs_Lakh`, configurable per request.

---

## Stage 2 -- Fuzzy uncertainty modelling (`app/fuzzy/engine.py`)

| Parameter | Value |
|---|---|
| Type | Mamdani (scikit-fuzzy `ControlSystem`) |
| Inputs | 3 (`rainfall_dev`, `water_storage`, `soil_fert`) |
| Outputs | 2 (`yield_conf`, `irrigation_risk`) |
| MF type | Triangular, 3 sets per variable |
| Rules | 14 |
| Defuzzification | Centroid |

Full rule base and membership-function parameters: `docs/fuzzy_rules.md`.
The two outputs feed Stage 3 via `crop_yield_confidence()`, which scales
each candidate crop's expected yield by its own `Rainfall_Dependency`.

---

## Stage 3 -- NSGA-II optimisation (`app/optimization/`)

| File | Responsibility |
|---|---|
| `problem.py` | `FarmPlanProblem` -- 4-objective pymoo `Problem`, vectorised `_evaluate` |
| `operators.py` | Custom `SinglePointCrossover`, `GaussianMutation`, `AllocationRepair` (implemented from scratch to match the paper's stated operators rather than pymoo's SBX/polynomial-mutation defaults) |
| `nsga2_runner.py` | Runs `pymoo.algorithms.moo.nsga2.NSGA2`, decodes the Pareto front, tracks per-generation convergence + hypervolume |

| Hyperparameter | Value (`app/config.py`) |
|---|---|
| Population | 80 |
| Generations | 200 |
| Crossover | Single-point, p=0.85 |
| Mutation | Gaussian, p=0.12, sigma=0.12 |
| Seed | 42 (reproducible) |
| Fast/test settings | pop=24, gen=15 |

Chromosome: length `3n` for `n` candidate crops -- land allocation
fraction, irrigation multiplier (0.7-1.3x), fertilizer multiplier
(0.7-1.3x) per crop.

**Objectives** (`FarmPlanProblem._evaluate`, all vectorised across the
population):

| # | Objective | Direction | What it computes |
|---|---|---|---|
| f1 | Yield (t) | Maximise | `sum(area * yield_kg_ha/1000 * fuzzy_crop_confidence)` |
| f2 | Cost (Rs) | Minimise | `sum(area * (fert_mult*fert_cost + pesticide_cost + labor_days*wage))` |
| f3 | Water (L) | Minimise | `sum(area * irr_mult * max(water_req - effective_rainfall, 0) * 10,000)` |
| f4 | Env. impact | Minimise | `sqrt(leaching_total * carbon_total)` -- geometric mean of an N-leaching proxy and a carbon proxy |

An optional inequality constraint (`cost - budget_rs <= 0`) applies when the
farmer supplies a budget; infeasible individuals are flagged, not dropped,
by `extract_pareto_plans` (filtering happens one layer up, in
`plan_service`).

---

## Stage 4 -- Decision output (`app/decision/ranking.py`)

Ranks the Pareto front with **TOPSIS** (closeness to an ideal point / away
from a worst point), rather than a plain weighted sum, because yield
empirically correlates ~0.7-0.85 with cost/water/env in this system --
see `notes/methodology_notes.md` Section 7 for why that makes a naive
weighted sum collapse to a minimal-input corner plan.

**Preference weight sets** (`ranking._PREFERENCE_WEIGHTS`, exact values):

| Preference | Yield | Cost | Water | Env |
|---|---|---|---|---|
| `balanced` | 0.300 | 0.233 | 0.233 | 0.233 |
| `max_yield` | 0.550 | 0.150 | 0.150 | 0.150 |
| `min_cost` | 0.150 | 0.550 | 0.150 | 0.150 |
| `min_water` | 0.150 | 0.150 | 0.550 | 0.150 |
| `min_env_impact` | 0.150 | 0.150 | 0.150 | 0.550 |

Each ranked plan also gets a plain-language trade-off summary (e.g. "High
yield, Moderate cost, Low water use, Moderate environmental impact") worded
from raw-magnitude buckets kept deliberately separate from the TOPSIS
goodness scores, so "Low cost" always means "cheap," never "scored low on
the cost criterion."

---

## Stage 5 -- Results persistence (`app/services/results_store.py`)

Every run (API or CLI) writes to `results/` by default
(`FarmPlanRequest.save_results`, default `true`), one `run_id`
(`<location>_<season>_<year>_<UTC-timestamp>`), up to 4 files:

| File | Contents |
|---|---|
| `<run_id>.json` | Full response + embedded convergence history |
| `<run_id>_plans.csv` | Ranked plan table, one row per plan |
| `<run_id>_convergence.csv` | One row per generation (best/mean objectives, hypervolume) |
| `<run_id>_convergence.png` | Hypervolume + best yield/cost vs. generation chart |

`results/` is git-ignored (see `.gitignore`) -- it's a local run log, not
committed source.

---

## API (`app/main.py`)

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness check |
| GET | `/api/catalog` | Locations / seasons / years / crops-by-season |
| GET | `/api/region-profile` | Preprocessing + fuzzy stages only (fast, no optimisation) |
| POST | `/api/farm-plans` | Full pipeline -> ranked plans (saves to disk by default) |
| GET | `/api/results` | List every saved run |
| GET | `/api/results/{run_id}` | Full saved record for one past run |

Full request/response schemas: `app/schemas.py`, browsable live at
`/docs`. Field-level detail: `docs/api_docs.md`.

---

## Technology stack

| Component | Technology |
|---|---|
| Language | Python 3.10 |
| API framework | FastAPI + Uvicorn |
| Optimisation | pymoo (NSGA-II) |
| Fuzzy logic | scikit-fuzzy |
| Data | pandas + NumPy |
| Visualisation | Matplotlib |
| Testing | pytest (`tests/test_pipeline.py`, `test_fuzzy.py`, `test_data.py`, `test_api.py`) |
| Persistence | File-based (JSON + CSV + PNG under `results/`) |

## Module dependency map

```
app/main.py
  -> app/services/plan_service.py
       -> app/data/loader.py
       -> app/data/preprocessing.py
       -> app/fuzzy/engine.py
       -> app/optimization/nsga2_runner.py
            -> app/optimization/problem.py
            -> app/optimization/operators.py
       -> app/decision/ranking.py
       -> app/services/results_store.py
```
