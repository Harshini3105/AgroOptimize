# Literature Survey

**Author:** Gaddam Jahnavi (CB.SC.U4CSE23023)
**Project:** AgroOptimize -- Team 52

Every entry below was checked against a live source before being included
(title, authors, venue, year, and DOI where available) -- see the note in
`CONTRIBUTING.md`: this survey isn't allowed to cite anything that wasn't
actually verified. Sources are listed under each entry.

---

## Surveyed papers

### [1] Deb, Pratap, Agarwal & Meyarivan (2002) -- NSGA-II
**Title:** A Fast and Elitist Multiobjective Genetic Algorithm: NSGA-II
**Venue:** IEEE Transactions on Evolutionary Computation, 6(2), 182-197
**DOI:** 10.1109/4235.996017
**Algorithm:** NSGA-II
**Contribution:** Introduces fast non-dominated sorting, crowding-distance
diversity preservation, and elitist parent+offspring survival -- the
foundational multi-objective evolutionary algorithm this project's
`app/optimization/nsga2_runner.py` builds on (via `pymoo`).
**Research gap (relative to this project):** General-purpose algorithm,
no agricultural application and no uncertainty modelling of any kind.

### [2] Huang, Pu, Zhang et al. (2025) -- Fuzzy-Expert enhanced NSGA-II
**Title:** A Fuzzy-Expert enhanced NSGA-II approach for sustainable
agricultural systems
**Venue:** Scientific Reports, 15, Article 34070
**Algorithm:** Fuzzy-Expert-NSGA-II (adds a Hybrid Adaptive Local Search
and an Expert Rule-based Repair module on top of NSGA-II)
**Contribution:** Combines expert fuzzy rules with NSGA-II for
multi-period crop planning, validated on a 41-crop / 54-plot case study in
Chehe Village, Shanxi Province, China.
**Research gap (relative to this project):** China-specific case study,
not Tamil Nadu; the fuzzy layer is an expert rule-repair mechanism scoped
to planting-strategy feasibility, not a Mamdani model of rainfall/water/
soil-fertility uncertainty feeding the objective function directly the way
`app/fuzzy/engine.py` does.

### [3] Karamian, Mirakzadeh & Azari (2023) -- WEF nexus GA
**Title:** Application of Multi-Objective Genetic Algorithm for Optimal
Combination of Resources to Achieve Sustainable Agriculture Based on the
Water-Energy-Food Nexus Framework
**Venue:** Science of The Total Environment, 860, Article 160419
**Algorithm:** Multi-objective genetic algorithm
**Contribution:** Optimises a water-energy-food nexus index and a social
dimension while minimising environmental impact, for resource allocation
in agriculture.
**Research gap (relative to this project):** Nexus-indicator framing
rather than per-crop land/irrigation/fertilizer allocation; no explicit
fuzzy treatment of climate/soil measurement uncertainty.

### [4] Margarit et al. (2025) -- Trade-offs under uncertainty
**Title:** Investigating Tradeoffs Between Competing Agricultural
Objectives Using Multi-Objective Optimization Under Uncertainty
**Venue:** Frontiers in Environmental Science, 13
**DOI:** 10.3389/fenvs.2025.1634272
**Algorithm:** Multi-objective optimisation with Bayesian history-matching
(PESTPP-IES ensemble smoother)
**Contribution:** Studies trade-offs between economic benefit, regulatory
groundwater-quality compliance, and equitable revenue distribution,
explicitly propagating uncertainty through Bayesian ensemble methods.
**Research gap (relative to this project):** Groundwater-quality /
regulatory-compliance framing rather than crop-mix planning; uncertainty
handled via Bayesian ensembles rather than fuzzy logic, and no
NSGA-II-style Pareto front over yield/cost/water/environmental-impact.

### [5] Erdoğdu, Dayi, Yıldız, Yanık & Ganji (2025) -- Fuzzy logic + GA
**Title:** Combining Fuzzy Logic and Genetic Algorithms to Optimize Cost,
Time and Quality in Modern Agriculture
**Venue:** Sustainability, 17(7), 2829
**DOI:** 10.3390/su17072829
**Algorithm:** Fuzzy multi-objective optimisation + genetic algorithm
**Contribution:** Combines fuzzy logic with a GA to manage the
cost-time-quality trade-off in agricultural projects, aimed at scaling to
large projects.
**Research gap (relative to this project):** Project-management-style
cost/time/quality objectives rather than yield/cost/water/environment; a
single combined fuzzy-GA stage rather than a two-stage "fuzzy uncertainty
first, then NSGA-II" pipeline; not evaluated against real multi-district
agricultural data.

---

## Research gap summary

Across these five, the pattern is consistent: papers either do
multi-objective **optimisation** without explicit **uncertainty**
modelling ([1], [3]), or combine fuzzy/uncertainty methods with
optimisation but in a different domain framing or geography than this
project's ([2], [4], [5]). None combines a Mamdani fuzzy layer over
rainfall/water/soil uncertainty with an NSGA-II search over
yield/cost/water/environmental-impact, validated on real Tamil Nadu
district-level data.

## Our contribution

AgroOptimize's approach:
1. A Mamdani fuzzy inference layer (`app/fuzzy/engine.py`) converts
   rainfall/water/soil readings into `yield_confidence` and
   `irrigation_risk`, feeding directly into the NSGA-II yield objective
   rather than being a separate advisory output.
2. NSGA-II optimises 4 objectives simultaneously (yield, cost, water,
   environmental impact), with custom operators matching a specified
   paper's parameters (single-point crossover p=0.85, Gaussian mutation
   p=0.12).
3. Validated on real multi-year, multi-district Tamil Nadu agricultural
   data (Coimbatore, Erode, Salem, Pollachi; 2020-2023) rather than a
   synthetic or single-region example.
4. TOPSIS-ranked, plain-language trade-off summaries make the Pareto front
   directly actionable for a farmer choosing between plans.
