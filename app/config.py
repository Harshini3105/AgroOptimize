"""
Central configuration and "assumption constants" for AgroOptimize.

Every number in this file that is NOT sourced directly from the datasets in
data/raw/ is a modelling assumption. They are collected here (instead of
being scattered as magic numbers through the codebase) for two reasons:

1. It makes the whole system easy to re-tune (e.g. if fertilizer prices
   change, edit one line).
2. It gives a single place to point to during the viva when asked
   "where does this number come from?" -- see notes/methodology_notes.md
   for the justification of each assumption below.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parent
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
RESULTS_DIR = PROJECT_ROOT / "results"

# ---------------------------------------------------------------------------
# Dataset structure (data/raw/<location>_<kind>.csv)
# ---------------------------------------------------------------------------
LOCATIONS = ["Coimbatore", "Erode", "Salem", "Pollachi"]
DATASET_KINDS = ["crop", "land", "rainfall", "water_availability"]

# Approximate town-centre WGS84 coordinates for each district, used only to
# query the live Open-Meteo weather API (app/services/dashboard_service.py
# get_weather). Not used anywhere in the fuzzy/NSGA-II pipeline itself.
DISTRICT_COORDINATES = {
    "Coimbatore": (11.0168, 76.9558),
    "Erode": (11.3410, 77.7172),
    "Salem": (11.6643, 78.1460),
    "Pollachi": (10.6589, 77.0084),
}

# Agricultural (cropping) seasons used in crop.csv / land.csv
AG_SEASONS = ["Kharif", "Rabi", "Summer"]

# Meteorological months that fall inside each agricultural season. Used to
# aggregate the monthly rainfall.csv / water_availability.csv records onto
# the coarser Kharif/Rabi/Summer granularity used for cropping decisions.
# This mapping follows the standard Tamil Nadu agricultural calendar and is
# a documented modelling assumption (see methodology notes, Section 2).
SEASON_MONTH_MAP = {
    "Kharif": ["June", "July", "August", "September"],
    "Rabi": ["October", "November", "December", "January", "February", "March"],
    "Summer": ["February", "March", "April", "May"],
}

# ---------------------------------------------------------------------------
# Candidate crop selection
# ---------------------------------------------------------------------------
# A farmer plan mixes at most this many crops (matches the 3-crop-style
# combinations reported in the reference paper's results, e.g. "Sugarcane +
# Wheat + Groundnut"). If fewer crops are available for a location/season,
# all of them are used.
DEFAULT_MAX_CANDIDATE_CROPS = 6
MIN_CANDIDATE_CROPS = 2

# ---------------------------------------------------------------------------
# Economic assumptions (₹) -- used to turn dataset fields into a cost figure
#
# Updated 2026-09-16 with Tamil Nadu / India, 2024-25 sourced values (each
# derived as: notified retail bag MRP ÷ nutrient content of that bag, using
# the standard N / P2O5 / K2O basis -- matching this dataset's own
# Fertilizer_N/P/K_Kg_Ha columns, which are reported on the same basis).
# Source bag prices:
#   - Urea (46% N), neem-coated, govt-notified MRP: Rs 266.50 / 45 kg bag.
#     (PIB / Dept. of Fertilizers; widely republished at this exact figure.)
#     => Rs 266.50 / (45 * 0.46) = Rs 12.87 / kg N
#   - DAP (18% N, 46% P2O5), govt-capped MRP: Rs 1,350 / 50 kg bag.
#     (IFFCO official issue-price list, Feb 2025; PIB coverage of the DAP
#     MRP cap.) => Rs 1,350 / (50 * 0.46) = Rs 58.70 / kg P2O5
#   - MOP (60% K2O), market retail: Rs 1,700 / 50 kg bag (typical 2024-25
#     dealer price; MOP is not MRP-capped like urea/DAP, so this is a
#     representative market rate rather than a notified price).
#     => Rs 1,700 / (50 * 0.60) = Rs 56.67 / kg K2O
# NOTE: earlier values here (N=6.5, P=27.0, K=17.0) were a rougher, unsourced
# 2024-25 "typical retail range" estimate -- these replace them with figures
# traceable to a specific notified/quoted bag price.
FERTILIZER_PRICE_RS_PER_KG_NUTRIENT = {
    "N": 12.87,
    "P": 58.70,
    "K": 56.67,
}

# MGNREGA Tamil Nadu unskilled agricultural wage, FY 2024-25 (Rs 319/day,
# effective until the April-2025 revision to Rs 336/day -- see e.g. DT Next,
# "MGNREGS wage in TN to go up by Rs 15; Rs 336 per day from April 1", which
# reports the pre-hike FY24-25 rate as Rs 319). Replaces the earlier
# unsourced flat Rs 400/day placeholder.
LABOR_WAGE_RS_PER_DAY = 319.0

# Groundwater/diesel-pump irrigation cost, order-of-magnitude assumption for
# Tamil Nadu smallholder pumped irrigation (no single authoritative
# per-mm/ha rate exists; typical diesel-pump irrigation cost literature for
# India falls in the low-hundreds-of-Rs-per-1000-m^3 range, which this is
# consistent with: Rs 3.0/mm/ha = Rs 300 per 1,000 m^3). Documented
# assumption, like RAINFALL_UTILIZATION_FACTOR below -- NOT currently wired
# into the NSGA-II cost objective (app/optimization/problem.py f2), which
# only prices fertilizer + labor + pesticide today. Left unwired
# deliberately (2026-09-16) to avoid changing the optimizer's cost math --
# and hence its already-reviewed objective formulation -- this close to
# Panel Review 1; wire this in explicitly (and re-verify against
# test_dashboard.py) if/when the cost objective is meant to include water.
WATER_COST_RS_PER_MM_PER_HA = 3.0

# ---------------------------------------------------------------------------
# Water assumptions
# ---------------------------------------------------------------------------
# 1 mm of water applied over 1 hectare = 10,000 litres (standard conversion:
# 1 mm/ha = 10 m^3/ha = 10,000 L/ha).
LITERS_PER_MM_PER_HA = 10_000.0

# Fraction of seasonal rainfall that is agronomically usable by the crop
# (rest is lost to runoff / deep percolation / evaporation). Used to derive
# "effective rainfall" that offsets the irrigation requirement.
RAINFALL_UTILIZATION_FACTOR = 0.7

# ---------------------------------------------------------------------------
# Environmental impact proxy weights (Section III-D of the reference paper:
# "environmental impact score calculated as the product of the chemical
# leaching risk and carbon emission proxies")
#
# Real-world anchor (2026-09-16): IPCC 2006 Guidelines for National GHG
# Inventories, Vol. 4, Ch. 11 sets the default direct-emission factor for
# synthetic N fertilizer at EF1 = 0.01 kg N2O-N per kg N applied. Converting
# to CO2-equivalent (x 44/28 for N2O-N -> N2O, x 298 for N2O's 100-yr GWP,
# per IPCC AR4) gives approximately 4.68 kg CO2-eq per kg N applied -- the
# real-world order of magnitude this proxy is standing in for.
# CARBON_FERTILIZER_FACTOR itself is deliberately left unchanged (still a
# unitless proxy applied across combined N+P+K, not just N) rather than
# rescaled to that figure: IPCC's EF1 is N-specific and rescaling would
# change the NSGA-II f4 objective's magnitude and the already fixed/
# verified Land Impact radar score (see agrooptimize-frontend-hardcoded-
# data-audit.md) days before Panel Review 1. Treat this as the documented
# real-world basis for the proxy's existence, not a literal plug-in value.
CARBON_FERTILIZER_FACTOR = 0.15   # synthetic carbon-proxy units per kg NPK applied
CARBON_PUMPING_FACTOR = 0.01      # synthetic carbon-proxy units per mm irrigation per ha

# Dependency of a crop's yield confidence on rainfall adequacy, keyed off
# the dataset's own `Rainfall_Dependency` column (Very Low/Low/Medium/High).
RAINFALL_DEPENDENCY_FACTOR = {
    "Very Low": 0.1,
    "Low": 0.3,
    "Medium": 0.6,
    "High": 1.0,
}

# ---------------------------------------------------------------------------
# Decision variable bounds (chromosome design, Section III-D)
# ---------------------------------------------------------------------------
ALLOC_MIN, ALLOC_MAX = 0.0, 1.0           # land allocation fraction per crop
IRRIGATION_MULT_MIN, IRRIGATION_MULT_MAX = 0.7, 1.3   # multiplier on baseline water need
FERTILIZER_MULT_MIN, FERTILIZER_MULT_MAX = 0.7, 1.3   # multiplier on baseline fertilizer dose

# ---------------------------------------------------------------------------
# NSGA-II hyperparameters -- match the values reported in the reference
# paper (Section III-D): 200 generations, single-point crossover p=0.85,
# Gaussian mutation p=0.12.
# ---------------------------------------------------------------------------
NSGA2_POP_SIZE = 80
NSGA2_N_GEN = 200
NSGA2_CROSSOVER_PROB = 0.85
NSGA2_MUTATION_PROB = 0.12
NSGA2_MUTATION_SIGMA = 0.12
NSGA2_SEED = 42

# Fast settings used by automated tests / quick smoke checks so the whole
# suite runs in a couple of seconds instead of ~10s per optimisation run.
NSGA2_FAST_POP_SIZE = 24
NSGA2_FAST_N_GEN = 15

# ---------------------------------------------------------------------------
# Decision output
# ---------------------------------------------------------------------------
MAX_RETURNED_PLANS = 50
