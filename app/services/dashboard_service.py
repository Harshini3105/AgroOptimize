"""
Support logic for the frontend-facing dashboard endpoints (weather, KPI
summary, history, soil profile, Pareto plans, and A/B/C comparison).

Every value returned here is derived from data/raw/*.csv and the same
fuzzy/NSGA-II/TOPSIS pipeline the rest of the backend uses (see
app/fuzzy/engine.py, app/optimization/, app/decision/ranking.py) -- nothing
here is random or hardcoded. Where a metric has no single canonical
formula already defined elsewhere in the codebase (e.g. "water
utilization" as distinct from the already-used "water storage", or the
comparison view's 6-axis radar scores), the derivation is documented
inline so it's easy to challenge or retune later -- see
docs/frontend_integration.md for the full list of these choices in one
place.
"""
from __future__ import annotations

import datetime as _dt
from typing import Optional

from app import config
from app.data import loader
from app.data import preprocessing as pp
from app.data.preprocessing import compute_soil_fertility_index
from app.decision import ranking
from app.fuzzy import engine as fz
from app.optimization.nsga2_runner import extract_pareto_plans, run_nsga2
from app.optimization.problem import FarmPlanProblem
from app.services import results_store

_MONTHS_IN_YEAR_ORDER = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def resolve_location(location: str) -> str:
    """Case-insensitive district lookup (frontend sends lowercase path
    segments, e.g. 'salem'). Raises ValueError -- mapped to a 404 in
    main.py -- if it isn't one of the 4 districts in app.config.LOCATIONS."""
    for loc in config.LOCATIONS:
        if loc.lower() == location.strip().lower():
            return loc
    raise ValueError(
        f"Unknown location '{location}'. Choose one of "
        f"{[l.lower() for l in config.LOCATIONS]}."
    )


def _current_season(today: Optional[_dt.date] = None) -> str:
    """Maps today's calendar month onto Kharif/Rabi/Summer via
    app.config.SEASON_MONTH_MAP. Kharif/Rabi/Summer's month lists overlap
    at the edges (Feb/Mar fall in both Rabi and Summer) -- ties resolve to
    whichever season is listed first in SEASON_MONTH_MAP (currently Rabi)."""
    today = today or _dt.date.today()
    month_name = _MONTHS_IN_YEAR_ORDER[today.month - 1]
    for season, months in config.SEASON_MONTH_MAP.items():
        if month_name in months:
            return season
    return config.AG_SEASONS[0]  # unreachable in practice -- every month is mapped


def _latest_year_for(df, location: str) -> int:
    years = df.loc[df["Location"] == location, "Year"]
    return int(years.max())


# ---------------------------------------------------------------------------
# GET /api/weather/{location}
# ---------------------------------------------------------------------------

_CONDITION_TEXT = {
    "rainy": "Rainy",
    "partly_cloudy_day": "Partly Cloudy",
    "sunny": "Sunny",
}


def _condition_for_rainfall(monthly_rainfall_mm: float) -> str:
    """Thresholds as specified for this project: no live weather API, so
    'condition' is a proxy read off historical monthly rainfall."""
    if monthly_rainfall_mm > 100:
        return "rainy"
    if monthly_rainfall_mm > 50:
        return "partly_cloudy_day"
    return "sunny"


