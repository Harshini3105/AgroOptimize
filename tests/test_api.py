"""
Test suite for the FastAPI REST endpoints (app/main.py).

Covers all 6 routes against the real request/response schemas in
app/schemas.py -- field names here (total_land_ha, budget_rs,
min_env_impact, ...) are load-bearing, not descriptive: get them wrong and
FastAPI/Pydantic will 422 the request.

Author: Garudammagari Sreenithya (CB.SC.U4CSE23061)
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------

class TestHealthEndpoint:

    def test_health_returns_200(self):
        assert client.get("/health").status_code == 200

    def test_health_returns_status_ok(self):
        assert client.get("/health").json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# GET /api/catalog
# ---------------------------------------------------------------------------

class TestCatalogEndpoint:

    def test_catalog_returns_200(self):
        assert client.get("/api/catalog").status_code == 200

    def test_catalog_has_all_locations(self):
        data = client.get("/api/catalog").json()
        assert set(data["locations"]) == set(config.LOCATIONS)

    def test_catalog_has_all_seasons(self):
        data = client.get("/api/catalog").json()
        assert set(data["seasons"]) == set(config.AG_SEASONS)

    def test_catalog_has_crops_by_season(self):
        data = client.get("/api/catalog").json()
        assert "crops_by_season" in data
        assert set(data["crops_by_season"].keys()) == set(config.AG_SEASONS)


# ---------------------------------------------------------------------------
# GET /api/region-profile
# ---------------------------------------------------------------------------

class TestRegionProfileEndpoint:

    def test_region_profile_returns_200(self):
        r = client.get("/api/region-profile", params={"location": "Coimbatore", "season": "Kharif"})
        assert r.status_code == 200

    def test_region_profile_includes_fuzzy_assessment(self):
        r = client.get(
            "/api/region-profile",
            params={"location": "Salem", "season": "Kharif", "year": 2023},
        )
        data = r.json()
        assert "fuzzy_assessment" in data
        assert 0.0 <= data["fuzzy_assessment"]["yield_confidence"] <= 1.0
        assert 0.0 <= data["fuzzy_assessment"]["irrigation_risk"] <= 1.0

    def test_region_profile_rejects_unknown_location(self):
        r = client.get("/api/region-profile", params={"location": "Nowhere", "season": "Kharif"})
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# POST /api/farm-plans
# ---------------------------------------------------------------------------

class TestFarmPlansEndpoint:

    def _payload(self, location="Coimbatore", **overrides):
        payload = {
            "location": location,
            "season": "Kharif",
            "year": 2023,
            "total_land_ha": 5,
            "budget_rs": 200000,
            "preference": "balanced",
            # fast settings so the suite stays quick, same knobs test_pipeline.py uses
            "pop_size": config.NSGA2_FAST_POP_SIZE,
            "n_gen": config.NSGA2_FAST_N_GEN,
            "save_results": False,
        }
        payload.update(overrides)
        return payload

    def test_farm_plans_returns_200_with_plans(self):
        r = client.post("/api/farm-plans", json=self._payload())
        assert r.status_code == 200
        assert len(r.json()["plans"]) > 0

    def test_farm_plans_top_plan_allocation_sums_to_100_percent(self):
        r = client.post("/api/farm-plans", json=self._payload())
        top_plan = r.json()["plans"][0]
        assert sum(top_plan["allocation_percent"]) == pytest.approx(100.0, abs=0.01)

    @pytest.mark.parametrize("location", config.LOCATIONS)
    def test_farm_plans_works_for_every_location(self, location):
        r = client.post("/api/farm-plans", json=self._payload(location=location))
        assert r.status_code == 200, f"Failed for {location}: {r.text}"
        assert len(r.json()["plans"]) > 0

    def test_farm_plans_missing_required_field_is_422(self):
        # total_land_ha is required (gt=0) -- omitting it must fail
        # validation, not silently fall back to a default.
        bad_payload = self._payload()
        del bad_payload["total_land_ha"]
        r = client.post("/api/farm-plans", json=bad_payload)
        assert r.status_code == 422

    def test_farm_plans_unknown_location_is_400(self):
        r = client.post("/api/farm-plans", json=self._payload(location="Nowhere"))
        assert r.status_code == 400

    def test_farm_plans_respects_budget_constraint(self):
        # 180k is tight-but-feasible for Coimbatore/5ha at the fast pop/gen
        # settings used here (checked empirically -- 150k returns zero
        # feasible plans at these settings and would make this test
        # vacuously true).
        r = client.post("/api/farm-plans", json=self._payload(budget_rs=180_000))
        body = r.json()
        assert len(body["plans"]) > 0
        for plan in body["plans"]:
            assert plan["cost_rs"] <= 180_000 + 1e-6

    def test_farm_plans_max_yield_preference_beats_min_cost_on_yield(self):
        max_yield = client.post(
            "/api/farm-plans", json=self._payload(preference="max_yield")
        ).json()["plans"][0]
        min_cost = client.post(
            "/api/farm-plans", json=self._payload(preference="min_cost")
        ).json()["plans"][0]
        assert max_yield["yield_tonnes"] >= min_cost["yield_tonnes"]


# ---------------------------------------------------------------------------
# GET /api/results, GET /api/results/{run_id}
# ---------------------------------------------------------------------------

class TestResultsEndpoints:

    def test_results_list_returns_200_and_a_list(self):
        r = client.get("/api/results")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_results_detail_returns_404_for_unknown_run_id(self):
        r = client.get("/api/results/not-a-real-run-id")
        assert r.status_code == 404
