"""
Persists every optimisation run to disk under results/, so a run has a
record independent of the API response it produced (which otherwise only
exists for the lifetime of one HTTP request / CLI invocation).

Each run writes up to four files, all sharing one `run_id`
(`<location>_<season>_<year>_<UTC timestamp>`):

    results/<run_id>.json               full response + convergence history
    results/<run_id>_plans.csv          flattened ranked-plan table (Excel/Sheets-friendly)
    results/<run_id>_convergence.csv    per-generation convergence stats
    results/<run_id>_convergence.png    hypervolume + best-yield/cost convergence chart
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import pandas as pd

from app import config


def _slugify(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", str(text)).strip("-").lower()


def make_run_id(location: str, season: str, year: int) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{_slugify(location)}_{_slugify(season)}_{year}_{ts}"


@dataclass
class SavedRunFiles:
    run_id: str
    json_path: str
    plans_csv_path: str
    convergence_csv_path: Optional[str] = None
    convergence_plot_path: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


def save_run_results(
    response: dict,
    convergence_history: List[dict],
    out_dir: Path = config.RESULTS_DIR,
    client_id: Optional[str] = None,
) -> SavedRunFiles:
    """Write one run's full results to `out_dir`. Safe to call with an
    empty `convergence_history` (e.g. when the run used
    track_history=False) -- the convergence CSV/plot are simply skipped.

    `client_id` (optional) is the per-browser id the request came in with
    -- stored on the record so GET /api/history/{location} can show this
    run back only to the client that generated it. Older records saved
    before this existed simply have no client_id and so won't match any
    real requester going forward.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    profile = response["region_profile"]
    run_id = make_run_id(profile["location"], profile["season"], profile["year"])

    full_record = dict(response)
    full_record["run_id"] = run_id
    full_record["saved_at"] = datetime.now(timezone.utc).isoformat()
    full_record["client_id"] = client_id
    full_record["convergence_history"] = convergence_history

    json_path = out_dir / f"{run_id}.json"
    json_path.write_text(json.dumps(full_record, indent=2))

    plans_csv_path = out_dir / f"{run_id}_plans.csv"
    plans_df = pd.DataFrame(response["plans"])
    for col in plans_df.columns:
        if plans_df[col].apply(lambda v: isinstance(v, (list, dict))).any():
            plans_df[col] = plans_df[col].apply(json.dumps)
    plans_df.to_csv(plans_csv_path, index=False)

    convergence_csv_path = None
    convergence_plot_path = None
    if convergence_history:
        conv_df = pd.DataFrame(convergence_history)
        convergence_csv_path = out_dir / f"{run_id}_convergence.csv"
        conv_df.to_csv(convergence_csv_path, index=False)
        convergence_plot_path = _plot_convergence(
            conv_df, out_dir / f"{run_id}_convergence.png", run_id, profile
        )

    return SavedRunFiles(
        run_id=run_id,
        json_path=str(json_path),
        plans_csv_path=str(plans_csv_path),
        convergence_csv_path=str(convergence_csv_path) if convergence_csv_path else None,
        convergence_plot_path=str(convergence_plot_path) if convergence_plot_path else None,
    )


def _plot_convergence(conv_df: pd.DataFrame, out_path: Path, run_id: str, profile: dict) -> Path:
    import matplotlib

    matplotlib.use("Agg")  # headless -- no display server in the sandbox / on a server
    import matplotlib.pyplot as plt

    fig, (ax_hv, ax_obj) = plt.subplots(1, 2, figsize=(11, 4.2))

    ax_hv.plot(conv_df["generation"], conv_df["hypervolume"], color="#2a7f3f")
    ax_hv.set_title("Hypervolume (normalised) vs. generation")
    ax_hv.set_xlabel("Generation")
    ax_hv.set_ylabel("Hypervolume")
    ax_hv.grid(alpha=0.3)

    ax_obj.plot(conv_df["generation"], conv_df["best_yield_tonnes"], color="#2a7f3f", label="best yield (t)")
    ax_obj.set_xlabel("Generation")
    ax_obj.set_ylabel("Best yield (t)", color="#2a7f3f")
    ax_obj.tick_params(axis="y", labelcolor="#2a7f3f")
    ax_obj.grid(alpha=0.3)

    ax_cost = ax_obj.twinx()
    ax_cost.plot(conv_df["generation"], conv_df["best_cost_rs"], color="#b5651d", label="best cost (Rs)")
    ax_cost.set_ylabel("Best cost (Rs)", color="#b5651d")
    ax_cost.tick_params(axis="y", labelcolor="#b5651d")
    ax_obj.set_title("Best yield & cost vs. generation")

    fig.suptitle(
        f"NSGA-II convergence -- {profile['location']} / {profile['season']} / {profile['year']}  ({run_id})",
        fontsize=10,
    )
    fig.tight_layout()
    fig.savefig(out_path, dpi=130)
    plt.close(fig)
    return out_path


def list_saved_runs(out_dir: Path = config.RESULTS_DIR) -> List[dict]:
    out_dir = Path(out_dir)
    if not out_dir.exists():
        return []
    runs = []
    for json_path in sorted(out_dir.glob("*.json"), reverse=True):
        try:
            record = json.loads(json_path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        runs.append(
            {
                "run_id": record.get("run_id", json_path.stem),
                "location": record["region_profile"]["location"],
                "season": record["region_profile"]["season"],
                "year": record["region_profile"]["year"],
                "preference": record.get("meta", {}).get("preference"),
                "saved_at": record.get("saved_at"),
                "n_plans": len(record.get("plans", [])),
                "client_id": record.get("client_id"),
            }
        )
    return runs


def load_run(run_id: str, out_dir: Path = config.RESULTS_DIR) -> Optional[dict]:
    out_dir = Path(out_dir)
    path = out_dir / f"{run_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())