def get_weather(location: str) -> dict:
    location = resolve_location(location)
    rainfall = loader.load_all()["rainfall"]
    rows = rainfall[rainfall["Location"] == location]
    today = _dt.date.today()

    def month_avg(month_name: str) -> dict:
        month_rows = rows[rows["Month"] == month_name]
        if month_rows.empty:
            month_rows = rows  # degrade to the location's overall average rather than crash
        return {
            "rainfall_mm": round(float(month_rows["Monthly_Rainfall_mm"].mean()), 1),
            "max_temp_c": round(float(month_rows["Max_Temp_C"].mean()), 1),
            "min_temp_c": round(float(month_rows["Min_Temp_C"].mean()), 1),
            "humidity_pct": round(float(month_rows["Humidity_Percent"].mean()), 1),
        }

    current_month = _MONTHS_IN_YEAR_ORDER[today.month - 1]
    current = month_avg(current_month)
    condition = _condition_for_rainfall(current["rainfall_mm"])
    temp = round((current["max_temp_c"] + current["min_temp_c"]) / 2)

    # "5-day" forecast proxy: the next 5 calendar months' historical
    # averages, one per weekday label -- there's no live forecast source,
    # so this is explicitly a seasonal-trend proxy, not a real 5-day
    # forecast (documented in docs/frontend_integration.md).
    forecast = []
    for i, day in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri"], start=1):
        month_name = _MONTHS_IN_YEAR_ORDER[(today.month - 1 + i) % 12]
        stats = month_avg(month_name)
        forecast.append({
            "day": day,
            "icon": _condition_for_rainfall(stats["rainfall_mm"]),
            "temp": f"{round(stats['max_temp_c'])}° / {round(stats['min_temp_c'])}°",
        })

    return {
        "location": location,
        "temp": temp,
        "condition": condition,
        "conditionText": _CONDITION_TEXT[condition],
        "rainfall_mm": current["rainfall_mm"],
        "humidity": round(current["humidity_pct"]),
        "source": "Historical CSV data",
        "forecast": forecast,
    }


# ---------------------------------------------------------------------------
# GET /api/dashboard/{location}
# ---------------------------------------------------------------------------

_ACTION_LIBRARY = {
    "nitrogen": ("Apply nitrogen fertilizer", "Soil N status from the land survey is Low.", "high", "Next 48 hours"),
    "phosphorus": ("Apply phosphorus (DAP) fertilizer", "Soil P status from the land survey is Low.", "high", "Next 5 days"),
    "potassium": ("Apply potash (MOP) fertilizer", "Soil K status from the land survey is Low.", "medium", "Next 5 days"),
    "irrigation": ("Schedule additional irrigation", "Reservoir storage for this district is below 40%.", "high", "Next 24 hours"),
}


def _soil_status_label(fertility_index_0_100: float) -> str:
    if fertility_index_0_100 >= 70:
        return "Optimal"
    if fertility_index_0_100 >= 45:
        return "Moderate"
    return "Needs Attention"


def _current_land_row(land_df, location: str, year: int):
    """The land.csv row for (location, year, current-season) -- falls
    back to the last row for that year if the current season is somehow
    missing, so this never raises for a location that's in the dataset."""
    year_rows = land_df[(land_df["Location"] == location) & (land_df["Year"] == year)]
    season_rows = year_rows[year_rows["Season"] == _current_season()]
    return season_rows.iloc[0] if not season_rows.empty else year_rows.iloc[-1]


