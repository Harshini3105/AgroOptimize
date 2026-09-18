"""
Test suite for data loading and preprocessing
(app/data/loader.py, app/data/preprocessing.py).

Validates raw CSV loading/caching and the RegionSeasonProfile pipeline
that turns those CSVs into fuzzy/NSGA-II-ready inputs.

Author: Garudammagari Sreenithya (CB.SC.U4CSE23061)
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from app import config
from app.data import loader
from app.data import preprocessing as pp


# ---------------------------------------------------------------------------
# Raw CSV presence -- the 16 files the whole pipeline depends on
# ---------------------------------------------------------------------------

class TestRawCsvFilesExist:

    def test_all_sixteen_csv_files_exist(self):
        missing = []
        for location in config.LOCATIONS:
            for kind in config.DATASET_KINDS:
                path = config.RAW_DATA_DIR / f"{location.lower()}_{kind}.csv"
                if not path.exists():
                    missing.append(path.name)
        assert missing == [], f"Missing CSV files: {missing}"


# ---------------------------------------------------------------------------
# app/data/loader.py
# ---------------------------------------------------------------------------

class TestLoader:

    def test_load_all_returns_all_four_kinds(self):
        data = loader.load_all()
        assert set(data.keys()) == {"crop", "land", "rainfall", "water"}
        for df in data.values():
            assert len(df) > 0

    def test_load_all_concatenates_every_location(self):
        data = loader.load_all()
        assert set(data["crop"]["Location"].unique()) == set(config.LOCATIONS)

    def test_available_locations_matches_config(self):
        assert loader.available_locations() == config.LOCATIONS

    def test_available_seasons_matches_config(self):
        assert loader.available_seasons() == config.AG_SEASONS

    def test_available_years_covers_2020_to_2023(self):
        years = loader.available_years("crop")
        assert {2020, 2021, 2022, 2023}.issubset(set(years))

    def test_load_all_is_cached(self):
        # lru_cache(maxsize=1) -- the same object should come back twice.
        first = loader.load_all()
        second = loader.load_all()
        assert first is second

    def test_clear_cache_forces_a_fresh_load(self):
        first = loader.load_all()
        loader.clear_cache()
        second = loader.load_all()
        assert first is not second
        assert first["crop"].equals(second["crop"])  # same data, new object


# ---------------------------------------------------------------------------
# app/data/preprocessing.py -- catalog
# ---------------------------------------------------------------------------

class TestCatalog:

    def test_list_catalog_shape(self):
        catalog = pp.list_catalog()
        assert set(catalog["locations"]) == set(config.LOCATIONS)
        assert set(catalog["seasons"]) == set(config.AG_SEASONS)
        assert len(catalog["years"]) >= 1
        assert set(catalog["crops_by_season"].keys()) == set(config.AG_SEASONS)

    def test_catalog_crops_by_season_are_non_empty(self):
        catalog = pp.list_catalog()
        for season, crops in catalog["crops_by_season"].items():
            assert len(crops) > 0, f"No crops listed for {season}"


# ---------------------------------------------------------------------------
# app/data/preprocessing.py -- RegionSeasonProfile
# ---------------------------------------------------------------------------

class TestRegionSeasonProfile:

    @pytest.mark.parametrize("location", config.LOCATIONS)
    @pytest.mark.parametrize("season", config.AG_SEASONS)
    def test_profile_builds_for_every_location_and_season(self, location, season):
        profile = pp.get_region_season_profile(location, season, year=2023)
        assert profile.location == location
        assert profile.season == season
        assert profile.year == 2023
        assert len(profile.candidate_crops) >= config.MIN_CANDIDATE_CROPS

    def test_profile_defaults_to_latest_year_when_year_is_none(self):
        profile = pp.get_region_season_profile("Coimbatore", "Kharif", year=None)
        assert profile.year == max(loader.available_years("crop"))

    def test_unknown_location_raises_value_error(self):
        with pytest.raises(ValueError):
            pp.get_region_season_profile("Chennai", "Kharif")

    def test_unknown_season_raises_value_error(self):
        with pytest.raises(ValueError):
            pp.get_region_season_profile("Coimbatore", "Monsoon")

    def test_soil_fertility_index_in_range(self):
        profile = pp.get_region_season_profile("Coimbatore", "Kharif", year=2023)
        assert 0 <= profile.soil.fertility_index <= 100

    def test_effective_rainfall_is_non_negative(self):
        profile = pp.get_region_season_profile("Salem", "Kharif", year=2023)
        assert profile.rainfall.effective_rainfall_mm >= 0

    def test_candidate_crops_sorted_by_historical_revenue_descending(self):
        profile = pp.get_region_season_profile("Coimbatore", "Kharif", year=2023)
        revenues = [c.revenue_rs_lakh_hist for c in profile.candidate_crops]
        assert revenues == sorted(revenues, reverse=True)

    def test_max_candidate_crops_is_respected(self):
        profile = pp.get_region_season_profile(
            "Coimbatore", "Kharif", year=2023, max_candidate_crops=3
        )
        assert len(profile.candidate_crops) == 3


# ---------------------------------------------------------------------------
# app/data/preprocessing.py -- soil fertility index formula
# ---------------------------------------------------------------------------

class TestSoilFertilityIndexFormula:

    def test_optimal_ph_high_carbon_high_npk_scores_near_maximum(self):
        score = pp.compute_soil_fertility_index(
            avg_ph=6.5, organic_carbon_percent=1.0, n_status="High", p_status="High", k_status="High"
        )
        assert score > 95

    def test_poor_ph_low_carbon_low_npk_scores_near_minimum(self):
        score = pp.compute_soil_fertility_index(
            avg_ph=9.0, organic_carbon_percent=0.0, n_status="Low", p_status="Low", k_status="Low"
        )
        assert score < 40

    def test_score_is_clamped_to_0_100(self):
        score = pp.compute_soil_fertility_index(
            avg_ph=20.0, organic_carbon_percent=10.0, n_status="High", p_status="High", k_status="High"
        )
        assert 0.0 <= score <= 100.0


# ---------------------------------------------------------------------------
# app/data/preprocessing.py -- normalized_snapshot
# ---------------------------------------------------------------------------

class TestNormalizedSnapshot:

    @pytest.mark.parametrize("location", config.LOCATIONS)
    def test_all_normalized_fields_in_unit_range(self, location):
        profile = pp.get_region_season_profile(location, "Kharif", year=2023)
        snapshot = pp.normalized_snapshot(profile)
        for key, value in snapshot.items():
            assert 0.0 <= value <= 1.0, f"{key} out of [0,1] range: {value}"
