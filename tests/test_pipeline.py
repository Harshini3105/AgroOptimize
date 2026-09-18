"""
End-to-end and unit tests for the AgroOptimize pipeline.

Run with:
    pytest -v

Optimisation-stage tests use a small pop_size/n_gen (see
app.config.NSGA2_FAST_*) purely so the suite runs in a couple of seconds;
the API defaults to the paper-matching full settings (pop=80, gen=200).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app import config
from app.data import preprocessing as pp
from app.fuzzy import engine as fz
from app.optimization.nsga2_runner import extract_convergence_history, extract_pareto_plans, run_nsga2
from app.optimization.problem import FarmPlanProblem
from app.decision import ranking
from app.schemas import FarmPlanRequest
from app.services import results_store
from app.services.plan_service import generate_farm_plans


# ---------------------------------------------------------------------------
# Data layer
# ---------------------------------------------------------------------------

def test_catalog_has_all_locations():
    catalog = pp.list_catalog()
    assert set(catalog["locations"]) == set(config.LOCATIONS)
    assert set(catalog["seasons"]) == set(config.AG_SEASONS)
    assert len(catalog["years"]) >= 1


@pytest.mark.parametrize("location", config.LOCATIONS)
@pytest.mark.parametrize("season", config.AG_SEASONS)
def test_region_profile_builds_for_every_location_and_season(location, season):
    profile = pp.get_region_season_profile(location, season)
    assert profile.location == location
    assert profile.season == season
    assert len(profile.candidate_crops) >= config.MIN_CANDIDATE_CROPS
    assert 0 <= profile.soil.fertility_index <= 100
    assert profile.rainfall.effective_rainfall_mm >= 0


def test_region_profile_rejects_unknown_location():
    with pytest.raises(ValueError):
        pp.get_region_season_profile("Chennai", "Kharif")


def test_region_profile_rejects_unknown_season():
    with pytest.raises(ValueError):
        pp.get_region_season_profile("Coimbatore", "Monsoon")


# ---------------------------------------------------------------------------
# Fuzzy layer
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "rainfall_dev,storage,soil_fert",
    [(-55, 5, 10), (0, 50, 50), (55, 95, 95), (-100, -10, 150)],  # last row exercises clipping
)
def test_fuzzy_outputs_always_in_unit_range(rainfall_dev, storage, soil_fert):
    result = fz.evaluate_uncertainty(rainfall_dev, storage, soil_fert)
    assert 0.0 <= result.yield_confidence <= 1.0
    assert 0.0 <= result.irrigation_risk <= 1.0


def test_severe_drought_yields_lower_confidence_than_favourable_conditions():
    drought = fz.evaluate_uncertainty(-55, 5, 20)
    favourable = fz.evaluate_uncertainty(10, 80, 80)
    assert drought.yield_confidence < favourable.yield_confidence
    assert drought.irrigation_risk > favourable.irrigation_risk


def test_high_rainfall_dependency_crop_penalised_more_than_low_dependency():
    base_conf, irr_risk = 0.8, 0.8
    high_dep = fz.crop_yield_confidence(base_conf, irr_risk, "High")
    low_dep = fz.crop_yield_confidence(base_conf, irr_risk, "Very Low")
    assert high_dep < low_dep


# ---------------------------------------------------------------------------
# Optimisation layer
# ---------------------------------------------------------------------------

@pytest.fixture
def small_problem():
    profile = pp.get_region_season_profile("Coimbatore", "Kharif", year=2023)
    assessment = fz.evaluate_uncertainty(
        profile.rainfall.avg_deviation_percent,
        profile.water.avg_storage_percent,
        profile.soil.fertility_index,
    )
    return FarmPlanProblem(profile, assessment, total_land_ha=5.0, budget_rs=200_000)


def test_nsga2_produces_a_valid_pareto_front(small_problem):
    result = run_nsga2(small_problem, pop_size=config.NSGA2_FAST_POP_SIZE, n_gen=config.NSGA2_FAST_N_GEN, seed=7)
    plans = extract_pareto_plans(result, small_problem)
    assert len(plans) > 0
    for plan in plans:
        assert plan.feasible  # budget constraint respected
        assert plan.yield_tonnes >= 0
        assert plan.cost_rs >= 0
        assert plan.water_liters >= 0
        assert plan.env_impact_score >= 0
        # allocation fractions must sum to ~1 (land can't exceed 100%)
        assert abs(sum(plan.allocation_fraction) - 1.0) < 1e-6
        # every area must fit inside the farmer's total land
        assert sum(plan.area_ha) <= small_problem.total_land_ha + 1e-6


def test_nsga2_is_reasonably_fast_at_full_paper_settings(small_problem):
    import time

    t0 = time.time()
    result = run_nsga2(small_problem, pop_size=config.NSGA2_POP_SIZE, n_gen=config.NSGA2_N_GEN, seed=1)
    elapsed = time.time() - t0
    plans = extract_pareto_plans(result, small_problem)
    assert len(plans) > 0
    assert elapsed < 15.0  # generous ceiling; observed ~0.5s in dev


def test_unconstrained_problem_has_no_budget_and_still_solves():
    profile = pp.get_region_season_profile("Salem", "Summer")
    assessment = fz.evaluate_uncertainty(
        profile.rainfall.avg_deviation_percent,
        profile.water.avg_storage_percent,
        profile.soil.fertility_index,
    )
    problem = FarmPlanProblem(profile, assessment, total_land_ha=2.0, budget_rs=None)
    assert problem.n_ieq_constr == 0
    result = run_nsga2(problem, pop_size=config.NSGA2_FAST_POP_SIZE, n_gen=config.NSGA2_FAST_N_GEN, seed=3)
    plans = extract_pareto_plans(result, problem)
    assert len(plans) > 0
    assert all(p.feasible for p in plans)


# ---------------------------------------------------------------------------
# Decision / ranking layer
# ---------------------------------------------------------------------------

def test_ranking_orders_by_composite_score_and_labels_trade_offs(small_problem):
    result = run_nsga2(small_problem, pop_size=config.NSGA2_FAST_POP_SIZE, n_gen=config.NSGA2_FAST_N_GEN, seed=5)
    raw_plans = [p for p in extract_pareto_plans(result, small_problem) if p.feasible]
    conf_map = dict(zip(small_problem.crop_vec.names, small_problem.crop_vec.crop_yield_confidence.tolist()))

    ranked = ranking.rank_plans(raw_plans, conf_map, preference="balanced")
    assert len(ranked) > 0
    scores = [rp.composite_score for rp in ranked]
    assert scores == sorted(scores, reverse=True)
    assert [rp.rank for rp in ranked] == list(range(1, len(ranked) + 1))
    for rp in ranked:
        assert rp.trade_off_summary  # non-empty string
        assert rp.confidence_label in {"Low", "Moderate", "High"}


def test_max_yield_preference_favours_higher_yield_than_min_cost_preference(small_problem):
    result = run_nsga2(small_problem, pop_size=config.NSGA2_FAST_POP_SIZE, n_gen=config.NSGA2_FAST_N_GEN, seed=9)
    raw_plans = [p for p in extract_pareto_plans(result, small_problem) if p.feasible]
    conf_map = dict(zip(small_problem.crop_vec.names, small_problem.crop_vec.crop_yield_confidence.tolist()))

    by_yield = ranking.rank_plans(raw_plans, conf_map, preference="max_yield")
    by_cost = ranking.rank_plans(raw_plans, conf_map, preference="min_cost")
    assert by_yield[0].yield_tonnes >= by_cost[0].yield_tonnes


def test_filter_plans_respects_hard_limits(small_problem):
    result = run_nsga2(small_problem, pop_size=config.NSGA2_FAST_POP_SIZE, n_gen=config.NSGA2_FAST_N_GEN, seed=11)
    raw_plans = extract_pareto_plans(result, small_problem)
    filtered = ranking.filter_plans(raw_plans, max_cost=150_000)
    assert all(p.cost_rs <= 150_000 for p in filtered)


# ---------------------------------------------------------------------------
# Full service / API
# ---------------------------------------------------------------------------

def test_generate_farm_plans_end_to_end():
    # save_results=False here: this test is about pipeline correctness, not
    # persistence (that gets its own tests below, writing to a tmp dir).
    request = FarmPlanRequest(
        location="Pollachi",
        season="Kharif",
        total_land_ha=4.0,
        budget_rs=180_000,
        preference="balanced",
        pop_size=config.NSGA2_FAST_POP_SIZE,
        n_gen=config.NSGA2_FAST_N_GEN,
        save_results=False,
    )
    response = generate_farm_plans(request)
    assert response["meta"]["n_plans_returned"] > 0
    assert response["fuzzy_assessment"]["yield_confidence"] is not None
    assert response["region_profile"]["location"] == "Pollachi"
    assert response["run_id"] is None
    assert response["saved_files"] is None
    assert response["convergence_history"] == []
    top_plan = response["plans"][0]
    assert top_plan["rank"] == 1
    assert sum(top_plan["allocation_percent"]) == pytest.approx(100.0, abs=0.01)


def test_api_endpoints_via_testclient():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    assert client.get("/health").status_code == 200
    assert client.get("/api/catalog").status_code == 200

    r = client.get("/api/region-profile", params={"location": "Coimbatore", "season": "Kharif"})
    assert r.status_code == 200

    r = client.post(
        "/api/farm-plans",
        json={
            "location": "Coimbatore",
            "season": "Kharif",
            "total_land_ha": 5,
            "budget_rs": 200000,
            "pop_size": config.NSGA2_FAST_POP_SIZE,
            "n_gen": config.NSGA2_FAST_N_GEN,
            "save_results": False,
        },
    )
    assert r.status_code == 200
    assert len(r.json()["plans"]) > 0

    bad = client.post("/api/farm-plans", json={"location": "Nowhere", "season": "Kharif", "total_land_ha": 1})
    assert bad.status_code == 400


# ---------------------------------------------------------------------------
# Convergence history (the "evolutionary algorithm" now tracks its own
# progress across generations, not just the final Pareto front)
# ---------------------------------------------------------------------------

def test_convergence_history_empty_without_tracking(small_problem):
    result = run_nsga2(small_problem, pop_size=config.NSGA2_FAST_POP_SIZE, n_gen=config.NSGA2_FAST_N_GEN, seed=1)
    assert extract_convergence_history(result) == []


def test_convergence_history_tracks_every_generation(small_problem):
    n_gen = config.NSGA2_FAST_N_GEN
    result = run_nsga2(
        small_problem, pop_size=config.NSGA2_FAST_POP_SIZE, n_gen=n_gen, seed=1, track_history=True
    )
    history = extract_convergence_history(result)
    assert len(history) == n_gen
    assert [h["generation"] for h in history] == list(range(1, n_gen + 1))
    for h in history:
        assert h["population_size"] == config.NSGA2_FAST_POP_SIZE
        assert h["best_yield_tonnes"] >= 0
        assert 0.0 <= h["hypervolume"] <= 2.0  # normalised space, ref point (1.1,1.1,1.1,1.1)
    # hypervolume shouldn't collapse to zero by the end of the run
    assert history[-1]["hypervolume"] > 0


# ---------------------------------------------------------------------------
# Results persistence ("store the results in a file")
# ---------------------------------------------------------------------------

def test_generate_farm_plans_saves_results_to_disk(tmp_path):
    request = FarmPlanRequest(
        location="Erode",
        season="Kharif",
        total_land_ha=3.0,
        budget_rs=150_000,
        pop_size=config.NSGA2_FAST_POP_SIZE,
        n_gen=config.NSGA2_FAST_N_GEN,
        save_results=True,
    )
    response = generate_farm_plans(request, results_dir=tmp_path)

    assert response["run_id"] is not None
    assert response["run_id"].startswith("erode_kharif_")
    assert len(response["convergence_history"]) == config.NSGA2_FAST_N_GEN

    saved = response["saved_files"]
    for key in ("json_path", "plans_csv_path", "convergence_csv_path", "convergence_plot_path"):
        assert saved[key] is not None
        path = Path(saved[key])
        assert path.exists(), f"{key} was not written to disk: {path}"
        assert path.stat().st_size > 0

    # the saved JSON round-trips through results_store.load_run
    reloaded = results_store.load_run(response["run_id"], out_dir=tmp_path)
    assert reloaded is not None
    assert reloaded["region_profile"]["location"] == "Erode"
    assert len(reloaded["convergence_history"]) == config.NSGA2_FAST_N_GEN

    # and shows up in the run listing
    runs = results_store.list_saved_runs(out_dir=tmp_path)
    assert any(r["run_id"] == response["run_id"] for r in runs)


def test_list_saved_runs_empty_for_missing_dir(tmp_path):
    assert results_store.list_saved_runs(out_dir=tmp_path / "does-not-exist") == []


def test_load_run_returns_none_for_unknown_id(tmp_path):
    assert results_store.load_run("not-a-real-run", out_dir=tmp_path) is None
