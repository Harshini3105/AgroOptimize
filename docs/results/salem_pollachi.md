# Results Analysis -- Salem and Pollachi

**Author:** Gaddam Jahnavi (CB.SC.U4CSE23023)

Same ground rule as `docs/results/coimbatore_erode.md`: every figure here
is from an actual saved run in `results/`, not an illustrative estimate.

---

## Salem -- Kharif 2023

`run_id: salem_kharif_2023_20260812T061631Z` -- 5 ha, preference
`balanced`, budget cap Rs 200,000.

Salem is generally the driest of the four districts in this dataset on
average, and that's the assumption this section started from when this
run was planned -- but the actual Kharif 2023 record for Salem turned out
to describe a **favourable** season (near-normal rainfall, very high water
storage), not a dry one. Reporting the number that assumption predicted
rather than the number the run actually produced would have made this
page wrong, so this documents what the saved run actually shows.

### Region snapshot
| | |
|---|---|
| Soil | Red Loam, pH 6.8, fertility index 67.8/100 |
| Rainfall | 63.1 mm/month avg, deviation +2.78% (normal), effective 176.68mm for the season |
| Water | 96.6% reservoir storage (Very High groundwater status) |
| Candidate crops | Paddy, Tapioca, Maize, Groundnut, Cotton |

### Fuzzy assessment
| Output | Value | Label |
|---|---|---|
| Yield confidence | 0.742 | normal rainfall / high water / **medium** soil |
| Irrigation risk | 0.120 | -- |

Soil fertility (67.8) lands in the "medium" fuzzy set rather than "good" --
the one respect in which this run is visibly weaker than Coimbatore's
(70.3, "good") or Pollachi's (75.9, "good") -- but rainfall and water are
both favourable, which is why overall confidence still comes out
comparable to the other three districts rather than notably lower.

### NSGA-II run
pop=80, gen=200, 1.15s, 80 Pareto solutions found, 50 returned. Hypervolume
0.319 (gen 1) -> 0.878 (gen 200).

### Top 3 ranked plans (preference: `balanced`)
| Rank | Crop mix | Yield (t) | Cost (Rs) | Water (L) | Env. impact |
|---|---|---|---|---|---|
| 1 | Tapioca 36%, Maize 64% | 48.87 | 181,095 | 14,629,075 | 230.6 |
| 2 | Tapioca 29%, Maize 71% | 44.26 | 177,476 | 13,866,838 | 244.2 |
| 3 | Tapioca 32%, Maize 63%, Groundnut 4% | 45.85 | 179,777 | 15,504,436 | 217.8 |

All three: "Moderate yield, Moderate cost, Low water use, Moderate
environmental impact (confidence: high)".

### Observation
A genuinely dry-season Salem comparison (matching the "high irrigation
risk, conservative plan" narrative that motivated pulling this run) would
need a different year or season pulled from `data/raw/salem_rainfall.csv`
/ `salem_water_availability.csv` -- worth doing explicitly for the paper
rather than assumed. This is a good, concrete example for
`notes/viva_prep.md`: the fuzzy engine responds to the *actual* rainfall
and water readings for the specific season queried, not to a district's
general reputation.

---

## Pollachi -- Summer 2023

`run_id: pollachi_summer_2023_20260808T113729Z` -- 2 ha, preference
`balanced`; no clean cost ceiling visible across the 50 returned plans
(max cost Rs 63,925), so this run does not appear to have had a binding
budget cap.

*(Note: the saved run is Summer, not Kharif.)*

### Region snapshot
| | |
|---|---|
| Soil | Black Cotton Soil, pH 7.5, fertility index 75.9/100 |
| Rainfall | 48.6 mm/month avg, deviation +2.53% (normal), effective 136.08mm for the season |
| Water | 77.95% reservoir storage (Normal groundwater status) |

### Fuzzy assessment
| Output | Value | Label |
|---|---|---|
| Yield confidence | 0.860 | normal rainfall / high water / good soil |
| Irrigation risk | 0.140 | -- |

Highest yield confidence of the four districts in the currently-saved
runs -- Black Cotton Soil's fertility index (75.9) is the highest of the
four, and water storage, while lower in absolute percent than
Coimbatore/Salem, is still comfortably in the fuzzy engine's "high" band.

### NSGA-II run
pop=80, gen=200, 1.16s, 80 Pareto solutions found, 50 returned. Hypervolume
0.978 (gen 1) -> 1.407 (gen 200) -- notably higher than the other three
districts' hypervolume at gen 1 already; the smaller 2 ha land size and
correspondingly smaller absolute objective ranges change the normalised
hypervolume scale, so this isn't directly comparable to the other
districts' hypervolume numbers either (see the cross-region note below).

### Top 3 ranked plans (preference: `balanced`)
| Rank | Crop mix | Yield (t) | Cost (Rs) | Water (L) | Env. impact |
|---|---|---|---|---|---|
| 1 | Maize 100% | 11.41 | 63,710 | 4,814,908 | 94.3 |
| 2 | Maize 99%, Fodder Crops 1% | 11.66 | 63,478 | 4,818,267 | 93.8 |
| 3 | Maize 98%, Fodder Crops 2% | 11.91 | 63,253 | 4,821,517 | 93.3 |

All three: "Low yield, High cost, Low water use, High environmental impact
(confidence: high)" -- note "Low"/"High" here are *relative to this run's
own 50-plan set* (`ranking._plain_minmax`), not an absolute judgement; at
only 2 ha the absolute yield/cost/impact numbers are naturally much
smaller than Coimbatore's or Salem's 5 ha runs.

---

## Cross-region comparison -- fuzzy outputs only (the land-size-independent part)

| Region | Season | Soil type | Fertility | Yield Conf. | Irrig. Risk |
|---|---|---|---|---|---|
| Coimbatore | Kharif 2023 | Red Sandy Loam | 70.3 | 0.775 | 0.118 |
| Erode | Rabi 2023 | Red Laterite | 71.2 | 0.711 | 0.158 |
| Salem | Kharif 2023 | Red Loam | 67.8 | 0.742 | 0.120 |
| Pollachi | Summer 2023 | Black Cotton Soil | 75.9 | 0.860 | 0.140 |

All four of the currently-saved 2023 runs land in the fuzzy engine's
"normal rainfall / high water storage" region, so confidence stays in a
fairly narrow 0.71-0.86 band and risk stays low (0.12-0.16) across all
four districts -- there is no drought-conditions run in the currently-saved
set to contrast against. **This is a genuine finding worth stating
plainly** rather than smoothing over: it means these four particular
saved runs don't yet demonstrate the fuzzy engine's full range (the
low-confidence/high-risk corner is exercised directly in
`tests/test_fuzzy.py::TestFuzzyRuleBaseBehaviour`, but not yet by a real
saved regional run). Pulling one deliberately dry year/season per
district (or a poor-soil district/season combination) would make a
stronger regional-contrast section for the paper than the four
already-saved runs alone.

Plan-level figures (yield/cost/water/env) are not cross-region comparable
here since Coimbatore/Salem used 5 ha, Erode 3 ha, and Pollachi 2 ha.
