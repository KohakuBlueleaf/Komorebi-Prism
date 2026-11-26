"""Tile threads for the loop alone: TOY, one step that reads no list and writes
nothing; WALK, one step with a list pass over every layer, an ask, an output with its
convert, a kept space, a begin and a variant."""

from pathlib import Path

from prism.core.thread.module import ListPass, Output, Plane, Step, TileThread

KERNELS = Path(__file__).resolve().parent / "kernels"
PLANE = Plane("frame.toy", "fp32")


def every_layer(layers):
    """Every layer of the frame, in order."""
    return range(len(layers))


TOY = TileThread(
    steps=(
        Step(
            name="toy",
            header=str(KERNELS / "toy.hpp"),
            leaves=(PLANE.name,),
            depth=True,
        ),
    ),
    planes=(PLANE,),
)

WALK = TileThread(
    steps=(
        Step(
            name="walk",
            header=str(KERNELS / "walk.hpp"),
            passes=(ListPass(every_layer),),
            outputs=(Output("walk_out", 16 + 64, 2, "walk_convert"),),
            leaves=(PLANE.name,),
            keeps={"space": 64},
            codes={1: "walk_variant"},
            depth=True,
            begin=True,
        ),
    ),
    planes=(PLANE,),
)
