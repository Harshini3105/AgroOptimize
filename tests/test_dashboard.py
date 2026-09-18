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
from app.services import results_store

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
        # Covers both the live Open-Meteo path (richer WMO-code-derived
        # conditions) and the CSV-derived fallback (rainy/partly_cloudy_day/
        # sunny only) -- whichever one actually ran on this machine/network.
        assert body["condition"] in {
            "sunny", "partly_cloudy_day", "cloud", "foggy", "rainy", "thunderstorm", "ac_unit",
        }
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


class TestLiveWeatherParsing:
    """Exercises ds._get_weather_live's parsing against a hand-built
    response matching Open-Meteo's documented JSON shape (see
    https://open-meteo.com/en/docs), via a mocked requests.get -- this
    verifies the parsing logic itself works, independent of whether this
    machine actually has outbound internet access to Open-Meteo."""

    @staticmethod
    def _fake_response(weather_code=0):
        class _FakeResp:
            def raise_for_status(self):
                pass

            def json(self):
                return {
                    "current": {"temperature_2m": 31.4, "relative_humidity_2m": 62, "weather_code": weather_code},
                    "daily": {
                        "time": ["2026-08-13", "2026-08-14", "2026-08-15", "2026-08-16", "2026-08-17", "2026-08-18"],
                        "weather_code": [weather_code, 1, 3, 61, 95, 0],
                        "temperature_2m_max": [34.0, 33.5, 32.0, 30.1, 29.5, 33.0],
                        "temperature_2m_min": [24.0, 23.5, 23.0, 22.5, 22.0, 24.0],
                        "precipitation_sum": [0.0, 0.0, 1.2, 12.5, 30.0, 0.0],
                    },
                }
        return _FakeResp()

    def test_parses_current_and_forecast(self, monkeypatch):
        import requests
        from app.services import dashboard_service as ds

        monkeypatch.setattr(requests, "get", lambda *a, **k: self._fake_response(weather_code=0))
        result = ds._get_weather_live("Coimbatore")

        assert result["location"] == "Coimbatore"
        assert result["temp"] == 31
        assert result["condition"] == "sunny"
        assert result["source"] == "Live (Open-Meteo)"
        assert len(result["forecast"]) == 5
        # weather codes [1, 3, 61, 95, 0] for the 5 forecast days (index 1-5)
        assert [f["icon"] for f in result["forecast"]] == [
            "partly_cloudy_day", "cloud", "rainy", "thunderstorm", "sunny",
        ]
        assert result["forecast"][0]["temp"] == "34° / 24°"

    def test_falls_back_to_csv_on_network_error(self, monkeypatch):
        import requests
        from app.services import dashboard_service as ds

        def _raise(*a, **k):
            raise requests.exceptions.ConnectionError("no network in this environment")

        monkeypatch.setattr(requests, "get", _raise)
        result = ds.get_weather("coimbatore")
        assert result["source"] == "Historical CSV average (live weather unavailable)"
        assert result["condition"] in {"rainy", "partly_cloudy_day", "sunny"}


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
    def test_returns_200_with_valid_shape(self, district):
        r = client.get(f"/api/history/{district}")
        assert r.status_code == 200
        history = r.json()["history"]
        assert isinstance(history, list)
        for entry in history:
            assert entry["location"] == config.LOCATIONS[DISTRICTS.index(district)]
            assert "t/ha" in entry["target_yield"] or entry["target_yield"] == "--"

    @pytest.mark.parametrize("district", DISTRICTS)
    def test_no_client_id_returns_empty_history(self, district):
        # By product decision (2026-09-07 UX pass -- see
        # dashboard_service.get_history's docstring and
        # agrooptimize-frontend-hardcoded-data-audit.md), History shows
        # ONLY a visitor's own real saved runs, with no CSV-derived filler
        # rows for a district nobody has actually run yet. A request with
        # no client_id (a brand-new browser) can never match any saved
        # run's client_id, so it must get back an empty list, not a 404 or
        # placeholder rows -- this replaces the old
        # test_returns_200_and_nonempty_history, which predated that UX
        # pass and asserted the opposite (nonempty, "Estimated" rows).
        r = client.get(f"/api/history/{district}")
        assert r.status_code == 200
        assert r.json()["history"] == []

    def test_no_client_id_never_shows_a_completed_run(self):
        # There are no user accounts in this project -- a request with no
        # client_id (a brand new browser, or the demo/seed runs saved
        # before client_id existed) must never surface someone else's
        # saved run as if it were this visitor's own completed history.
        # (Vacuously true today since history is empty without a
        # client_id -- kept as an explicit regression guard in case that
        # ever changes.)
        history = client.get("/api/history/coimbatore").json()["history"]
        assert all(h["is_estimated"] for h in history)
        assert all(h["status"] != "Completed" for h in history)

    def test_estimated_entries_have_no_fuzzy_weights(self):
        history = client.get("/api/history/coimbatore").json()["history"]
        for h in history:
            if h["is_estimated"]:
                assert h["fuzzy_weights"] is None


