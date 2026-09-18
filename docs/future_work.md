# Future Work Roadmap

**Author:** Gaddam Jahnavi (CB.SC.U4CSE23023)

This tracks the same remaining-work list as `CONTRIBUTING.md`'s "Real
remaining work" section -- restated here with more detail, and split into
near-term vs. longer-term so it's easy to reference for the guide review.

---

## Phase 1 -- near-term

### 1. Frontend (Vamsi)
React dashboard consuming the existing API (`app/main.py`, 6 endpoints,
already stable): a farm-input form, a Pareto-front / plan-comparison view,
a run-history browser (`GET /api/results`), and a downloadable plan
report. Deliberately sequenced after the backend/API shape stabilised
(see README "Status" section) rather than built in parallel against a
moving target.

### 2. Calibrate economic constants (Harshini)
Replace the approximate market-rate placeholders in `app/config.py`
(fertilizer Rs/kg-nutrient prices, labour daily wage) with sourced
figures -- TNAU price bulletins for fertilizer, current MGNREGA Tamil Nadu
rates for labour -- and document the source inline. See
`docs/assumptions.md` for exactly which constants these are.

### 3. Expand the fuzzy rule base (Harshini)
Current: 14 rules over 3 inputs (`docs/fuzzy_rules.md`). Candidate
extensions: district-specific rule variants, and/or a 4th input
(e.g. a rainfall-dependency-weighted crop signal) if the two-output
(`yield_confidence`, `irrigation_risk`) design proves too coarse once
calibrated against real outcomes.

### 4. Fuzzy vs. non-fuzzy comparison study (Sreenithya)
Run NSGA-II with `crop_yield_confidence` held at a constant 1.0 (fuzzy
layer effectively disabled) vs. the real fuzzy-adjusted run, on the same
seed/location/season, and compare: hypervolume trajectory, final Pareto
front spread, and whether the fuzzy-adjusted "balanced" recommendation
differs meaningfully from the non-fuzzy one. Feeds directly into the
paper's evaluation section.

### 5. Expand the test suite beyond the current 4 files (Sreenithya)
`tests/test_pipeline.py` (broad end-to-end), `test_fuzzy.py`,
`test_data.py`, `test_api.py` (module-focused) currently cover 113 cases
combined. Gaps worth closing next: `app/services/results_store.py`
error paths (corrupt JSON on disk, partial writes), and
`app/optimization/operators.py` unit tests isolated from the full NSGA-II
loop (crossover/mutation/repair behaviour on hand-built chromosomes).

### 6. Guide review status doc (Jahnavi)
Keep `notes/AgroOptimize_Guide_Review_Status.docx` current against
whatever the guide/panel actually asks in each review round.

---

## Phase 2 -- longer-term / paper-adjacent

- **IoT / live data.** Replace historical CSV snapshots with live sensor
  feeds (soil moisture, rain gauges, groundwater probes) or a weather API,
  instead of the current year-selected historical record.
- **ML surrogates.** A trained surrogate (Random Forest / XGBoost) as a
  faster fitness evaluator for a much larger population/generation count,
  if the current sub-second NSGA-II runtime ever becomes a bottleneck.
- **Geographic expansion.** Beyond the current 4 districts to more of
  Tamil Nadu, contingent on comparable data being available in the same
  16-column-family format (`docs/dataset_description.md`).
- **Multi-season / multi-year planning.** Currently optimises one
  (location, season, year) at a time; a rotation-aware multi-season
  objective is a natural but non-trivial extension (interacting
  constraints across seasons, not just within one).
- **Clearer infeasible-budget response.** Today, a budget too tight for
  any feasible plan returns an empty `plans` list
  (`notes/viva_prep.md` -- "What happens if the farmer's budget makes the
  problem infeasible"). A more useful response would surface the nearest
  feasible cost instead of silence.