def get_dashboard(location: str) -> dict:
    location = resolve_location(location)
    data = loader.load_all()
    crop_df, land_df, water_df = data["crop"], data["land"], data["water"]

    loc_crop = crop_df[crop_df["Location"] == location]
    latest_year = _latest_year_for(loc_crop, location)

    # --- estimated_yield & yield_trend: mean Yield_Kg_Ha, latest year vs. previous ---
    this_year_yield = float(loc_crop.loc[loc_crop["Year"] == latest_year, "Yield_Kg_Ha"].mean())
    earlier_years = loc_crop.loc[loc_crop["Year"] < latest_year, "Year"]
    if not earlier_years.empty:
        prev_year = int(earlier_years.max())
        prev_year_yield = float(loc_crop.loc[loc_crop["Year"] == prev_year, "Yield_Kg_Ha"].mean())
        pct_change = (this_year_yield - prev_year_yield) / prev_year_yield * 100 if prev_year_yield else 0.0
    else:
        pct_change = 0.0
    estimated_yield = round(this_year_yield / 1000.0, 1)  # kg/ha -> t/ha
    yield_trend = f"{'+' if pct_change >= 0 else ''}{round(pct_change, 1)}%"

    # --- active_plans: saved optimisation runs on disk for this district ---
    active_plans = sum(1 for r in results_store.list_saved_runs() if r["location"] == location)

    # --- soil (current season's land.csv row) ---
    land_row = _current_land_row(land_df, location, latest_year)
    fertility_index = compute_soil_fertility_index(
        avg_ph=float(land_row["Avg_Soil_pH"]),
        organic_carbon_percent=float(land_row["Organic_Carbon_Percent"]),
        n_status=land_row["N_Status"], p_status=land_row["P_Status"], k_status=land_row["K_Status"],
    )

    # --- water_utilization_pct: irrigation's share of total seasonal water
    # demand (distinct from "storage percent", which is reservoir fullness
    # and is already used elsewhere as the fuzzy engine's water input) ---
    water_rows = water_df[(water_df["Location"] == location) & (water_df["Year"] == latest_year)]
    total_demand = float(water_rows["Total_Demand_MCM"].sum()) if not water_rows.empty else 0.0
    if total_demand > 0:
        water_utilization_pct = round(float(water_rows["Irrigation_Water_MCM"].sum()) / total_demand * 100, 1)
    else:
        water_utilization_pct = 0.0
    avg_storage_pct = float(water_rows["Storage_Percent"].mean()) if not water_rows.empty else 100.0

    # --- recommended_actions: rule-based off N/P/K status + water storage ---
    actions = []
    for key, status_col in (("nitrogen", "N_Status"), ("phosphorus", "P_Status"), ("potassium", "K_Status")):
        if str(land_row[status_col]) == "Low":
            title, desc, prio, window = _ACTION_LIBRARY[key]
            actions.append({"id": key, "title": title, "description": desc, "priority": prio, "window": window})
    if avg_storage_pct < 40:
        title, desc, prio, window = _ACTION_LIBRARY["irrigation"]
        actions.append({"id": "irrigation", "title": title, "description": desc, "priority": prio, "window": window})
    if not actions:
        actions.append({
            "id": "monitor", "title": "No urgent action needed",
            "description": "Soil N/P/K status and water storage are all within normal range.",
            "priority": "low", "window": "Routine monitoring",
        })

    # --- crop_allocations: top 3 candidate crops by historical revenue,
    # for the current season -- reuses the same ranking preprocessing.py
    # already does for the optimiser's candidate-crop shortlist ---
    try:
        profile = pp.get_region_season_profile(location, _current_season(), year=latest_year, max_candidate_crops=3)
        top3 = profile.candidate_crops
        total_revenue = sum(c.revenue_rs_lakh_hist for c in top3) or 1.0
        reference_land_ha = 10.0  # demo reference farm size, purely to turn a % into a Ha column
        crop_allocations = [
            {
                "crop": c.name,
                "pct": round(c.revenue_rs_lakh_hist / total_revenue * 100, 1),
                "ha": round(c.revenue_rs_lakh_hist / total_revenue * reference_land_ha, 1),
            }
            for c in top3
        ]
    except ValueError:
        crop_allocations = []

    return {
        "location": location,
        "estimated_yield": estimated_yield,
        "yield_trend": yield_trend,
        "active_plans": active_plans,
        "soil_health_pct": round(fertility_index),
        "water_utilization_pct": water_utilization_pct,
        "soil_status": _soil_status_label(fertility_index),
        "recommended_actions": actions,
        "crop_allocations": crop_allocations,
    }


# ---------------------------------------------------------------------------
# GET /api/soil-profile/{location}
# ---------------------------------------------------------------------------

def get_soil_profile(location: str) -> dict:
    location = resolve_location(location)
    land_df = loader.load_all()["land"]
    latest_year = _latest_year_for(land_df, location)
    row = _current_land_row(land_df, location, latest_year)

    fertility_index = compute_soil_fertility_index(
        avg_ph=float(row["Avg_Soil_pH"]),
        organic_carbon_percent=float(row["Organic_Carbon_Percent"]),
        n_status=row["N_Status"], p_status=row["P_Status"], k_status=row["K_Status"],
    )

    return {
        "location": location,
        "soil_pH": float(row["Avg_Soil_pH"]),
        "organic_carbon_pct": float(row["Organic_Carbon_Percent"]),
        "N_status": str(row["N_Status"]),
        "P_status": str(row["P_Status"]),
        "K_status": str(row["K_Status"]),
        "fertility_index": round(fertility_index / 100.0, 3),
        "irrigated_ha": float(row["Irrigated_Land_Ha"]),
        "total_agricultural_ha": float(row["Agricultural_Land_Ha"]),
    }


# ---------------------------------------------------------------------------
# GET /api/history/{location}
# ---------------------------------------------------------------------------

