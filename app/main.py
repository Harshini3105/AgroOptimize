"""
AgroOptimize backend API.

A fuzzy-evolutionary (NSGA-II) decision support system for agricultural
farming under uncertainty. See notes/methodology_notes.md for the full
write-up and notes/viva_prep.md for a Q&A-style reference.

Run locally:
    uvicorn app.main:app --reload --port 8000

Then open http://127.0.0.1:8000/docs for interactive Swagger docs.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.data import preprocessing as pp
from app.schemas import CatalogOut, FarmPlanRequest, FarmPlanResponse, SavedRunSummaryOut

app = FastAPI(
    title="AgroOptimize API",
    description=(
        "Fuzzy-evolutionary decision support system for agricultural farming "
        "under uncertainty. Combines a Mamdani fuzzy inference engine "
        "(rainfall / water / soil uncertainty) with NSGA-II multi-objective "
        "optimisation (yield, cost, water use, environmental impact) to "
        "produce a ranked set of Pareto-optimal farming plans."
    ),
    version="0.1.0",
)

# CORS for the Vite/React frontend (src: stitch_agrooptimize_app). Must be
# added before any route definitions -- it isn't order-sensitive for
# @app.get/@app.post itself, but keeping it first makes it apply to every
# route below without having to think about it again.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/catalog", response_model=CatalogOut)
def get_catalog():
    """What locations / years / seasons / crops the dataset covers."""
    return pp.list_catalog()


@app.get("/api/region-profile")
def get_region_profile(location: str, season: str, year: int | None = None):
    """Preprocessing + fuzzy stages only -- useful for inspecting/demoing
    the data pipeline without running the (slower) optimisation stage."""
    try:
        profile = pp.get_region_season_profile(location=location, season=season, year=year)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    from app.fuzzy import engine as fz

    assessment = fz.evaluate_uncertainty(
        profile.rainfall.avg_deviation_percent,
        profile.water.avg_storage_percent,
        profile.soil.fertility_index,
    )
    return {
        "location": profile.location,
        "year": profile.year,
        "season": profile.season,
        "soil": vars(profile.soil),
        "rainfall": vars(profile.rainfall),
        "water": vars(profile.water),
        "candidate_crops": [c.name for c in profile.candidate_crops],
        "normalized_snapshot": pp.normalized_snapshot(profile),
        "fuzzy_assessment": vars(assessment),
    }


@app.post("/api/farm-plans", response_model=FarmPlanResponse)
def post_farm_plans(request: FarmPlanRequest):
    """Full pipeline: preprocessing -> fuzzy -> NSGA-II -> ranked plans.

    When `save_results` (default true) is set on the request, the run is
    also written to disk under results/ -- see GET /api/results and
    GET /api/results/{run_id} to browse/retrieve saved runs afterwards.
    """
    from app.services.plan_service import generate_farm_plans

    try:
        return generate_farm_plans(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/results", response_model=list[SavedRunSummaryOut])
def list_results():
    """Every run that has been saved to disk so far (most recent first)."""
    from app.services import results_store

    return results_store.list_saved_runs()


@app.get("/api/results/{run_id}", response_model=FarmPlanResponse)
def get_result(run_id: str):
    """Full saved record for one past run, including its convergence
    history -- exactly what was written to results/<run_id>.json."""
    from app.services import results_store

    record = results_store.load_run(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"No saved run with id '{run_id}'.")
    return record


# ---------------------------------------------------------------------------
# Frontend-facing dashboard endpoints (stitch_agrooptimize_app).
#
# These all take a lowercase district path segment (coimbatore / erode /
# salem / pollachi) rather than the Title-case `location` the rest of the
# API uses, to match how the frontend derives a district from the user's
# saved farm location. See app/services/dashboard_service.py for the
# derivation of every field -- everything here is computed from
# data/raw/*.csv and the real fuzzy/NSGA-II/TOPSIS pipeline, not hardcoded.
# ---------------------------------------------------------------------------


@app.get("/api/weather/{location}")
def get_weather(location: str):
    """Weather proxy derived from historical rainfall.csv (no live weather
    API in this project) -- current month's average rainfall/temperature/
    humidity, plus a 5-value seasonal-trend forecast."""
    from app.services import dashboard_service as ds

    try:
        return ds.get_weather(location)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/dashboard/{location}")
def get_dashboard(location: str):
    """Dashboard KPI summary: yield/trend, active plans, soil health, water
    utilisation, recommended actions (from N/P/K status), and top-3
    crop allocation -- all derived from crop.csv/land.csv/water_availability.csv."""
    from app.services import dashboard_service as ds

    try:
        return ds.get_dashboard(location)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/history/{location}")
def get_history(location: str):
    """Past optimisation runs for a district: real saved runs from
    results/, plus CSV-derived (clearly flagged `is_estimated`) filler for
    any year that doesn't have a saved run yet."""
    from app.services import dashboard_service as ds

    try:
        return ds.get_history(location)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/soil-profile/{location}")
def get_soil_profile_by_district(location: str):
    """Soil snapshot for the farm-map section, read directly from the
    district's land.csv (current season's row)."""
    from app.services import dashboard_service as ds

    try:
        return ds.get_soil_profile(location)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/plans/{location}")
def get_plans_by_district(location: str, total_land_ha: float = 5.0, budget_rs: float | None = None):
    """Up to ~100 Pareto-optimal plans for AnalyticsView's scatter plot.
    Tries a live NSGA-II run first; falls back to the last saved result for
    this district, then to CSV-derived single-crop estimates, if that
    fails -- see dashboard_service.get_plans, this endpoint never 500s."""
    from app.services import dashboard_service as ds

    try:
        return ds.get_plans(location, total_land_ha=total_land_ha, budget_rs=budget_rs)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/comparison/{location}")
def get_comparison_by_district(location: str, total_land_ha: float = 5.0, budget_rs: float | None = None):
    """Plan A (balanced) / B (max yield) / C (lowest cost) for
    ComparisonView -- each the #1 pick of a real TOPSIS ranking over the
    same live Pareto front, not hand-picked."""
    from app.services import dashboard_service as ds

    try:
        return ds.get_comparison(location, total_land_ha=total_land_ha, budget_rs=budget_rs)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
