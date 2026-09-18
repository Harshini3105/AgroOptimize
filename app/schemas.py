"""Pydantic request/response models for the FastAPI layer."""

from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

Preference = Literal["balanced", "max_yield", "min_cost", "min_water", "min_env_impact"]


class FarmPlanRequest(BaseModel):
    location: str = Field(..., examples=["Coimbatore"])
    season: str = Field(..., examples=["Kharif"])
    year: Optional[int] = Field(None, description="Defaults to the latest year in the dataset.")
    total_land_ha: float = Field(..., gt=0, examples=[5.0])
    budget_rs: Optional[float] = Field(None, gt=0, description="Optional hard budget cap (Rs).")
    preference: Preference = "balanced"
    max_candidate_crops: Optional[int] = Field(None, ge=2, le=12)

    # Preference filters applied to the Pareto front before ranking.
    max_cost_rs: Optional[float] = None
    max_water_liters: Optional[float] = None
    min_yield_tonnes: Optional[float] = None
    max_env_impact: Optional[float] = None

    # Advanced / demo knobs. Capped server-side so a client can't request an
    # absurdly expensive run.
    pop_size: Optional[int] = Field(None, ge=8, le=300)
    n_gen: Optional[int] = Field(None, ge=5, le=500)

    # Persist this run to results/ (JSON + CSV + convergence plot)? Also
    # controls whether per-generation convergence history is tracked at
    # all, since that's the expensive part (~2-3x slower NSGA-II run).
    save_results: bool = True

    # Opaque per-browser id (see src/services/api.js) attached to a saved
    # run so GET /api/history/{location} can show it back only to the
    # client that actually generated it -- there are no real user accounts
    # in this project, so this is what keeps one visitor's saved runs from
    # appearing as another (or a brand-new) visitor's "completed" history.
    client_id: Optional[str] = None


class SoilOut(BaseModel):
    soil_type: str
    avg_ph: float
    organic_carbon_percent: float
    n_status: str
    p_status: str
    k_status: str
    irrigation_percent: float
    fertility_index: float


class RainfallOut(BaseModel):
    avg_monthly_rainfall_mm: float
    avg_deviation_percent: float
    avg_humidity_percent: float
    avg_max_temp_c: float
    avg_min_temp_c: float
    months_used: List[str]
    effective_rainfall_mm: float


class WaterOut(BaseModel):
    avg_storage_percent: float
    groundwater_status: str
    avg_deficit_surplus_mcm: float


class CropCandidateOut(BaseModel):
    name: str
    crop_type: str
    yield_kg_ha: float
    water_req_mm: float
    rainfall_dependency: str
    irrigation_type: str
    sowing_month: str
    harvest_month: str
    crop_duration_days: int


class RegionProfileOut(BaseModel):
    location: str
    year: int
    season: str
    soil: SoilOut
    rainfall: RainfallOut
    water: WaterOut
    candidate_crops: List[CropCandidateOut]
    normalized_snapshot: Dict[str, float]


class FuzzyAssessmentOut(BaseModel):
    yield_confidence: float
    irrigation_risk: float
    rainfall_label: str
    water_label: str
    soil_label: str


class RankedPlanOut(BaseModel):
    rank: int
    crop_names: List[str]
    allocation_percent: List[float]
    area_ha: List[float]
    irrigation_multiplier: List[float]
    fertilizer_multiplier: List[float]
    yield_tonnes: float
    cost_rs: float
    water_liters: float
    env_impact_score: float
    feasible: bool
    composite_score: float
    normalized_scores: Dict[str, float]
    confidence_label: str
    trade_off_summary: str


class RunMeta(BaseModel):
    algorithm: str = "NSGA-II"
    pop_size: int
    n_gen: int
    crossover_prob: float
    mutation_prob: float
    preference: str
    n_pareto_solutions_found: int
    n_plans_returned: int
    optimize_seconds: float


class ConvergencePointOut(BaseModel):
    generation: int
    population_size: int
    best_yield_tonnes: float
    mean_yield_tonnes: float
    best_cost_rs: float
    mean_cost_rs: float
    best_water_liters: float
    mean_water_liters: float
    best_env_impact: float
    mean_env_impact: float
    hypervolume: float


class SavedFilesOut(BaseModel):
    run_id: str
    json_path: str
    plans_csv_path: str
    convergence_csv_path: Optional[str] = None
    convergence_plot_path: Optional[str] = None


class FarmPlanResponse(BaseModel):
    region_profile: RegionProfileOut
    fuzzy_assessment: FuzzyAssessmentOut
    plans: List[RankedPlanOut]
    convergence_history: List[ConvergencePointOut] = []
    meta: RunMeta
    run_id: Optional[str] = None
    saved_files: Optional[SavedFilesOut] = None


class SavedRunSummaryOut(BaseModel):
    run_id: str
    location: str
    season: str
    year: int
    preference: Optional[str] = None
    saved_at: Optional[str] = None
    n_plans: int
    client_id: Optional[str] = None


class CatalogOut(BaseModel):
    locations: List[str]
    seasons: List[str]
    years: List[int]
    crops_by_season: Dict[str, List[str]]
