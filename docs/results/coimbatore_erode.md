# Results Analysis -- Coimbatore and Erode

**Author:** Gaddam Jahnavi (CB.SC.U4CSE23023)

Every number on this page is copied from an actual saved run in
`results/` (not hand-picked illustrative figures) -- run IDs are given
under each section so they're reproducible: `GET /api/results/{run_id}`
returns the exact same record, or re-run with the CLI (`run_demo.py`)
using the same location/season/year/land/budget/seed.

---

## Coimbatore -- Kharif 2023

`run_id: coimbatore_kharif_2023_20260808T113724Z` -- 5 ha, preference
`balanced`, budget cap ~Rs 200,000 (inferred: the most expensive plan in
the returned set costs Rs 199,968, right at that ceiling).

### Region snapshot
| | |
|---|---|
| Soil | Red Sandy Loam, pH 7.1, fertility index 70.3/100 |
| Rainfall | 56.0 mm/month avg, deviation +1.05% (normal), effective 156.8mm for the season |
| Water | 94.7% reservoir storage (Very High groundwater status) |
| Candidate crops | Sugarcane, Maize, Groundnut, Cotton, Sorghum |

### Fuzzy assessment
| Output | Value | Label |
|---|---|---|
| Yield confidence | 0.775 | normal rainfall / high water / good soil |
| Irrigation risk | 0.118 | -- |

### NSGA-II run
pop=80, gen=200, 1.10s, 80 Pareto solutions found, 50 returned. Hypervolume
0.335 (gen 1) -> 0.496 (gen 200) -- climbs fast early, then plateaus, the
expected NSGA-II convergence signature (`notes/methodology_notes.md`
Section 6.7).

### Top 3 ranked plans (preference: `balanced`)
| Rank | Crop mix | Yield (t) | Cost (Rs) | Water (L) | Env. impact |
|---|---|---|---|---|---|
| 1 | Sugarcane 11%, Sorghum 89% | 48.43 | 170,702 | 12,174,241 | 197.2 |
| 2 | Sugarcane 8%, Sorghum 92% | 39.99 | 164,595 | 10,951,712 | 188.7 |
| 3 | Sugarcane 11%, Sorghum 89% | 50.17 | 171,963 | 12,425,286 | 198.9 |

All three: "Moderate yield, Moderate cost, Low water use, Moderate
environmental impact (confidence: high)".

### Observation
The Pareto front for Coimbatore under `balanced` converges on a
Sugarcane/Sorghum mix rather than the higher-value crops (Maize,
Groundnut, Cotton) also on offer -- TOPSIS's ideal-point ranking is
favouring the combination that's well-rounded across all 4 objectives
simultaneously, not the single highest-yield option on its own (that
would be a different point on the same Pareto front, reachable with
`preference: max_yield`).

---

## Erode -- Rabi 2023

`run_id: erode_rabi_2023_20260808T113726Z` -- 3 ha, preference `balanced`;
no clean cost ceiling is visible across the 50 returned plans (max cost Rs
223,262), so this run does not appear to have had a binding budget cap.

*(Note: the saved run is Rabi, not Kharif -- Erode's Kharif 2023 profile
has not been separately captured here.)*

### Region snapshot
| | |
|---|---|
| Soil | Red Laterite, pH 6.9, fertility index 71.2/100 |
| Rainfall | 42.93 mm/month avg, deviation +11.88% (normal), effective 180.32mm for the season |
| Water | 89.75% reservoir storage (High groundwater status) |

### Fuzzy assessment
| Output | Value | Label |
|---|---|---|
| Yield confidence | 0.711 | normal rainfall / high water / good soil |
| Irrigation risk | 0.158 | -- |

### NSGA-II run
pop=80, gen=200, 0.98s, 80 Pareto solutions found, 50 returned. Hypervolume
0.439 (gen 1) -> 0.656 (gen 200).

### Top 3 ranked plans (preference: `balanced`)
| Rank | Crop mix | Yield (t) | Cost (Rs) | Water (L) | Env. impact |
|---|---|---|---|---|---|
| 1 | Banana 100% | 42.41 | 212,458 | 25,610,655 | 265.6 |
| 2 | Banana 94%, Paddy 2%, Sunflower 4% | 40.30 | 206,055 | 24,690,640 | 256.0 |
| 3 | Banana 96%, Sunflower 4% | 40.93 | 207,678 | 30,336,757 | 263.2 |

All three: "High yield, High cost, Moderate water use, Moderate
environmental impact (confidence: high)".

### Observation
Erode's top plans lean almost entirely into Banana -- a high-value,
high-water crop -- rather than the more mixed allocation Coimbatore's
Pareto front favoured. Note the two runs aren't directly comparable
scale-for-scale (Erode was run at 3 ha vs. Coimbatore's 5 ha, and a
different season), so this is a difference in which crops the local
candidate list and TOPSIS ranking favoured, not a per-hectare
yield/cost comparison.

---

## Coimbatore vs. Erode -- what's comparable and what isn't

Fuzzy outputs are land-size-independent and directly comparable:
Coimbatore's yield confidence (0.775) is somewhat higher than Erode's
(0.711), and its irrigation risk (0.118) somewhat lower than Erode's
(0.158) -- consistent with both landing in "normal rainfall / high water /
good soil" territory, with Coimbatore slightly further into the favourable
end of each range.

Plan-level figures (yield tonnes, cost, water) are **not** directly
comparable between these two runs as presented here, since they used
different `total_land_ha` (5 vs. 3) and different seasons. A fair
same-scale comparison would need both runs re-executed at the same land
size, season, and budget -- a good candidate addition for
`docs/future_work.md`.