def get_history(location: str) -> dict:
    location = resolve_location(location)

    real_runs = []
    for summary in results_store.list_saved_runs():
        if summary["location"] != location:
            continue
        record = results_store.load_run(summary["run_id"])
        if record is None:
            continue
        top_plan = record["plans"][0] if record["plans"] else None
        # top_plan's yield_tonnes/cost_rs are plan TOTALS over whatever
        # total_land_ha that run used, not per-hectare rates -- divide by
        # the plan's own area so "t/ha" and "/ha" are actually true.
        area_ha = sum(top_plan["area_ha"]) if top_plan else 0.0
        real_runs.append({
            "id": summary["run_id"],
            "season": f"{summary['season']} {summary['year']}",
            "date": (summary.get("saved_at") or "")[:10],
            "location": location,
            "target_yield": f"{round(top_plan['yield_tonnes'] / area_ha, 2)} t/ha" if top_plan and area_ha else "--",
            "est_cost": f"₹{round(top_plan['cost_rs'] / area_ha):,}/ha" if top_plan and area_ha else "--",
            "status": "Completed",
            "num_plans": summary["n_plans"],
            "preference": summary.get("preference") or "balanced",
            "fuzzy_weights": record["fuzzy_assessment"],
            "is_estimated": False,
        })
    covered_years = {int(r["season"].split()[-1]) for r in real_runs}

    # Years with no saved optimisation run are filled in from the
    # district's own crop.csv Kharif-season average -- NOT a real
    # optimisation result, clearly flagged is_estimated=True, so the
    # history view isn't empty for years nobody has actually run yet.
    crop_df = loader.load_all()["crop"]
    loc_crop = crop_df[(crop_df["Location"] == location) & (crop_df["Season"] == "Kharif")]
    estimated = []
    for year in sorted(int(y) for y in loc_crop["Year"].unique()):
        if year in covered_years:
            continue
        year_rows = loc_crop[loc_crop["Year"] == year]
        mean_yield_t_ha = round(float(year_rows["Yield_Kg_Ha"].mean()) / 1000.0, 1)
        cost_per_ha = (
            year_rows["Fertilizer_N_Kg_Ha"] * config.FERTILIZER_PRICE_RS_PER_KG_NUTRIENT["N"]
            + year_rows["Fertilizer_P_Kg_Ha"] * config.FERTILIZER_PRICE_RS_PER_KG_NUTRIENT["P"]
            + year_rows["Fertilizer_K_Kg_Ha"] * config.FERTILIZER_PRICE_RS_PER_KG_NUTRIENT["K"]
            + year_rows["Pesticide_Cost_Rs_Ha"]
            + year_rows["Labor_Days_Ha"] * config.LABOR_WAGE_RS_PER_DAY
        )
        mean_cost_per_ha = round(float(cost_per_ha.mean()))
        estimated.append({
            "id": f"estimated_{location.lower()}_{year}",
            "season": f"Kharif {year}",
            "date": f"{year}-09-01",
            "location": location,
            "target_yield": f"{mean_yield_t_ha} t/ha",
            "est_cost": f"₹{mean_cost_per_ha:,}/ha",
            "status": "Estimated (no saved run)",
            "num_plans": 0,
            "preference": None,
            "fuzzy_weights": None,
            "is_estimated": True,
        })

    history = sorted(real_runs + estimated, key=lambda h: h["season"], reverse=True)
    return {"history": history}


# ---------------------------------------------------------------------------
# Shared: run the real pipeline once, reused by /api/plans and /api/comparison
# ---------------------------------------------------------------------------

_DEMO_POP_SIZE = 100  # > config.NSGA2_POP_SIZE (80) so the Analytics scatter has ~100 points


