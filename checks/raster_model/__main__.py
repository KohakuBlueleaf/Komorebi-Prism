"""Runs every case in order: the C's sizes, the scenes, the C middle pass; exit 1 on a
difference."""

import json
import sys
import time

from checks.raster_model import middle_c, model
from checks.raster_model.compare import RESULTS
from prism.stages.raster import capacity as p_stage
from prism.stages.raster.model import numbers
from prism_common.paths import data_root
from prism_reference.scene.generated import make_preset
from prism_reference.scene.public.views import make_view


def main():
    """Runs every case; exit 1 when one differs."""
    data = data_root()
    started = time.perf_counter()
    middle_c.setup_sizes_case()
    library = middle_c.build(numbers.TILES, *p_stage.heavy_capacity(None))
    scenes = [(name, make_preset(name)) for name in ("tiny", "s10k")]
    scenes.append(("sponza", make_view("sponza_overview", data)))
    for name, scene in scenes:
        model.frame_case(name, scene)
        if name != "s10k":
            counts, rows, starts, ends = model.scene_counts(scene)
            for fill in model.FILLS:
                middle_c.c_case(name, library, counts, rows, starts, ends, fill)
    middle_c.c_case("seeded hot tiles", library, *middle_c.hot_counts(), 40)
    middle_c.large_cases()
    model.setup_writes_lists_case(scenes[0][1])
    different = [r["case"] for r in RESULTS if not r["equal"]]
    arrays = sum(r["arrays"] for r in RESULTS)
    seconds = round(time.perf_counter() - started, 1)
    summary = {"cases": len(RESULTS), "different": different, "arrays": arrays}
    print(json.dumps(summary | {"seconds": seconds}))
    return 1 if different else 0


if __name__ == "__main__":
    sys.exit(main())
