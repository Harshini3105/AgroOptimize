"""
Test suite for the frontend-facing dashboard endpoints added for
stitch_agrooptimize_app: /api/weather, /api/dashboard, /api/history,
/api/soil-profile, /api/plans, /api/comparison (app/services/dashboard_service.py,
wired up in app/main.py).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app
from app.services import dashboard_service as ds

client = TestClient(app)

DISTRICTS = [loc.lower() for loc in config.LOCATIONS]


class TestResolveLocation:

    @pytest.mark.parametrize("raw,expected", [
        ("coimbatore", "Coimbatore"),
        ("SALEM", "Salem"),
        (" Erode ", "Erode"),
        ("Pollachi", "Pollachi"),
    ])
    def test_case_and_whitespace_insensitive(self, raw, expected):
        assert ds.resolve_location(raw) == expected

    def test_unknown_district_raises(self):
        with pytest.raises(ValueError):
            ds.resolve_location("chennai")


class TestWeatherEndpoint:

    @pytest.mark.parametrize("district", DISTRICTS)
    def test_returns_200_with_expected_shape(self, district):
        r = client.get(f"/api/weather/{district}")
        assert r.status_code == 200
        body = r.json()
        for key in ("location", "temp", "condition", "conditionText", "rainfall_mm", "humidity", "source", "forecast"):
            assert key in body
        assert body["condition"] in {"rainy", "partly_cloudy_day", "sunny"}
        assert len(body["forecast"]) == 5
        assert all(set(f.keys()) == {"day", "icon", "temp"} for f in body["forecast"])

    def test_differs_between_districts(self):
        coimbatore = client.get("/api/weather/coimbatore").json()
        salem = client.get("/api/weather/salem").json()
        assert coimbatore["location"] != salem["location"]
        # not asserting the *values* differ (two districts could coincide by
        # chance) -- but they must be independently derived, i.e. each
        # response's location must match what was requested
        assert coimbatore["location"] == "Coimbatore"
        assert salem["location"] == "Salem"

    def test_unknown_district_is_404(self):
        r = client.get("/api/weather/chennai")
        assert r.status_code == 404


class TestDashboardEndpoint:

    @pytest.mark.parametrize("district", DISTRICTS)
    def test_returns_200_with_expected_shape(self, district):
        r = client.get(f"/api/dashboard/{district}")
        assert r.status_code == 200
        body = r.json()
        for key in (
            "location", "estimated_yield", "yield_trend", "active_plans",
            "soil_health_pct", "water_utilization_pct", "soil_status",
            "recommended_actions", "crop_allocations",
        ):
            assert key in body
        assert 0 <= body["soil_health_pct"] <= 100
        assert 0 <= body["water_utilization_pct"] <= 100
        assert body["soil_status"] in {"Optimal", "Moderate", "Needs Attention"}
        assert isinstance(body["recommended_actions"], list) and len(body["recommended_actions"]) >= 1
        for action in body["recommended_actions"]:
            assert {"id", "title", "description", "priority", "window"} <= set(action.keys())

    def test_crop_allocations_percentages_are_plausible(self):
        body = client.get("/api/dashboard/coimbatore").json()
        if body["crop_allocations"]:
            total_pct = sum(c["pct"] for c in body["crop_allocations"])
            assert 0 < total_pct <= 100.01


class TestSoilProfileEndpoint:

    @pytest.mark.parametrize("district", DISTRICTS)
    def test_returns_200_with_expected_shape(self, district):
        r = client.get(f"/api/soil-profile/{district}")
        assert r.status_code == 200
        body = r.json()
        for key in (
            "location", "soil_pH", "organic_carbon_pct", "N_status", "P_status",
            "K_status", "fertility_index", "irrigated_ha", "total_agricultural_ha",
        ):
            assert key in body
        assert 0.0 <= body["fertility_index"] <= 1.0
        assert body["N_status"] in {"Low", "Medium", "High"}
        assert body["irrigated_ha"] <= body["total_agricultural_ha"]


class TestHistoryEndpoint:

    @pytest.mark.parametrize("district", DISTRICTS)
    def test_returns_200_and_nonempty_history(self, district):
        r = client.get(f"/api/history/{district}")
        assert r.status_code == 200
        history = r.json()["history"]
        assert len(history) > 0
        for entry in history:
            assert entry["location"] == config.LOCATIONS[DISTRICTS.index(district)]
            assert "t/ha" in entry["target_yield"] or entry["target_yield"] == "--"

    def test_real_saved_run_is_not_flagged_estimated(self):
        # every district has exactly one real saved run at the time these
        # tests were written (see docs/results/); assert at least one
        # non-estimated entry exists for Coimbatore specifically.
        history = client.get("/api/history/coimbatore").json()["history"]
        assert any(not h["is_estimated"] for h in history)

    def test_estimated_entries_have_no_fuzzy_weights(self):
        history = client.get("/api/history/coimbatore").json()["history"]
        for h in history:
            if h["is_estimated"]:
                assert h["fuzzy_weights"] is None


class TestPlansEndpoint:

    @pytest.mark.parametrize("district", DISTRICTS)
    def test_returns_200_with_positive_plan_count(self, district):
        r = client.get(f"/api/plans/{district}")
        assert r.status_code == 200
        body = r.json()
        assert body["num_plans"] > 0
        assert body["is_fallback"] is False
        assert body["fuzzy_weights"] is not None
        assert 0.0 <= body["fuzzy_weights"]["yield_confidence"] <= 1.0

    def test_plan_fields_are_positive_and_per_hectare_scaled(self):
        body = client.get("/api/plans/coimbatore").json()
        for plan in body["plans"][:5]:
            assert plan["cost"] > 0
            assert plan["yield_val"] > 0
            assert plan["water_val"] >= 0
            assert sum(plan["crops"].values()) <= 1.01
        # sanity check the per-hectare fix: yield_val should be a plausible
        # tonnes/ha figure (single digits to low tens), not a 5ha plan total
        assert all(plan["yield_val"] < 200 for plan in body["plans"])

    def test_exactly_one_recommended_plan(self):
        body = client.get("/api/plans/coimbatore").json()
        recommended = [p for p in body["plans"] if p["is_recommended"]]
        assert len(recommended) == 1
        assert recommended[0]["rank"] == 1

    def test_best_plan_matches_rank_one(self):
        body = client.get("/api/plans/coimbatore").json()
        rank_one = next(p for p in body["plans"] if p["rank"] == 1)
        assert body["best_plan"]["id"] == rank_one["id"]
        assert body["best_plan"]["cost"] == rank_one["cost"]


class TestComparisonEndpoint:

    @pytest.mark.parametrize("district", DISTRICTS)
    def test_returns_200_with_three_plans(self, district):
        r = client.get(f"/api/comparison/{district}")
        assert r.status_code == 200
        plans = r.json()["plans"]
        assert set(plans.keys()) == {"A", "B", "C"}

    def test_plan_b_has_highest_yield_and_plan_c_lowest_cost(self):
        plans = client.get("/api/comparison/coimbatore").json()["plans"]
        assert plans["B"]["yield_val"] >= plans["A"]["yield_val"]
        assert plans["B"]["yield_val"] >= plans["C"]["yield_val"]
        assert plans["C"]["cost"] <= plans["A"]["cost"]
        assert plans["C"]["cost"] <= plans["B"]["cost"]

    def test_only_plan_a_is_recommended(self):
        plans = client.get("/api/comparison/coimbatore").json()["plans"]
        assert plans["A"]["recommended"] is True
        assert plans["B"]["recommended"] is False
        assert plans["C"]["recommended"] is False

    def test_radar_scores_in_0_100_range(self):
        plans = client.get("/api/comparison/coimbatore").json()["plans"]
        for plan in plans.values():
            for axis, score in plan["radar_scores"].items():
                assert 0 <= score <= 100, f"{axis} out of range: {score}"

    def test_allocations_sum_to_full_land_area(self):
        body = client.get("/api/comparison/coimbatore").json()
        total_land = body["total_land_ha"]
        for plan in body["plans"].values():
            ha_sum = sum(float(a["ha"].replace(" Ha", "")) for a in plan["allocations"])
            assert ha_sum == pytest.approx(total_land, abs=0.15)

    def test_unknown_district_is_404(self):
        r = client.get("/api/comparison/chennai")
        assert r.status_code == 404
