"""The preset `apply`: the light-transport apply alone, on every core."""

from prism import stages  # noqa: F401  (registers the implementations)
from prism.core.pipeline import Pipeline

PIPELINE = Pipeline("apply", ["indirect.transport"], inputs=("elements.radiance",))
OPTIONS = {"calls": 32}
