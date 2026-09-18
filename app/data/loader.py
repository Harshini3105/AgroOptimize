"""
Raw CSV loading with a simple in-memory cache.

The dataset is organised as one CSV per (location, kind) pair, e.g.
data/raw/coimbatore_crop.csv, data/raw/erode_rainfall.csv, ...
All four locations share an identical column schema per kind, so we can
safely concatenate them into one DataFrame per kind.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Dict

import pandas as pd

from app import config


def _read_kind(kind: str) -> pd.DataFrame:
    frames = []
    for location in config.LOCATIONS:
        path = config.RAW_DATA_DIR / f"{location.lower()}_{kind}.csv"
        if not path.exists():
            raise FileNotFoundError(
                f"Expected dataset file not found: {path}. "
                f"Make sure data/raw/ contains a '{kind}' CSV for every location "
                f"in app.config.LOCATIONS."
            )
        df = pd.read_csv(path)
        frames.append(df)
    combined = pd.concat(frames, ignore_index=True)
    return combined


@lru_cache(maxsize=1)
def load_all() -> Dict[str, pd.DataFrame]:
    """Load and cache all four dataset kinds, concatenated across locations.

    Returns a dict with keys: "crop", "land", "rainfall", "water".
    """
    return {
        "crop": _read_kind("crop"),
        "land": _read_kind("land"),
        "rainfall": _read_kind("rainfall"),
        "water": _read_kind("water_availability"),
    }


def clear_cache() -> None:
    """Drop the cached dataframes (mainly useful for tests)."""
    load_all.cache_clear()


def available_locations() -> list[str]:
    return list(config.LOCATIONS)


def available_years(kind: str = "crop") -> list[int]:
    df = load_all()[kind]
    return sorted(int(y) for y in df["Year"].unique())


def available_seasons() -> list[str]:
    return list(config.AG_SEASONS)