class TestHistoryClientScoping:
    """A saved run only ever appears as "Completed" history for the
    client_id that generated it (see dashboard_service.get_history) --
    there are no real user accounts, so this client_id is the only thing
    standing between a fresh visitor and seeing someone else's (or old
    demo/seed data's) saved runs as their own history."""

    @staticmethod
    def _fake_summary(client_id):
        return {
            "run_id": "coimbatore_kharif_2023_fake",
            "location": "Coimbatore",
            "season": "Kharif",
            "year": 2023,
            "preference": "balanced",
            "saved_at": "2026-01-01T00:00:00+00:00",
            "n_plans": 3,
            "client_id": client_id,
        }

    @staticmethod
    def _fake_record():
        return {
            "region_profile": {"location": "Coimbatore", "season": "Kharif", "year": 2023},
            "plans": [{"area_ha": [2.0, 3.0], "yield_tonnes": 25.0, "cost_rs": 60000.0}],
            "fuzzy_assessment": {
                "yield_confidence": 0.7,
                "irrigation_risk": 0.3,
                "rainfall_label": "Normal",
                "water_label": "Adequate",
                "soil_label": "Good",
            },
        }

    def _patch_store(self, monkeypatch, client_id_on_disk):
        monkeypatch.setattr(
            results_store, "list_saved_runs", lambda **k: [self._fake_summary(client_id_on_disk)]
        )
        monkeypatch.setattr(results_store, "load_run", lambda *a, **k: self._fake_record())

    def test_no_client_id_hides_the_run(self, monkeypatch):
        self._patch_store(monkeypatch, client_id_on_disk="visitor-abc")
        history = ds.get_history("coimbatore")["history"]
        assert all(h["is_estimated"] for h in history)

    def test_mismatched_client_id_hides_the_run(self, monkeypatch):
        self._patch_store(monkeypatch, client_id_on_disk="visitor-abc")
        history = ds.get_history("coimbatore", client_id="someone-else")["history"]
        assert all(h["is_estimated"] for h in history)

    def test_matching_client_id_shows_the_run_as_completed(self, monkeypatch):
        self._patch_store(monkeypatch, client_id_on_disk="visitor-abc")
        history = ds.get_history("coimbatore", client_id="visitor-abc")["history"]
        completed = [h for h in history if not h["is_estimated"]]
        assert len(completed) == 1
        assert completed[0]["status"] == "Completed"
        assert completed[0]["target_yield"] == "5.0 t/ha"

    def test_endpoint_accepts_client_id_query_param(self, monkeypatch):
        self._patch_store(monkeypatch, client_id_on_disk="visitor-abc")
        r = client.get("/api/history/coimbatore", params={"client_id": "visitor-abc"})
        assert r.status_code == 200
        completed = [h for h in r.json()["history"] if not h["is_estimated"]]
        assert len(completed) == 1


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