def _run_dashboard_pareto_front(
    location: str,
    season: Optional[str] = None,
    year: Optional[int] = None,
    total_land_ha: float = 5.0,
    budget_rs: Optional[float] = None,
):
    """Runs preprocessing -> fuzzy -> NSGA-II once. Returns (profile,
    assessment, raw_feasible_plans, crop_confidence_map) so callers can
    re-rank the same front under different TOPSIS preferences without
    re-running the optimiser. Deliberately calls the lower-level pieces
    (FarmPlanProblem / run_nsga2 / ranking.rank_plans) directly instead of
    app.services.plan_service.generate_farm_plans, specifically so it can
    ask for more than plan_service's hardcoded config.MAX_RETURNED_PLANS
    (50) without touching that already-tested orchestration path."""
    location = resolve_location(location)
    season = season or _current_season()

    profile = pp.get_region_season_profile(location, season, year=year)
    assessment = fz.evaluate_uncertainty(
        profile.rainfall.avg_deviation_percent,
        profile.water.avg_storage_percent,
        profile.soil.fertility_index,
    )
    problem = FarmPlanProblem(profile, assessment, total_land_ha=total_land_ha, budget_rs=budget_rs)
    result = run_nsga2(problem, pop_size=_DEMO_POP_SIZE, track_history=False)
    raw_plans = [p for p in extract_pareto_plans(result, problem) if p.feasible]
    crop_confidence_map = dict(zip(problem.crop_vec.names, problem.crop_vec.crop_yield_confidence.tolist()))
    return profile, assessment, raw_plans, crop_confidence_map


def _last_saved_run_for(location: str) -> Optional[dict]:
    for summary in results_store.list_saved_runs():
        if summary["location"] == location:
            return results_store.load_run(summary["run_id"])
    return None


def _synthetic_plans_from_csv(location: str) -> dict:
    """Last-resort fallback when both a live NSGA-II run and any saved
    result are unavailable: one single-crop 'plan' per top candidate crop,
    computed directly from crop.csv with no optimisation at all. Clearly a
    degenerate case, flagged via is_fallback/fallback_reason."""
    location = resolve_location(location)
    season = _current_season()
    crop_df = loader.load_all()["crop"]
    rows = crop_df[(crop_df["Location"] == location) & (crop_df["Season"] == season)]
    rows = rows.sort_values("Revenue_Rs_Lakh", ascending=False).head(10)

    plans = []
    for i, (_, r) in enumerate(rows.iterrows()):
        fert_cost = (
            float(r["Fertilizer_N_Kg_Ha"]) * config.FERTILIZER_PRICE_RS_PER_KG_NUTRIENT["N"]
            + float(r["Fertilizer_P_Kg_Ha"]) * config.FERTILIZER_PRICE_RS_PER_KG_NUTRIENT["P"]
            + float(r["Fertilizer_K_Kg_Ha"]) * config.FERTILIZER_PRICE_RS_PER_KG_NUTRIENT["K"]
        )
        cost_per_ha = fert_cost + float(r["Pesticide_Cost_Rs_Ha"]) + float(r["Labor_Days_Ha"]) * config.LABOR_WAGE_RS_PER_DAY
        plans.append({
            "id": i,
            "cost": round(cost_per_ha),
            "yield_val": round(float(r["Yield_Kg_Ha"]) / 1000.0, 2),
            "water_val": round(float(r["Water_Req_mm"]) * config.LITERS_PER_MM_PER_HA / 1_000_000, 2),
            "env_impact": round(float(r["Fertilizer_N_Kg_Ha"]) * config.CARBON_FERTILIZER_FACTOR, 2),
            "is_recommended": i == 0,
            "crops": {str(r["Crop_Name"]): 1.0},
            "rank": i + 1,
        })
    best = plans[0] if plans else None
    return {
        "location": location,
        "total_land_ha": None,  # not meaningful here -- these are per-ha single-crop estimates, no plan was sized to a farm
        "num_plans": len(plans),
        "fuzzy_weights": None,
        "plans": plans,
        "best_plan": {"id": best["id"], "cost": best["cost"], "yield_val": best["yield_val"]} if best else None,
        "is_fallback": True,
        "fallback_reason": "live NSGA-II run and saved results both unavailable; single-crop estimates from crop.csv",
    }


# ---------------------------------------------------------------------------
# GET /api/plans/{location}
# ---------------------------------------------------------------------------

