# Key Modelling Assumptions

**Author:** Gaddam Jahnavi (CB.SC.U4CSE23023)

Every value below is quoted directly from `app/config.py` (or the formula
that consumes it in `app/optimization/problem.py` /
`app/data/preprocessing.py`) -- this file is a one-stop index, not a
second source of truth. If a number here and `app/config.py` ever
disagree, `app/config.py` is right.

---

## Economic constants (`app/config.py`)

| Parameter | Value | Used for |
|---|---|---|
| Urea (N) price | Rs 6.5 / kg nutrient | Cost objective (f2) |
| DAP (P) price | Rs 27.0 / kg nutrient | Cost objective (f2) |
| MOP (K) price | Rs 17.0 / kg nutrient | Cost objective (f2) |
| Labour wage | Rs 400 / day | Cost objective (f2) |

**Note:** these are approximate market rates, not live/sourced quotes --
flagged in `app/config.py` itself and centralised there so they're a
one-line change once real TNAU/supplier figures are available (see
`docs/future_work.md`, Harshini's item). The cost objective is
`fert_mult * (N*6.5 + P*27 + K*17) + pesticide_cost + labor_days * 400`,
per hectare, summed over allocated area -- there is currently no separate
Rs cost line item for water or energy; irrigation water is optimised
directly in litres (objective f3), not converted to a rupee cost.

## Water constants

| Parameter | Value | Used for |
|---|---|---|
| 1mm over 1ha = 10,000 L | fixed unit conversion, not an assumption | Water objective (f3) |
| Rainfall utilisation factor | 0.7 | Effective rainfall = `avg_monthly_rainfall_mm * months_in_season * 0.7` |

The 0.7 accounts for runoff / percolation / evaporation losses -- a
standard simplifying assumption in agronomic water-balance modelling (real
usable-rainfall fractions vary by soil and slope; one constant is used
across all districts here).

## Environmental impact constants

| Parameter | Value | Used for |
|---|---|---|
| Carbon-per-NPK-kg factor | 0.15 | Env. impact objective (f4) |
| Carbon-per-irrigation-mm factor | 0.01 | Env. impact objective (f4) |

`env_impact_score = sqrt(leaching_total * carbon_total)`, where
`leaching_total` is the area-weighted nitrogen applied (nitrogen is the
most leach-prone of the three nutrients) and `carbon_total` combines the
fertilizer and irrigation carbon-proxy factors above. The reference
methodology describes this objective as "the product of the chemical
leaching risk and carbon emission proxies"; the square root (geometric
mean) is a deliberate, documented deviation so the composite score stays
in the same order of magnitude as either component rather than becoming a
squared unit -- see `notes/methodology_notes.md` Section 6.5.

## Fuzzy system constants

### Soil fertility index weights (`app/data/preprocessing.py`)

| Component | Weight |
|---|---|
| Soil pH (peaks at pH 6.5) | 0.3 |
| Organic carbon (scaled to a 1.0% "good" threshold) | 0.3 |
| NPK status (mean of N/P/K categorical scores) | 0.4 |

### Rainfall dependency -> per-crop confidence penalty factor

| `Rainfall_Dependency` | Factor |
|---|---|
| Very Low | 0.1 |
| Low | 0.3 |
| Medium | 0.6 |
| High | 1.0 |

`penalty = irrigation_risk * factor * 0.4` (capped at 40% of base
confidence) -- see `docs/fuzzy_rules.md`.

## TOPSIS preference weight sets (`app/decision/ranking.py`)

| Preference | Yield | Cost | Water | Env |
|---|---|---|---|---|
| `balanced` (default) | 0.300 | 0.233 | 0.233 | 0.233 |
| `max_yield` | 0.550 | 0.150 | 0.150 | 0.150 |
| `min_cost` | 0.150 | 0.550 | 0.150 | 0.150 |
| `min_water` | 0.150 | 0.150 | 0.550 | 0.150 |
| `min_env_impact` | 0.150 | 0.150 | 0.150 | 0.550 |

`balanced` weights yield as its own group (30%) against the footprint
group as a whole (70% split three ways) rather than an equal 25/25/25/25 --
tuned empirically because yield correlates ~0.7-0.85 with the other three
objectives in this system, so an equal split lets them outvote yield 3-to-1
(see `notes/methodology_notes.md` Section 7 for the full derivation).

## Season-to-months mapping (`app/config.SEASON_MONTH_MAP`)

| Season | Months |
|---|---|
| Kharif | June - September |
| Rabi | October - March |
| Summer | February - May |

Note the overlap: February and March fall in both Rabi and Summer's month
lists -- a documented simplification of the regional cropping calendar,
not an exact scientific boundary (see `notes/methodology_notes.md`
Section 3).

## Other documented assumptions

- 4 years of data (2020-2023) used as the historical base.
- District-level aggregates, not per-plot/GPS-level data.
- Harvest timing is read from the dataset's fixed Sowing/Harvest month
  columns, not optimised as its own decision variable.
- NSGA-II hyperparameters (population 80, generations 200, crossover
  p=0.85, mutation p=0.12) match the reference methodology's stated
  values; population size specifically is this project's own choice, sized
  to keep the Pareto front well populated.
