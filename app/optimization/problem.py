"""
Multi-Objective Genetic Optimization engine (reference paper, Section III-D).

Defines FarmPlanProblem, a pymoo Problem whose decision variables are a
per-crop land allocation plus irrigation/fertilizer intensity multipliers,
and whose four objectives are:

    f1 = -expected yield (t)            [maximise yield  -> minimise -yield]
    f2 =  total production cost (Rs)    [minimise]
    f3 =  total irrigation water (L)    [minimise]
    f4 =  environmental impact score    [minimise]

An optional inequality constraint keeps total cost under the farmer's
budget, if one was supplied.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import numpy as np
from pymoo.core.problem import Problem

from app import config
from app.data.preprocessing import CropCandidate, RegionSeasonProfile
from app.fuzzy.engine import UncertaintyAssessment, crop_yield_confidence


@dataclass
class CropVector:
    """Per-crop scalar arrays, precomputed once so `_evaluate` is fully
    vectorised across the population (no Python-level loops per individual).
    """

    names: List[str]
    yield_kg_ha: np.ndarray
    water_req_mm: np.ndarray
    fert_n_kg_ha: np.ndarray
    fert_p_kg_ha: np.ndarray
    fert_k_kg_ha: np.ndarray
    pesticide_cost_rs_ha: np.ndarray
    labor_days_ha: np.ndarray
    crop_yield_confidence: np.ndarray  # fuzzy-adjusted, per crop

    @classmethod
    def from_candidates(
        cls, crops: List[CropCandidate], assessment: UncertaintyAssessment, use_fuzzy: bool = True
    ) -> "CropVector":
        """`use_fuzzy=False` bypasses the Mamdani fuzzy uncertainty
        adjustment entirely (every crop gets confidence=1.0, i.e. the
        dataset's "book" yield is trusted as-is) -- this is the non-fuzzy
        baseline for the Task 4 fuzzy-vs-non-fuzzy comparison study, not a
        change to the default (fuzzy-on) pipeline every other caller uses.
        """
        if use_fuzzy:
            conf = np.array(
                [
                    crop_yield_confidence(assessment.yield_confidence, assessment.irrigation_risk, c.rainfall_dependency)
                    for c in crops
                ]
            )
        else:
            conf = np.ones(len(crops))
        return cls(
            names=[c.name for c in crops],
            yield_kg_ha=np.array([c.yield_kg_ha for c in crops]),
            water_req_mm=np.array([c.water_req_mm for c in crops]),
            fert_n_kg_ha=np.array([c.fert_n_kg_ha for c in crops]),
            fert_p_kg_ha=np.array([c.fert_p_kg_ha for c in crops]),
            fert_k_kg_ha=np.array([c.fert_k_kg_ha for c in crops]),
            pesticide_cost_rs_ha=np.array([c.pesticide_cost_rs_ha for c in crops]),
            labor_days_ha=np.array([c.labor_days_ha for c in crops]),
            crop_yield_confidence=conf,
        )


class FarmPlanProblem(Problem):
    def __init__(
        self,
        profile: RegionSeasonProfile,
        assessment: UncertaintyAssessment,
        total_land_ha: float,
        budget_rs: Optional[float] = None,
        use_fuzzy: bool = True,
    ):
        self.profile = profile
        self.assessment = assessment
        self.total_land_ha = float(total_land_ha)
        self.budget_rs = budget_rs
        self.use_fuzzy = use_fuzzy

        self.crop_vec = CropVector.from_candidates(profile.candidate_crops, assessment, use_fuzzy=use_fuzzy)
        self.n_crops = len(profile.candidate_crops)
        n = self.n_crops

        # Effective rainfall offsets part of the crop's water requirement.
        self.effective_rainfall_mm = profile.rainfall.effective_rainfall_mm

        xl = np.concatenate(
            [
                np.full(n, config.ALLOC_MIN),
                np.full(n, config.IRRIGATION_MULT_MIN),
                np.full(n, config.FERTILIZER_MULT_MIN),
            ]
        )
        xu = np.concatenate(
            [
                np.full(n, config.ALLOC_MAX if config.ALLOC_MAX > 0 else 1.0),
                np.full(n, config.IRRIGATION_MULT_MAX),
                np.full(n, config.FERTILIZER_MULT_MAX),
            ]
        )
        # avoid degenerate zero-width allocation bound
        xl[0:n] = 1e-4

        n_ieq_constr = 1 if budget_rs else 0

        super().__init__(n_var=3 * n, n_obj=4, n_ieq_constr=n_ieq_constr, xl=xl, xu=xu)

    def _evaluate(self, X, out, *args, **kwargs):
        n = self.n_crops
        cv = self.crop_vec

        alloc = X[:, 0:n]
        alloc = alloc / np.clip(alloc.sum(axis=1, keepdims=True), 1e-9, None)
        irr_mult = X[:, n : 2 * n]
        fert_mult = X[:, 2 * n : 3 * n]

        area_ha = alloc * self.total_land_ha  # (pop, n_crops)

        # --- f1: expected yield (tonnes), maximised -> stored as negative ---
        yield_tonnes = area_ha * (cv.yield_kg_ha / 1000.0) * cv.crop_yield_confidence
        total_yield = yield_tonnes.sum(axis=1)
        f1 = -total_yield

        # --- f2: total production cost (Rs) ---
        prices = config.FERTILIZER_PRICE_RS_PER_KG_NUTRIENT
        fert_cost_per_ha = (
            cv.fert_n_kg_ha * prices["N"] + cv.fert_p_kg_ha * prices["P"] + cv.fert_k_kg_ha * prices["K"]
        )
        cost_per_ha = (
            fert_mult * fert_cost_per_ha
            + cv.pesticide_cost_rs_ha
            + cv.labor_days_ha * config.LABOR_WAGE_RS_PER_DAY
        )
        total_cost = (area_ha * cost_per_ha).sum(axis=1)
        f2 = total_cost

        # --- f3: total irrigation water (litres) ---
        net_irrigation_mm = np.clip(cv.water_req_mm - self.effective_rainfall_mm, 0.0, None)
        water_liters = area_ha * irr_mult * net_irrigation_mm * config.LITERS_PER_MM_PER_HA
        total_water = water_liters.sum(axis=1)
        f3 = total_water

        # --- f4: environmental impact = sqrt(leaching_risk * carbon_proxy) ---
        # (geometric mean keeps the composite in the same order of magnitude
        # as its two components, while preserving the paper's "product of
        # leaching risk and carbon proxy" definition).
        leaching = (area_ha * fert_mult * cv.fert_n_kg_ha).sum(axis=1)
        carbon = (
            area_ha * fert_mult * (cv.fert_n_kg_ha + cv.fert_p_kg_ha + cv.fert_k_kg_ha) * config.CARBON_FERTILIZER_FACTOR
            + area_ha * irr_mult * cv.water_req_mm * config.CARBON_PUMPING_FACTOR
        ).sum(axis=1)
        f4 = np.sqrt(np.clip(leaching, 0, None) * np.clip(carbon, 0, None))

        out["F"] = np.column_stack([f1, f2, f3, f4])

        if self.budget_rs:
            out["G"] = (total_cost - self.budget_rs).reshape(-1, 1)

    def decode(self, x: np.ndarray) -> dict:
        """Decode a single chromosome (1D array) into farmer-readable fields."""
        n = self.n_crops
        cv = self.crop_vec
        alloc = x[0:n]
        alloc = alloc / max(alloc.sum(), 1e-9)
        irr_mult = x[n : 2 * n]
        fert_mult = x[2 * n : 3 * n]
        area_ha = alloc * self.total_land_ha
        return {
            "crop_names": cv.names,
            "allocation_fraction": alloc.tolist(),
            "area_ha": area_ha.tolist(),
            "irrigation_multiplier": irr_mult.tolist(),
            "fertilizer_multiplier": fert_mult.tolist(),
        }
