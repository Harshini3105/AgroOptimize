# API Documentation

**Author:** Garudammagari Sreenithya (CB.SC.U4CSE23061)
**Base URL:** `http://localhost:8000`
**Swagger UI:** `http://localhost:8000/docs`

Every field name and example value below was checked against
`app/schemas.py` and a real saved run in `results/` -- field names are
load-bearing (FastAPI/Pydantic will 422 a request that uses the wrong
ones), so this intentionally does not simplify them.

---

## GET /health

Liveness check.

**Response**
```json
{"status": "ok"}
```

---

## GET /api/catalog

Lists what the dataset covers. Source: `app/data/preprocessing.py::list_catalog()`.

**Response**
```json
{
  "locations": ["Coimbatore", "Erode", "Salem", "Pollachi"],
  "seasons": ["Kharif", "Rabi", "Summer"],
  "years": [2020, 2021, 2022, 2023],
  "crops_by_season": {
    "Kharif": ["Cotton", "Groundnut", "Maize", "Sorghum", "Sugarcane", "..."],
    "Rabi": ["Banana", "Paddy", "Sunflower", "..."],
    "Summer": ["Fodder Crops", "Maize", "..."]
  }
}
```
Note: there is no separate `preference_modes` field -- the valid
`preference` values are the `Literal` in `app/schemas.py`:
`balanced | max_yield | min_cost | min_water | min_env_impact`.

---

## GET /api/region-profile

Preprocessing + fuzzy stages only -- no NSGA-II, so it's fast. Useful for
inspecting/demoing the data pipeline in isolation.

**Query parameters**

| Param | Type | Required | Example |
|---|---|---|---|
| `location` | string | yes | `Coimbatore` |
| `season` | string | yes | `Kharif` |
| `year` | int | no (defaults to latest) | `2023` |

**Response** (trimmed -- `candidate_crops` has one entry per crop actually returned)
```json
{
  "location": "Coimbatore",
  "year": 2023,
  "season": "Kharif",
  "soil": {
    "soil_type": "Red Sandy Loam",
    "avg_ph": 7.1,
    "organic_carbon_percent": 0.65,
    "n_status": "Medium", "p_status": "Medium", "k_status": "High",
    "irrigation_percent": 59.7,
    "fertility_index": 70.3
  },
  "rainfall": {
    "avg_monthly_rainfall_mm": 56.0,
    "avg_deviation_percent": 1.05,
    "avg_humidity_percent": 76.5,
    "avg_max_temp_c": 34.1, "avg_min_temp_c": 23.77,
    "months_used": ["June", "July", "August", "September"],
    "effective_rainfall_mm": 156.8
  },
  "water": {
    "avg_storage_percent": 94.7,
    "groundwater_status": "Very High",
    "avg_deficit_surplus_mcm": 0.0
  },
  "candidate_crops": ["Sugarcane", "Maize", "Groundnut", "Cotton", "Sorghum"],
  "normalized_snapshot": {
    "soil_ph_norm": 0.62, "organic_carbon_norm": 0.433,
    "rainfall_norm": 0.373, "rainfall_deviation_norm": 0.51,
    "water_storage_norm": 0.947, "soil_fertility_index_norm": 0.703
  },
  "fuzzy_assessment": {
    "yield_confidence": 0.775, "irrigation_risk": 0.118,
    "rainfall_label": "normal", "water_label": "high", "soil_label": "good"
  }
}
```

---

## POST /api/farm-plans

Full pipeline: preprocessing -> fuzzy -> NSGA-II -> TOPSIS ranking.

**Request body** (`app/schemas.py::FarmPlanRequest`)

| Field | Type | Required | Notes |
|---|---|---|---|
| `location` | string | yes | one of `/api/catalog`'s `locations` |
| `season` | string | yes | one of `/api/catalog`'s `seasons` |
| `year` | int | no | defaults to the latest year in the dataset |
| `total_land_ha` | float | **yes**, `> 0` | total farm land, hectares |
| `budget_rs` | float | no, `> 0` | optional hard cost cap |
| `preference` | enum | no, default `balanced` | `balanced\|max_yield\|min_cost\|min_water\|min_env_impact` |
| `max_candidate_crops` | int | no, `2-12` | overrides the default top-6 candidate crops |
| `max_cost_rs`, `max_water_liters`, `min_yield_tonnes`, `max_env_impact` | float | no | post-hoc filters on the Pareto front before ranking |
| `pop_size` | int | no, `8-300` | NSGA-II population override |
| `n_gen` | int | no, `5-500` | NSGA-II generation-count override |
| `save_results` | bool | no, default `true` | persist this run to `results/` |