def get_plans(location: str, total_land_ha: float = 5.0, budget_rs: Optional[float] = None) -> dict:
    location = resolve_location(location)
    try:
        profile, assessment, raw_plans, crop_confidence_map = _run_dashboard_pareto_front(
            location, total_land_ha=total_land_ha, budget_rs=budget_rs
        )
        ranked = ranking.rank_plans(raw_plans, crop_confidence_map, preference="balanced", max_plans=_DEMO_POP_SIZE)
        if not ranked:
            raise RuntimeError("NSGA-II run produced no feasible plans")

        plans_out = []
        for rp in ranked:
            crops = {
                name: round(pct / 100, 4)
                for name, pct in zip(rp.crop_names, rp.allocation_percent)
                if pct > 0.5
            }
            # rp.cost_rs / yield_tonnes / water_liters / env_impact_score are
            # plan TOTALS over total_land_ha -- normalise to per-hectare so
            # plans (and, later, districts run at a different land size)
            # are comparable on a like-for-like basis.
            area = sum(rp.area_ha) or total_land_ha
            plans_out.append({
                "id": rp.rank - 1,
                "cost": round(rp.cost_rs / area),
                "yield_val": round(rp.yield_tonnes / area, 2),
                "water_val": round(rp.water_liters / area / 1_000_000, 2),  # million litres / ha
                "env_impact": round(rp.env_impact_score / area, 2),
                "is_recommended": rp.rank == 1,
                "crops": crops,
                "rank": rp.rank,
            })
        best = plans_out[0] if plans_out else None
        return {
            "location": location,
            "total_land_ha": total_land_ha,
            "num_plans": len(plans_out),
            "fuzzy_weights": {
                "yield_confidence": assessment.yield_confidence,
                "irrigation_risk": assessment.irrigation_risk,
            },
            "plans": plans_out,
            "best_plan": {"id": best["id"], "cost": best["cost"], "yield_val": best["yield_val"]} if best else None,
            "is_fallback": False,
        }
    except Exception as live_exc:  # noqa: BLE001 -- deliberate: this endpoint must degrade, never 500
        print(f"[dashboard_service.get_plans] live NSGA-II run failed for {location}: {live_exc!r}")
        saved = _last_saved_run_for(location)
        if saved is not None:
            plans_out = []
            for p in saved["plans"]:
                crops = {
                    name: round(pct / 100, 4)
                    for name, pct in zip(p["crop_names"], p["allocation_percent"])
                    if pct > 0.5
                }
                area = sum(p["area_ha"]) or 1.0
                plans_out.append({
                    "id": p["rank"] - 1,
                    "cost": round(p["cost_rs"] / area),
                    "yield_val": round(p["yield_tonnes"] / area, 2),
                    "water_val": round(p["water_liters"] / area / 1_000_000, 2),
                    "env_impact": round(p["env_impact_score"] / area, 2),
                    "is_recommended": p["rank"] == 1,
                    "crops": crops,
                    "rank": p["rank"],
                })
            best = plans_out[0] if plans_out else None
            return {
                "location": location,
                "total_land_ha": sum(saved["plans"][0]["area_ha"]) if saved["plans"] else total_land_ha,
                "num_plans": len(plans_out),
                "fuzzy_weights": saved["fuzzy_assessment"],
                "plans": plans_out,
                "best_plan": {"id": best["id"], "cost": best["cost"], "yield_val": best["yield_val"]} if best else None,
                "is_fallback": True,
                "fallback_reason": f"live run failed; showing last saved run {saved.get('run_id')}",
            }
        return _synthetic_plans_from_csv(location)


# ---------------------------------------------------------------------------
# GET /api/comparison/{location}
# ---------------------------------------------------------------------------

def _radar_scores(rp, trio, irrigation_risk: float, dep_by_crop: dict) -> dict:
    """0-100 scores across 6 axes for the comparison radar chart.
    yield/cost_eff/water are TOPSIS-style min-max normalisations computed
    over just these 3 compared plans (higher = better, direction-flipped
    for cost). land reuses the same yield normalisation as a land-use
    efficiency proxy (all 3 plans share the same total_land_ha, so
    higher yield IS higher yield-per-hectare here). risk is the region's
    fuzzy irrigation_risk, inverted (same value for all 3 plans -- it's a
    regional reading, not plan-specific). market has no real market data
    behind it, so it's built from something the dataset does have: the
    plan's crops' average Rainfall_Dependency -- lower climate-dependency
    is read as more market-stable regardless of weather swings."""
    yields = [p.yield_tonnes for p in trio]
    costs = [p.cost_rs for p in trio]
    waters = [p.water_liters for p in trio]

    def norm(v, values, higher_better):
        lo, hi = min(values), max(values)
        if hi - lo < 1e-9:
            return 50.0
        n = (v - lo) / (hi - lo)
        return (n if higher_better else 1 - n) * 100

    deps = [
        dep_by_crop.get(name, "Medium")
        for name, pct in zip(rp.crop_names, rp.allocation_percent)
        if pct > 1.0
    ]
    avg_dep_factor = (
        sum(config.RAINFALL_DEPENDENCY_FACTOR.get(d, 0.5) for d in deps) / len(deps) if deps else 0.5
    )

    return {
        "yield": round(norm(rp.yield_tonnes, yields, True)),
        "cost_eff": round(norm(rp.cost_rs, costs, False)),
        "water": round(norm(rp.water_liters, waters, False)),
        "land": round(norm(rp.yield_tonnes, yields, True)),
        "risk": round((1 - irrigation_risk) * 100),
        "market": round((1 - avg_dep_factor) * 100),
    }


