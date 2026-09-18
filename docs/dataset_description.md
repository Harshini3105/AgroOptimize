# Dataset Documentation

**Author:** Gaddam Jahnavi (CB.SC.U4CSE23023)

Column lists below are read directly from `data/raw/*.csv` headers, not
reconstructed from memory -- they're the ground truth for anyone writing
loader/preprocessing code against this dataset.

---

## Summary

- Districts: 4 (Coimbatore, Erode, Salem, Pollachi -- Tamil Nadu)
- Kinds: 4 per district (crop, land/soil, rainfall, water availability)
- Years: 2020-2023
- Total files: 16 CSVs, under `data/raw/`
- Granularity: crop/land are per Location-Year-Season; rainfall/water are
  per Location-Year-**Month**

## ⚠ Data provenance -- needs confirming before this goes in the report

Every other fact in this document was verified against the actual files in
this repo. The *origin* of the underlying figures was not independently
verified for this documentation pass -- whoever compiled `data/raw/`
(synthesised for the project vs. drawn from public sources such as
data.gov.in / TN's open data portal / CGWB groundwater bulletins / TNAU
Agritech) should confirm the real provenance here before it goes in a
report or the paper. Overstating this as "sourced from data.gov.in / CGWB
/ TNAU" without checking would be a factual claim about the project that
needs to actually be true.

---

## File structure

Naming convention: `data/raw/<district-lowercase>_<kind>.csv`

| File | District | Kind |
|---|---|---|
| `coimbatore_crop.csv` / `_land.csv` / `_rainfall.csv` / `_water_availability.csv` | Coimbatore | all 4 |
| `erode_crop.csv` / `_land.csv` / `_rainfall.csv` / `_water_availability.csv` | Erode | all 4 |
| `salem_crop.csv` / `_land.csv` / `_rainfall.csv` / `_water_availability.csv` | Salem | all 4 |
| `pollachi_crop.csv` / `_land.csv` / `_rainfall.csv` / `_water_availability.csv` | Pollachi | all 4 |

(16 files total -- confirmed present by `tests/test_data.py::TestRawCsvFilesExist`.)

---

## Column reference

### `<district>_crop.csv` -- per Location/Year/Season/Crop

| Column | Description |
|---|---|
| `Location`, `Year`, `Season` | District, year, agricultural season (Kharif/Rabi/Summer) |
| `Crop_Name`, `Crop_Type` | e.g. "Sugarcane", "Commercial" |
| `Area_Sown_Ha`, `Area_Harvested_Ha` | Hectares sown / harvested |
| `Production_Tonnes`, `Yield_Kg_Ha` | Total production and per-hectare yield |
| `MSP_Rs_Qtl` | Minimum support price, Rs per quintal |
| `Revenue_Rs_Lakh` | Historical revenue, Rs lakh -- drives candidate-crop ranking |
| `Water_Req_mm` | Crop water requirement, mm |
| `Fertilizer_N_Kg_Ha`, `Fertilizer_P_Kg_Ha`, `Fertilizer_K_Kg_Ha` | NPK dose, kg/ha |
| `Pesticide_Cost_Rs_Ha`, `Labor_Days_Ha` | Cost/ha and labour days/ha |
| `Crop_Duration_Days`, `Sowing_Month`, `Harvest_Month` | Crop calendar |
| `Irrigation_Type` | e.g. "Drip", "Rainfed", "Drip+Flood" |
| `Rainfall_Dependency` | Very Low / Low / Medium / High -- drives the fuzzy per-crop confidence penalty |

### `<district>_land.csv` -- per Location/Year/Season

| Column | Description |
|---|---|
| `Total_Land_Ha`, `Agricultural_Land_Ha`, `Irrigated_Land_Ha`, `Rainfed_Land_Ha` | Land-use breakdown |
| `Fallow_Land_Ha`, `Forest_Land_Ha`, `Urban_Land_Ha`, `Wasteland_Ha`, `Horticulture_Ha`, `Plantation_Ha` | Remaining land-use categories |
| `Irrigation_Percent`, `Agricultural_Percent` | Derived percentages |
| `Soil_Type` | e.g. "Red Sandy Loam", "Red Laterite", "Black Cotton Soil" |
| `Avg_Soil_pH`, `Organic_Carbon_Percent` | Soil chemistry -- feed the fertility index |
| `N_Status`, `P_Status`, `K_Status` | Low / Medium / High |

### `<district>_rainfall.csv` -- per Location/Year/**Month**

| Column | Description |
|---|---|
| `Season` | *Meteorological* season label (differs from crop.csv's agricultural seasons -- see `app/config.SEASON_MONTH_MAP`) |
| `Monthly_Rainfall_mm`, `Rainy_Days`, `Max_Daily_Rainfall_mm` | Rainfall stats |
| `Min_Temp_C`, `Max_Temp_C`, `Humidity_Percent` | Weather |
| `Rainfall_Type` | e.g. "Light", "Pre-monsoon" |
| `Normal_Rainfall_mm`, `Deviation_from_Normal_mm`, `Deviation_Percent` | Deviation from the historical normal -- `Deviation_Percent` feeds the fuzzy `rainfall_dev` input directly |

### `<district>_water_availability.csv` -- per Location/Year/**Month**

| Column | Description |
|---|---|
| `River_Inflow_MCM`, `Reservoir_Storage_MCM`, `Reservoir_Capacity_MCM`, `Storage_Percent` | Reservoir status -- `Storage_Percent` feeds the fuzzy `water_storage` input directly |
| `Groundwater_Level_mbgl`, `Groundwater_Status` | Groundwater depth (metres below ground level) and a categorical status |
| `Canal_Release_MCM`, `Irrigation_Water_MCM`, `Drinking_Water_MCM`, `Industrial_Water_MCM`, `Total_Demand_MCM` | Demand-side breakdown |
| `Deficit_Surplus_MCM` | Supply minus demand |
| `Primary_Source` | e.g. "Bhavani River", "Pillur Dam" |

---

## Season vocabulary mismatch (important, see `notes/methodology_notes.md` Section 3)

`crop.csv` / `land.csv` use **agricultural** seasons (Kharif, Rabi,
Summer). `rainfall.csv` / `water_availability.csv` are monthly and carry
their own **meteorological** season label, which doesn't line up 1:1 with
the agricultural one. `app/config.SEASON_MONTH_MAP` bridges this by
defining which calendar months fall inside each agricultural season
(Kharif = Jun-Sep, Rabi = Oct-Mar, Summer = Feb-May); `preprocessing.py`
filters the monthly files by `Month.isin(...)`, not by their own `Season`
column.

## Normalisation

`app/data/preprocessing.py::normalized_snapshot()` min-max scales raw
readings to `[0,1]` against fixed, domain-informed reference ranges (pH
4-9, rainfall 0-150mm/month, etc.) for **API transparency/display only** --
the optimiser itself works in natural units (tonnes, Rs, litres), not
normalised ones. See `app/data/preprocessing.py::_REFERENCE_RANGES`.
