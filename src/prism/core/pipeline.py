"""A pipeline: the implementations that fill its items, in order, and what it is given."""

from prism.core.implementation import IMPLEMENTATIONS
from prism_common.build import build
from prism_common.registry import RegistryError
from prism_common.slots import Contract

ITEMS = ("raster", "material", "direct", "indirect", "reflect", "post")


class Pipeline:
    """`implementations` by registered name or dotted path, each resolved once; the
    slots in `inputs` are given to it."""

    def __init__(self, name, implementations, inputs=()):
        self.name = name
        self.inputs = tuple(inputs)
        self.implementations = tuple(self.resolved(item) for item in implementations)
        self.check()

    def resolved(self, choice):
        """One implementation of the list, by build()."""
        try:
            return build(choice, IMPLEMENTATIONS)
        except RegistryError as error:
            raise ValueError(f"pipeline {self.name!r}: {error}") from None

    def check(self):
        """Each item known and filled once; each read given or written earlier."""
        filled = {}
        for implementation in self.implementations:
            for item in implementation.fills:
                if item not in ITEMS:
                    raise ValueError(
                        f"pipeline {self.name!r}: {implementation.name} fills "
                        f"{item!r}, none of {', '.join(ITEMS)}"
                    )
                if item in filled:
                    raise ValueError(
                        f"pipeline {self.name!r}: item {item!r} filled twice, by "
                        f"{filled[item]} and by {implementation.name}"
                    )
                filled[item] = implementation.name
        Contract(reads=self.inputs).check(self)

    def names(self):
        """The implementations' names, in order."""
        return [implementation.name for implementation in self.implementations]
