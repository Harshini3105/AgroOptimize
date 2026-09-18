# Problem Statement

**Author:** Gaddam Jahnavi (CB.SC.U4CSE23023)

---

## The problem

Farmers in Tamil Nadu must decide, every season:
- Which crops to plant
- How to allocate land across multiple crops
- How much to irrigate each crop
- How much fertilizer to apply

...under conditions that are never known with certainty: rainfall varies
year to year, soil moisture shifts with weather, and groundwater
availability is unpredictable.

## Why simpler decision-support approaches fall short

**Single-objective optimisation.** Tools that optimise only yield ignore
cost; tools that optimise only cost ignore yield. Real farming needs
yield, cost, water use, and environmental impact weighed together, and the
right trade-off differs by farmer.

**No uncertainty modelling.** Treating last year's rainfall as this
year's forecast, or soil quality as static, throws away exactly the
information a farmer most needs help reasoning about: how confident should
I be in this "book" yield number, given what I actually know about this
season?

**Not region-specific.** Tamil Nadu's agricultural zones differ
meaningfully in soil type and rainfall/water profile (see
`docs/dataset_description.md` and `docs/results/`) -- a generic,
one-size-fits-all recommendation doesn't reflect that.

---

## This project's approach

1. Loads real district-level agricultural data (soil, rainfall,
   crop-history, water-availability -- 2020-2023, 4 Tamil Nadu districts).
2. Uses a Mamdani fuzzy inference engine to convert rainfall/water/soil
   readings into two uncertainty-aware scenario weights
   (`yield_confidence`, `irrigation_risk`).
3. Runs a custom NSGA-II to optimise land allocation, irrigation, and
   fertilizer decisions across 4 objectives at once (yield, cost, water,
   environmental impact).
4. Ranks the resulting Pareto-optimal plans with TOPSIS, under one of 5
   farmer-selectable preference modes, with a plain-language trade-off
   summary attached to each plan.

### Why this is different
- Uncertainty is modelled explicitly, not collapsed into a single "best
  guess" number.
- All 4 objectives are optimised together; the farmer chooses the
  trade-off afterwards instead of the system guessing weights up front.
- Grounded in real multi-district Tamil Nadu data rather than a synthetic
  or single-region example.

---

## Reference methodology

This backend implements the pipeline described in *"A fuzzy-evolutionary
decision support system for agricultural farming under uncertainties"*
(23CSE498 Project Phase II) -- see `README.md` and
`notes/methodology_notes.md` for exactly which sections of that
methodology map to which module, and `docs/literature_survey.md` Section
"Our contribution" for how this implementation's scope compares to it.

Current status: the backend (data pipeline, fuzzy engine, NSGA-II
optimiser, TOPSIS ranking, REST API, automated tests) is built and
passing; the frontend is deliberately deferred until the UI is finalised
(see `docs/future_work.md`). Not yet a submitted or published paper --
`docs/assumptions.md` and `notes/methodology_notes.md` Section 9 list what
still needs calibration/validation before that would be appropriate.