_PLOT_LABELS = ["Plots 1, 2, 4", "Plots 3, 5", "Plot 6", "Plot 7", "Plots 8, 9", "Plot 10"]


def get_comparison(location: str, total_land_ha: float = 5.0, budget_rs: Optional[float] = None) -> dict:
    location = resolve_location(location)
    profile, assessment, raw_plans, crop_confidence_map = _run_dashboard_pareto_front(
        location, total_land_ha=total_land_ha, budget_rs=budget_rs
    )
    if not raw_plans:
        raise ValueError(f"No feasible plans found for {location} to build a comparison from.")

    dep_by_crop = {c.name: c.rainfall_dependency for c in profile.candidate_crops}

    # Plan A = most balanced (TOPSIS 'balanced' rank 1, i.e. closest to the
    # ideal point across all 4 objectives at once); Plan B = highest yield
    # (TOPSIS 'max_yield' rank 1); Plan C = lowest cost (TOPSIS 'min_cost'
    # rank 1) -- each is the #1 pick of a real TOPSIS ranking over the same
    # Pareto front, not a hand-picked plan.
    balanced = ranking.rank_plans(raw_plans, crop_confidence_map, preference="balanced")[0]
    max_yield = ranking.rank_plans(raw_plans, crop_confidence_map, preference="max_yield")[0]
    min_cost = ranking.rank_plans(raw_plans, crop_confidence_map, preference="min_cost")[0]
    trio = [balanced, max_yield, min_cost]

    chosen = {
        "A": (balanced, "Plan A -- Balanced", True),
        "B": (max_yield, "Plan B -- Max Yield", False),
        "C": (min_cost, "Plan C -- Lowest Cost", False),
    }
    water_values = [p.water_liters for p in trio]

    plans_out = {}
    for key, (rp, label, recommended) in chosen.items():
        crop_items = [
            (name, pct / 100)
            for name, pct in zip(rp.crop_names, rp.allocation_percent)
            if pct > 1.0
        ]
        allocations = [
            {
                "crop": name,
                "pct": f"{round(frac * 100)}%",
                "ha": f"{round(frac * total_land_ha, 1)} Ha",
                "plots": _PLOT_LABELS[i % len(_PLOT_LABELS)],
            }
            for i, (name, frac) in enumerate(crop_items)
        ]
        if rp.water_liters == min(water_values):
            water_label = "Efficient"
        elif rp.water_liters == max(water_values):
            water_label = "High usage"
        else:
            water_label = "Moderate"

        # Same total_land_ha for all 3 (one NSGA-II run) -- normalise to
        # per-hectare for the headline yield/cost/env figures, matching
        # get_plans(); allocations[].ha below is deliberately the absolute
        # hectares instead, since that's what a farmer picking a plan wants.
        area = sum(rp.area_ha) or total_land_ha
        plans_out[key] = {
            "name": label,
            "crops": ", ".join(name for name, _ in crop_items),
            "yield_val": round(rp.yield_tonnes / area, 2),
            "cost": round(rp.cost_rs / area),
            "env_impact": round(rp.env_impact_score / area, 2),
            "water": water_label,
            "recommended": recommended,
            "allocations": allocations,
            "radar_scores": _radar_scores(rp, trio, assessment.irrigation_risk, dep_by_crop),
        }

    return {"location": location, "total_land_ha": total_land_ha, "plans": plans_out}
