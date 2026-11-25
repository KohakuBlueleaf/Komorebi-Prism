"""Where data, caches and run outputs live, outside the repository."""

import os
from pathlib import Path

DATA_VARIABLE = "PRISM_DATA"
BUILD_VARIABLE = "PRISM_BUILD"
CACHE_VARIABLE = "PRISM_CACHE"


def data_root():
    """The data root: the folder named by $PRISM_DATA; an error naming it when unset."""
    value = os.environ.get(DATA_VARIABLE)
    if not value:
        raise RuntimeError(
            f"${DATA_VARIABLE} is not set: name the data root (scenes, lights, "
            f"results) with it"
        )
    return Path(value)


def build_root():
    """Where compiled helpers go: $PRISM_BUILD, else <data root>/build; made if missing."""
    value = os.environ.get(BUILD_VARIABLE)
    path = Path(value) if value else data_root() / "build"
    path.mkdir(parents=True, exist_ok=True)
    return path


def cache_root():
    """Where caches go: $PRISM_CACHE, else <data root>/cache; made if missing."""
    value = os.environ.get(CACHE_VARIABLE)
    path = Path(value) if value else data_root() / "cache"
    path.mkdir(parents=True, exist_ok=True)
    return path