```json
{
  "location": "Coimbatore",
  "season": "Kharif",
  "year": 2023,
  "total_land_ha": 5,
  "budget_rs": 200000,
  "preference": "balanced"
}
```

**Response** (`FarmPlanResponse`, trimmed to 1 of the ~50 returned plans)
```json
{
  "region_profile": { "...": "same shape as GET /api/region-profile's body" },
  "fuzzy_assessment": {
    "yield_confidence": 0.775, "irrigation_risk": 0.118,
    "rainfall_label": "normal", "water_label": "high", "soil_label": "good"
  },
  "plans": [
    {
      "rank": 1,
      "crop_names": ["Sugarcane", "Sorghum"],
      "allocation_percent": [11.3, 88.7],
      "area_ha": [0.56, 4.44],
      "irrigation_multiplier": [0.94, 1.05],
      "fertilizer_multiplier": [0.88, 1.12],
      "yield_tonnes": 48.43,
      "cost_rs": 170702.18,
      "water_liters": 12174241.4,
      "env_impact_score": 197.18,
      "feasible": true,
      "composite_score": 0.7124,
      "normalized_scores": {"yield": 0.91, "cost": 0.62, "water": 0.58, "env": 0.60},
      "confidence_label": "High",
      "trade_off_summary": "Moderate yield, Moderate cost, Low water use, Moderate environmental impact (confidence: high)"
    }
  ],
  "convergence_history": [
    {"generation": 1, "population_size": 80, "best_yield_tonnes": 12.4, "hypervolume": 0.33, "...": "..."},
    {"generation": 200, "population_size": 80, "best_yield_tonnes": 50.2, "hypervolume": 0.50, "...": "..."}
  ],
  "meta": {
    "algorithm": "NSGA-II", "pop_size": 80, "n_gen": 200,
    "crossover_prob": 0.85, "mutation_prob": 0.12,
    "preference": "balanced", "n_pareto_solutions_found": 80,
    "n_plans_returned": 50, "optimize_seconds": 1.1
  },
  "run_id": "coimbatore_kharif_2023_20260808T113724Z",
  "saved_files": {
    "run_id": "coimbatore_kharif_2023_20260808T113724Z",
    "json_path": "results/coimbatore_kharif_2023_20260808T113724Z.json",
    "plans_csv_path": "results/coimbatore_kharif_2023_20260808T113724Z_plans.csv",
    "convergence_csv_path": "results/coimbatore_kharif_2023_20260808T113724Z_convergence.csv",
    "convergence_plot_path": "results/coimbatore_kharif_2023_20260808T113724Z_convergence.png"
  }
}
```
`run_id` / `saved_files` are `null` when `save_results: false`.

---

## GET /api/results

Lists every run saved to `results/` so far (most recent first). Source:
`app/services/results_store.py::list_saved_runs()`.

**Response** (`SavedRunSummaryOut[]`)
```json
[
  {
    "run_id": "coimbatore_kharif_2023_20260808T113724Z",
    "location": "Coimbatore",
    "season": "Kharif",
    "year": 2023,
    "preference": "balanced",
    "saved_at": "2026-08-08T11:37:25.912481+00:00",
    "n_plans": 50
  }
]
```

---

## GET /api/results/{run_id}

Full saved record for one past run -- exactly what `POST /api/farm-plans`
returned at the time, including the complete `convergence_history`. Same
shape as the `POST /api/farm-plans` response. 404s if `run_id` doesn't
exist.

---

## Preference weight table (`app/decision/ranking.py::_PREFERENCE_WEIGHTS`)

| Preference | Yield | Cost | Water | Env |
|---|---|---|---|---|
| `balanced` | 0.300 | 0.233 | 0.233 | 0.233 |
| `max_yield` | 0.550 | 0.150 | 0.150 | 0.150 |
| `min_cost` | 0.150 | 0.550 | 0.150 | 0.150 |
| `min_water` | 0.150 | 0.150 | 0.550 | 0.150 |
| `min_env_impact` | 0.150 | 0.150 | 0.150 | 0.550 |

---

## Error responses

| Code | Meaning | Raised when |
|---|---|---|
| 200 | Success | -- |
| 400 | Bad request | Unknown `location`/`season`, or another `ValueError` from preprocessing |
| 404 | Not found | `GET /api/results/{run_id}` with an unknown id |
| 422 | Validation error | Pydantic rejects the request body (e.g. missing `total_land_ha`, negative `budget_rs`) |
| 500 | Internal server error | Uncaught exception |

---

## Running the API

```bash
# Install dependencies
pip install -r requirements.txt      # add --break-system-packages on some Linux setups

# Start the server
uvicorn app.main:app --reload --port 8000

# Open Swagger UI
open http://localhost:8000/docs
```
