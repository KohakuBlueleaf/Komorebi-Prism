"""What a host lets a person change in a live run: a control, its kind, its limits or
choices, its value, and the check of a value given for it."""

import math
from dataclasses import asdict, dataclass

KINDS = ("toggle", "range", "count", "choice", "direction")
ANGLES = ("azimuth", "elevation")  # a direction's angles, in order


@dataclass(frozen=True)
class Control:
    """A host's control: `kind` one of KINDS; `limits` (least, most) of a range or a
    count (a count's most None: no most), of a direction a (least, most) per angle
    (degrees); `choices` of a choice its (value, label) pairs; `value` the current."""

    name: str
    label: str
    kind: str
    value: object
    limits: tuple = ()
    choices: tuple = ()
    unit: str = ""
    help: str = ""

    def __post_init__(self):
        if self.kind not in KINDS:
            raise ValueError(
                f"control {self.name!r}: kind {self.kind!r} is none of "
                f"{', '.join(KINDS)}"
            )
        if self.kind == "direction" and len(self.limits) != len(ANGLES):
            raise ValueError(f"control {self.name!r}: limits for each of {ANGLES}")
        if self.kind == "choice" and not all(len(one) == 2 for one in self.choices):
            raise ValueError(f"control {self.name!r}: choices are (value, label)")

    def values(self):
        """A choice's values, in order."""
        return tuple(value for value, _ in self.choices)

    def checked(self, value):
        """`value` as this control holds it; TypeError or ValueError with the reason
        otherwise."""
        match self.kind:
            case "toggle":
                if not isinstance(value, bool):
                    raise TypeError(f"{self.name} is true or false, not {value!r}")
                return value
            case "range":
                return within(self.name, number(self.name, value), self.limits)
            case "count":
                if isinstance(value, bool) or not isinstance(value, int):
                    raise TypeError(f"{self.name} is a whole number, not {value!r}")
                return within(self.name, value, self.limits)
            case "choice":
                if value not in self.values():
                    named = (f"{value} ({label})" for value, label in self.choices)
                    raise ValueError(
                        f"{self.name} is one of {', '.join(named)}, not {value!r}"
                    )
                return value
            case "direction":
                if not isinstance(value, list | tuple) or len(value) != len(ANGLES):
                    raise ValueError(f"{self.name} is two angles, not {value!r}")
                return tuple(
                    within(f"{self.name}'s {angle}", number(self.name, one), limits)
                    for angle, one, limits in zip(ANGLES, value, self.limits)
                )

    def described(self):
        """The control as a dict of plain values."""
        return asdict(self)


def within(name, value, limits):
    """`value` inside `limits` (least, most; most None: no most); ValueError with them
    otherwise."""
    least, most = limits
    if most is None:
        if not least <= value:
            raise ValueError(f"{name} is {least} or more, not {value}")
        return value
    if not least <= value <= most:
        raise ValueError(f"{name} is {least} to {most}, not {value}")
    return value


def number(name, value):
    """`value` as a finite float; TypeError or ValueError naming the control
    otherwise."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{name} is a number, not {value!r}")
    if not math.isfinite(value):
        raise ValueError(f"{name} is a finite number, not {value}")
    return float(value)
