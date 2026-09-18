"""
Runs NSGA-II (Deb et al., 2002) over a FarmPlanProblem and decodes the
resulting Pareto front into plain farm-plan dictionaries.

NSGA-II retains only non-dominated solutions at each generation and uses
crowding distance to preserve diversity along the Pareto front (reference
paper, Section III-D) -- both behaviours are pymoo's NSGA2 defaults, so we
lean on the library for the selection/survival mechanics and supply our own
crossover/mutation/repair operators to match the paper's stated parameters.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import numpy as np
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.indicators.hv import HV
from pymoo.operators.sampling.rnd import FloatRandomSampling
from pymoo.optimize import minimize

from app import config
from app.data.preprocessing import RegionSeasonProfile
from app.fuzzy.engine import UncertaintyAssessment
from app.optimization.operators import AllocationRepair, GaussianMutation, SinglePointCrossover
from app.optimization.problem import FarmPlanProblem


@dataclass
class FarmPlan:
    crop_names: List[str]
    allocation_fraction: List[float]
    area_ha: List[float]
    irrigation_multiplier: List[float]
    fertilizer_multiplier: List[float]
    yield_tonnes: float
    cost_rs: float
    water_liters: float
    env_impact_score: float
    feasible: bool


def run_nsga2(
    problem: FarmPlanProblem,
    pop_size: Optional[int] = None,
    n_gen: Optional[int] = None,
    crossover_prob: float = config.NSGA2_CROSSOVER_PROB,
    mutation_prob: float = config.NSGA2_MUTATION_PROB,
    mutation_sigma: float = config.NSGA2_MUTATION_SIGMA,
    seed: int = config.NSGA2_SEED,
    verbose: bool = False,
    track_history: bool = False,
):
    """Run NSGA-II. Set `track_history=True` to have pymoo snapshot the
    population at every generation (needed for convergence plots / the
    hypervolume trend in `extract_convergence_history`); this costs extra
    time (~2-3x slower, still well under 2s at the paper's pop=80/gen=200
    settings) and memory, so it defaults to off for quick/test runs.
    """
    pop_size = pop_size or config.NSGA2_POP_SIZE
    n_gen = n_gen or config.NSGA2_N_GEN

    # Our custom operators (operators.py) draw from the plain numpy global
    # RNG (np.random.*), not from whatever internal RNG object pymoo wires
    # up for `seed=`. Seed it explicitly here so a given (problem, seed)
    # pair is fully reproducible end to end, independent of call history
    # elsewhere in the process.
    np.random.seed(seed)

    algorithm = NSGA2(
        pop_size=pop_size,
        sampling=FloatRandomSampling(),
        crossover=SinglePointCrossover(prob=crossover_prob),
        mutation=GaussianMutation(prob=mutation_prob, sigma=mutation_sigma),
        repair=AllocationRepair(),
        eliminate_duplicates=True,
    )

    result = minimize(
        problem,
        algorithm,
        ("n_gen", n_gen),
        seed=seed,
        verbose=verbose,
        save_history=track_history,
    )
    return result


def run_nsga2_with_fuzzy_toggle(
    profile: RegionSeasonProfile,
    assessment: UncertaintyAssessment,
    total_land_ha: float,
    budget_rs: Optional[float] = None,
    use_fuzzy: bool = True,
    **run_kwargs,
):
    """Convenience entry point for the Task 4 fuzzy-vs-non-fuzzy comparison
    study: builds a FarmPlanProblem with `use_fuzzy` applied (see
    CropVector.from_candidates / FarmPlanProblem in app/optimization/
    problem.py -- that's where the actual fuzzy-bypass logic lives) and
    runs it through the normal `run_nsga2`. `use_fuzzy=True` reproduces the
    exact behaviour every other caller (plan_service, dashboard_service)
    already gets; `use_fuzzy=False` is the non-fuzzy baseline, where every
    crop's yield confidence is trusted at 1.0 instead of being adjusted by
    the Mamdani rule base. Any extra `run_kwargs` (pop_size, n_gen, seed,
    etc.) pass straight through to `run_nsga2`.
    """
    problem = FarmPlanProblem(
        profile=profile,
        assessment=assessment,
        total_land_ha=total_land_ha,
        budget_rs=budget_rs,
        use_fuzzy=use_fuzzy,
    )
    result = run_nsga2(problem, **run_kwargs)
    return problem, result


def extract_convergence_history(result) -> List[dict]:
    """Per-generation convergence statistics, requires `run_nsga2(...,
    track_history=True)`. Returns [] if history wasn't tracked.

    For each generation: the best (min) and mean of every raw objective
    across that generation's surviving population, plus a normalised
    hypervolume indicator (Zitzler & Thiele, 1999) -- the standard
    MOEA convergence metric, tracking how much of the (normalised)
    objective space the current front dominates relative to a fixed
    reference point. A rising, plateauing hypervolume curve is the
    textbook signature of NSGA-II converging.
    """
    if not getattr(result, "history", None):
        return []

    all_F = np.vstack([snapshot.pop.get("F") for snapshot in result.history])
    lo = all_F.min(axis=0)
    hi = all_F.max(axis=0)
    span = np.where(hi - lo < 1e-9, 1.0, hi - lo)
    # Fixed reference point in normalised space, slightly worse than the
    # worst value seen in any generation on every objective (required by
    # the hypervolume definition -- larger normalised F is worse here
    # since every objective is a "minimise" in FarmPlanProblem).
    hv_indicator = HV(ref_point=np.array([1.1, 1.1, 1.1, 1.1]))

    history: List[dict] = []
    for gen_idx, snapshot in enumerate(result.history, start=1):
        F = snapshot.pop.get("F")
        F_norm = np.clip((F - lo) / span, 0.0, 1.5)
        history.append(
            {
                "generation": gen_idx,
                "population_size": int(F.shape[0]),
                "best_yield_tonnes": round(float(-F[:, 0].min()), 3),
                "mean_yield_tonnes": round(float(-F[:, 0].mean()), 3),
                "best_cost_rs": round(float(F[:, 1].min()), 2),
                "mean_cost_rs": round(float(F[:, 1].mean()), 2),
                "best_water_liters": round(float(F[:, 2].min()), 1),
                "mean_water_liters": round(float(F[:, 2].mean()), 1),
                "best_env_impact": round(float(F[:, 3].min()), 3),
                "mean_env_impact": round(float(F[:, 3].mean()), 3),
                "hypervolume": round(float(hv_indicator(F_norm)), 4),
            }
        )
    return history


def extract_pareto_plans(result, problem: FarmPlanProblem) -> List[FarmPlan]:
    """Decode every non-dominated solution pymoo found into a FarmPlan."""
    if result.X is None or len(result.X) == 0:
        return []

    X = np.atleast_2d(result.X)
    F = np.atleast_2d(result.F)
    G = np.atleast_2d(result.G) if result.G is not None else None

    plans: List[FarmPlan] = []
    for i in range(X.shape[0]):
        decoded = problem.decode(X[i])
        f1, f2, f3, f4 = F[i]
        feasible = True
        if G is not None:
            feasible = bool(np.all(G[i] <= 1e-6))
        plans.append(
            FarmPlan(
                crop_names=decoded["crop_names"],
                allocation_fraction=decoded["allocation_fraction"],
                area_ha=decoded["area_ha"],
                irrigation_multiplier=decoded["irrigation_multiplier"],
                fertilizer_multiplier=decoded["fertilizer_multiplier"],
                yield_tonnes=round(float(-f1), 3),
                cost_rs=round(float(f2), 2),
                water_liters=round(float(f3), 1),
                env_impact_score=round(float(f4), 3),
                feasible=feasible,
            )
        )
    return plans
