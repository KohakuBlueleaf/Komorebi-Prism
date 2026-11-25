"""The preset `field`: the indirect field's update alone, the transport's apply a pass,
an update an `update` command to the thread."""

from prism import stages  # noqa: F401  (registers the implementations)
from prism.core.pipeline import Pipeline

PIPELINE = Pipeline(
    "field",
    ["indirect.transport", "indirect.field_update"],
    inputs=("elements.radiance", "light.shadow_map"),
)
OPTIONS = {"bounces": 2, "sun": (120.0, 40.0), "updates": 2, "stepped": False}
