"""
Turns the raw CSVs into the structured, query-ready objects the rest of the
pipeline (fuzzy engine + NSGA-II) consumes.

Pipeline stage 1 & 2 of the reference paper (Section III-B "Data Collection
and Preprocessing of input"): gathers soil, rainfall, crop-history and
water-availability data for a given (location, year, season) and normalises
it into a single RegionSeasonProfile.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import pandas as pd

from app import config
from app.data.loader import load_all

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class CropCandidate:
    name: str
    crop_type: str
    yield_kg_ha: float
    water_req_mm: float
    fert_n_kg_ha: float
    fert_p_kg_ha: float
    fert_k_kg_ha: float
    pesticide_cost_rs_ha: float
    labor_days_ha: float
    msp_rs_qtl: float
    revenue_rs_lakh_hist: float
    crop_duration_days: int
    sowing_month: str
    harvest_month: str
    irrigation_type: str
    rainfall_dependency: str


@dataclass
class SoilProfile:
    soil_type: str
    avg_ph: float
    organic_carbon_percent: float
    n_status: str
    p_status: str
    k_status: str
    irrigation_percent: float
    fertility_index: float  # 0-100, derived


@dataclass
class RainfallProfile:
    avg_monthly_rainfall_mm: float
    avg_deviation_percent: float
    avg_humidity_percent: float
    avg_max_temp_c: float
    avg_min_temp_c: float
    months_used: List[str]
    effective_rainfall_mm: float  # season-aggregate, usable fraction only


@dataclass
class WaterProfile:
    avg_storage_percent: float
    groundwater_status: str
    avg_deficit_surplus_mcm: float


@dataclass
class RegionSeasonProfile:
    location: str
    year: int
    season: str
    soil: SoilProfile
    rainfall: RainfallProfile
    water: WaterProfile
    candidate_crops: List[CropCandidate] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_STATUS_SCORE = {"Low": 30.0, "Medium": 60.0, "High": 90.0}


def _status_to_score(status: str) -> float:
    return _STATUS_SCORE.get(str(status).strip(), 50.0)


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def compute_soil_fertility_index(
    avg_ph: float, organic_carbon_percent: float, n_status: str, p_status: str, k_status: str
) -> float:
    """0-100 composite soil fertility score.

    - pH score peaks at the agronomic optimum (~6.5) and decays linearly.
    - Organic carbon score scales linearly up to 1.0% (a commonly used
      "good" threshold for tropical agricultural soils).
    - NPK score is the mean of the three categorical nutrient statuses.
    Weights (0.3 / 0.3 / 0.4) are a documented modelling choice - see
    notes/methodology_notes.md.
    """
    ph_score = _clamp(100.0 - abs(avg_ph - 6.5) * 40.0)
    oc_score = _clamp((organic_carbon_percent / 1.0) * 100.0)
    npk_score = (
        _status_to_score(n_status) + _status_to_score(p_status) + _status_to_score(k_status)
    ) / 3.0
    return round(0.3 * ph_score + 0.3 * oc_score + 0.4 * npk_score, 2)


def _mode_or_first(series: pd.Series) -> str:
    m = series.mode()
    return str(m.iloc[0]) if not m.empty else str(series.iloc[0])


def _resolve_year(df: pd.DataFrame, location: str, year: Optional[int]) -> int:
    years = sorted(df.loc[df["Location"] == location, "Year"].unique())
    if not years:
        raise ValueError(f"No data available for location '{location}'.")
    if year is None:
        return int(years[-1])  # latest available year
    if int(year) not in years:
        raise ValueError(
            f"No data for location='{location}', year={year}. Available years: {years}."
        )
    return int(year)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def list_catalog() -> dict:
    """Discovery endpoint payload: what locations/years/seasons/crops exist."""
    data = load_all()
    crop_df = data["crop"]
    return {
        "locations": config.LOCATIONS,
        "seasons": config.AG_SEASONS,
        "years": sorted(int(y) for y in crop_df["Year"].unique()),
        "crops_by_season": {
            season: sorted(crop_df.loc[crop_df["Season"] == season, "Crop_Name"].unique().tolist())
            for season in config.AG_SEASONS
        },
    }


def get_region_season_profile(
    location: str,
    season: str,
    year: Optional[int] = None,
    max_candidate_crops: Optional[int] = None,
) -> RegionSeasonProfile:
    if location not in config.LOCATIONS:
        raise ValueError(f"Unknown location '{location}'. Choose one of {config.LOCATIONS}.")
    if season not in config.AG_SEASONS:
        raise ValueError(f"Unknown season '{season}'. Choose one of {config.AG_SEASONS}.")

    data = load_all()
    crop_df, land_df, rain_df, water_df = data["crop"], data["land"], data["rainfall"], data["water"]

    resolved_year = _resolve_year(crop_df, location, year)

    # ---- Soil (land.csv) ----
    land_rows = land_df[
        (land_df["Location"] == location)
        & (land_df["Year"] == resolved_year)
        & (land_df["Season"] == season)
    ]
    if land_rows.empty:
        raise ValueError(
            f"No soil/land data for {location}/{resolved_year}/{season}."
        )
    land_row = land_rows.iloc[0]
    fertility_index = compute_soil_fertility_index(
        avg_ph=float(land_row["Avg_Soil_pH"]),
        organic_carbon_percent=float(land_row["Organic_Carbon_Percent"]),
        n_status=land_row["N_Status"],
        p_status=land_row["P_Status"],
        k_status=land_row["K_Status"],
    )
    soil = SoilProfile(
        soil_type=str(land_row["Soil_Type"]),
        avg_ph=float(land_row["Avg_Soil_pH"]),
        organic_carbon_percent=float(land_row["Organic_Carbon_Percent"]),
        n_status=str(land_row["N_Status"]),
        p_status=str(land_row["P_Status"]),
        k_status=str(land_row["K_Status"]),
        irrigation_percent=float(land_row["Irrigation_Percent"]),
        fertility_index=fertility_index,
    )

    # ---- Rainfall (rainfall.csv), aggregated over the season's months ----
    months = config.SEASON_MONTH_MAP[season]
    rain_rows = rain_df[
        (rain_df["Location"] == location)
        & (rain_df["Year"] == resolved_year)
        & (rain_df["Month"].isin(months))
    ]
    if rain_rows.empty:
        raise ValueError(f"No rainfall data for {location}/{resolved_year}/season={season}.")
    avg_monthly_rainfall = float(rain_rows["Monthly_Rainfall_mm"].mean())
    effective_rainfall = avg_monthly_rainfall * len(months) * config.RAINFALL_UTILIZATION_FACTOR
    rainfall = RainfallProfile(
        avg_monthly_rainfall_mm=round(avg_monthly_rainfall, 2),
        avg_deviation_percent=round(float(rain_rows["Deviation_Percent"].mean()), 2),
        avg_humidity_percent=round(float(rain_rows["Humidity_Percent"].mean()), 2),
        avg_max_temp_c=round(float(rain_rows["Max_Temp_C"].mean()), 2),
        avg_min_temp_c=round(float(rain_rows["Min_Temp_C"].mean()), 2),
        months_used=months,
        effective_rainfall_mm=round(effective_rainfall, 2),
    )

    # ---- Water availability (water_availability.csv), same month window ----
    water_rows = water_df[
        (water_df["Location"] == location)
        & (water_df["Year"] == resolved_year)
        & (water_df["Month"].isin(months))
    ]
    if water_rows.empty:
        raise ValueError(f"No water availability data for {location}/{resolved_year}/season={season}.")
    water = WaterProfile(
        avg_storage_percent=round(float(water_rows["Storage_Percent"].mean()), 2),
        groundwater_status=_mode_or_first(water_rows["Groundwater_Status"]),
        avg_deficit_surplus_mcm=round(float(water_rows["Deficit_Surplus_MCM"].mean()), 2),
    )

    # ---- Candidate crops (crop.csv) ----
    crop_rows = crop_df[
        (crop_df["Location"] == location)
        & (crop_df["Year"] == resolved_year)
        & (crop_df["Season"] == season)
    ].sort_values("Revenue_Rs_Lakh", ascending=False)

    if crop_rows.empty:
        raise ValueError(f"No crop history for {location}/{resolved_year}/{season}.")

    top_n = max_candidate_crops or config.DEFAULT_MAX_CANDIDATE_CROPS
    crop_rows = crop_rows.head(max(top_n, config.MIN_CANDIDATE_CROPS))

    candidates = [
        CropCandidate(
            name=str(r["Crop_Name"]),
            crop_type=str(r["Crop_Type"]),
            yield_kg_ha=float(r["Yield_Kg_Ha"]),
            water_req_mm=float(r["Water_Req_mm"]),
            fert_n_kg_ha=float(r["Fertilizer_N_Kg_Ha"]),
            fert_p_kg_ha=float(r["Fertilizer_P_Kg_Ha"]),
            fert_k_kg_ha=float(r["Fertilizer_K_Kg_Ha"]),
            pesticide_cost_rs_ha=float(r["Pesticide_Cost_Rs_Ha"]),
            labor_days_ha=float(r["Labor_Days_Ha"]),
            msp_rs_qtl=float(r["MSP_Rs_Qtl"]),
            revenue_rs_lakh_hist=float(r["Revenue_Rs_Lakh"]),
            crop_duration_days=int(r["Crop_Duration_Days"]),
            sowing_month=str(r["Sowing_Month"]),
            harvest_month=str(r["Harvest_Month"]),
            irrigation_type=str(r["Irrigation_Type"]),
            rainfall_dependency=str(r["Rainfall_Dependency"]),
        )
        for _, r in crop_rows.iterrows()
    ]

    if len(candidates) < config.MIN_CANDIDATE_CROPS:
        raise ValueError(
            f"Only {len(candidates)} candidate crop(s) available for "
            f"{location}/{resolved_year}/{season}; need at least "
            f"{config.MIN_CANDIDATE_CROPS}."
        )

    return RegionSeasonProfile(
        location=location,
        year=resolved_year,
        season=season,
        soil=soil,
        rainfall=rainfall,
        water=water,
        candidate_crops=candidates,
    )


# Reference ranges used purely to produce a human-readable [0,1] snapshot of
# the raw inputs for API transparency (Section III-B: "numeric data are all
# scaled to [0,1]"). These are domain-informed plausible ranges, not derived
# from the (small) per-query sample.
_REFERENCE_RANGES = {
    "avg_ph": (4.0, 9.0),
    "organic_carbon_percent": (0.0, 1.5),
    "avg_monthly_rainfall_mm": (0.0, 150.0),
    "avg_deviation_percent": (-50.0, 50.0),
    "avg_storage_percent": (0.0, 100.0),
}


def _minmax(value: float, key: str) -> float:
    lo, hi = _REFERENCE_RANGES[key]
    if hi == lo:
        return 0.5
    return round(max(0.0, min(1.0, (value - lo) / (hi - lo))), 3)


def normalized_snapshot(profile: RegionSeasonProfile) -> dict:
    return {
        "soil_ph_norm": _minmax(profile.soil.avg_ph, "avg_ph"),
        "organic_carbon_norm": _minmax(profile.soil.organic_carbon_percent, "organic_carbon_percent"),
        "rainfall_norm": _minmax(profile.rainfall.avg_monthly_rainfall_mm, "avg_monthly_rainfall_mm"),
        "rainfall_deviation_norm": _minmax(profile.rainfall.avg_deviation_percent, "avg_deviation_percent"),
        "water_storage_norm": _minmax(profile.water.avg_storage_percent, "avg_storage_percent"),
        "soil_fertility_index_norm": round(profile.soil.fertility_index / 100.0, 3),
    }
