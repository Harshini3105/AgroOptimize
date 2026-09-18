"""
Test suite for the Mamdani fuzzy inference engine (app/fuzzy/engine.py).

Validates output ranges, rule-base directional behaviour, the per-crop
rainfall-dependency adjustment, and integration with real region profiles.

Every assertion in this file was checked against the actual engine output
before being committed (see docs/fuzzy_rules.md for the full rule base and
membership-function reference this file is testing against).

Author: Vennela Harshini (CB.SC.U4CSE23455)
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from app.data import preprocessing as pp
from app.fuzzy import engine as fz
from app.fuzzy.engine import UncertaintyAssessment


# ---------------------------------------------------------------------------
# Output range / shape
# ---------------------------------------------------------------------------

class TestFuzzyOutputRanges:
    """evaluate_uncertainty() must always return values inside [0, 1], even
    at or beyond the membership functions' universe boundaries (rainfall_dev
    is defined over [-60, 60], water_storage/soil_fert over [0, 100])."""

    @pytest.mark.parametrize(
        "rainfall_dev,water_storage,soil_fert",
        [
            (-60, 0, 0),        # worst corner of every universe
            (60, 100, 100),     # best corner of every universe
            (0, 50, 50),        # dead centre
            (-15, 20, 25),      # sits on a boundary between adjacent sets
            (-120, -20, 150),   # out-of-range inputs -- must clip, not raise
        ],
    )
    def test_outputs_always_in_unit_range(self, rainfall_dev, water_storage, soil_fert):
        result = fz.evaluate_uncertainty(rainfall_dev, water_storage, soil_fert)
        assert isinstance(result, UncertaintyAssessment)
        assert 0.0 <= result.yield_confidence <= 1.0
        assert 0.0 <= result.irrigation_risk <= 1.0

    def test_extreme_out_of_range_inputs_are_clipped_not_rejected(self):
        """Readings far outside any sensible physical range shouldn't raise
        -- evaluate_uncertainty clips to [-60,60]/[0,100]/[0,100] first."""
        result = fz.evaluate_uncertainty(-1000, -1000, 1000)
        assert 0.0 <= result.yield_confidence <= 1.0
        assert 0.0 <= result.irrigation_risk <= 1.0

    def test_dominant_labels_are_valid_categories(self):
        result = fz.evaluate_uncertainty(-55, 5, 20)
        assert result.rainfall_label in {"deficit", "normal", "surplus"}
        assert result.water_label in {"low", "medium", "high"}
        assert result.soil_label in {"poor", "medium", "good"}


# ---------------------------------------------------------------------------
# Rule-base behaviour (directional sanity checks against the 14 Mamdani rules)
# ---------------------------------------------------------------------------

class TestFuzzyRuleBaseBehaviour:

    def test_drought_and_low_storage_gives_high_risk_low_confidence(self):
        # rainfall_dev="deficit", water_storage="low" -> rule 1:
        # [irrigation_risk-high, yield_conf-low]
        result = fz.evaluate_uncertainty(
            rainfall_deviation_percent=-55,
            water_storage_percent=5,
            soil_fertility_index=15,
        )
        assert result.irrigation_risk > 0.5
        assert result.yield_confidence < 0.5

    def test_normal_rainfall_with_medium_storage_gives_high_confidence_low_risk(self):
        # rainfall_dev="normal", water_storage="medium" -> rule 5:
        # [irrigation_risk-low, yield_conf-high]
        result = fz.evaluate_uncertainty(
            rainfall_deviation_percent=0,
            water_storage_percent=55,
            soil_fertility_index=70,
        )
        assert result.yield_confidence > 0.5
        assert result.irrigation_risk < 0.5

    def test_drought_scores_worse_than_favourable_conditions(self):
        drought = fz.evaluate_uncertainty(-55, 5, 20)
        favourable = fz.evaluate_uncertainty(10, 80, 80)
        assert drought.yield_confidence < favourable.yield_confidence
        assert drought.irrigation_risk > favourable.irrigation_risk

    def test_good_soil_alone_lifts_yield_confidence(self):
        # rules: soil_fert-good -> yield_conf-high / soil_fert-poor -> yield_conf-low,
        # holding rainfall/water fixed at their "normal"/"medium" anchor points.
        poor_soil = fz.evaluate_uncertainty(0, 50, 10)
        good_soil = fz.evaluate_uncertainty(0, 50, 95)
        assert good_soil.yield_confidence > poor_soil.yield_confidence

    def test_high_water_storage_and_good_soil_gives_high_confidence(self):
        # rule: water_storage-high & soil_fert-good -> yield_conf-high
        result = fz.evaluate_uncertainty(
            rainfall_deviation_percent=0,
            water_storage_percent=95,
            soil_fertility_index=95,
        )
        assert result.yield_confidence > 0.6


# ---------------------------------------------------------------------------
# Per-crop confidence adjustment (crop_yield_confidence)
# ---------------------------------------------------------------------------

class TestPerCropConfidenceAdjustment:

    def test_higher_rainfall_dependency_is_penalised_more(self):
        base_conf, irr_risk = 0.8, 0.8
        very_low = fz.crop_yield_confidence(base_conf, irr_risk, "Very Low")
        low = fz.crop_yield_confidence(base_conf, irr_risk, "Low")
        medium = fz.crop_yield_confidence(base_conf, irr_risk, "Medium")
        high = fz.crop_yield_confidence(base_conf, irr_risk, "High")
        assert very_low >= low >= medium >= high

    def test_zero_irrigation_risk_means_no_penalty(self):
        conf = fz.crop_yield_confidence(0.8, 0.0, "High")
        assert conf == pytest.approx(0.8, abs=1e-9)

    def test_penalty_capped_at_forty_percent_of_base(self):
        # penalty = irrigation_risk * dependency_factor * 0.4; worst case
        # (irrigation_risk=1.0, "High"->factor 1.0) caps the penalty at 0.4,
        # so confidence can't drop below 60% of its base value.
        conf = fz.crop_yield_confidence(1.0, 1.0, "High")
        assert conf == pytest.approx(0.6, abs=1e-6)

    def test_unknown_dependency_label_falls_back_to_a_mid_factor(self):
        # app.config.RAINFALL_DEPENDENCY_FACTOR.get(label, 0.5) default
        conf = fz.crop_yield_confidence(0.8, 0.5, "Unknown")
        assert conf == pytest.approx(0.72, abs=1e-6)

    def test_output_stays_in_unit_range_at_worst_case_inputs(self):
        for dep in ["Very Low", "Low", "Medium", "High"]:
            conf = fz.crop_yield_confidence(1.0, 1.0, dep)
            assert 0.0 <= conf <= 1.0


# ---------------------------------------------------------------------------
# Integration: real region profiles -> real fuzzy assessments
# ---------------------------------------------------------------------------

class TestFuzzyAgainstRealRegionProfiles:
    """Runs the actual data -> fuzzy pipeline the way
    app/services/plan_service.py does, for every location, instead of only
    hand-picked numbers."""

    @pytest.mark.parametrize("location", ["Coimbatore", "Erode", "Salem", "Pollachi"])
    def test_every_location_produces_a_valid_assessment(self, location):
        profile = pp.get_region_season_profile(location, "Kharif", year=2023)
        result = fz.evaluate_uncertainty(
            profile.rainfall.avg_deviation_percent,
            profile.water.avg_storage_percent,
            profile.soil.fertility_index,
        )
        assert 0.0 <= result.yield_confidence <= 1.0
        assert 0.0 <= result.irrigation_risk <= 1.0

    def test_assessment_is_deterministic_for_the_same_inputs(self):
        """Same (rainfall_dev, water_storage, soil_fert) in -> exactly the
        same outputs, every time -- the fuzzy engine itself has no hidden
        randomness (unlike the separately-seeded NSGA-II stage)."""
        profile = pp.get_region_season_profile("Coimbatore", "Kharif", year=2023)
        args = (
            profile.rainfall.avg_deviation_percent,
            profile.water.avg_storage_percent,
            profile.soil.fertility_index,
        )
        first = fz.evaluate_uncertainty(*args)
        second = fz.evaluate_uncertainty(*args)
        assert first == second
