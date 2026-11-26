"""What a stage gives the job thread: its C, the job commands it serves (each a C
function of the shape `uint32_t f(const km_command_t* command)`), the regions it asks
for (shared by every cluster of the image), its build-time defines."""

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Shared:
    """A region of the job thread, one copy that every cluster of the image reads:
    `bytes` an int or a function of the host; `contents` None or a function of the host
    giving its first words."""

    bytes: int | Callable
    contents: Callable | None = None

    def size(self, host):
        """Its bytes for `host`."""
        return int(self.bytes(host) if callable(self.bytes) else self.bytes)


@dataclass(frozen=True)
class Job:
    """A stage's part of the job thread: `folder` its sources' and includes' root;
    `serves` {command: C function}; `regions` {name: Shared}; `defines` a function of
    the host giving its build-time {name: text}."""

    folder: Path
    sources: tuple = ()
    includes: tuple = ()
    serves: dict = field(default_factory=dict)
    regions: dict = field(default_factory=dict)
    defines: Callable | None = None

    def __post_init__(self):
        for name, function in self.serves.items():
            if not name.isidentifier() or not function.isidentifier():
                raise ValueError(f"job: command {name!r} by {function!r}, not names")
        for name, region in self.regions.items():
            if not isinstance(region, Shared):
                raise TypeError(f"job: region {name!r} is not a Shared")

    def files(self):
        """Its sources and include folders as paths."""
        root = Path(self.folder)
        return [root / s for s in self.sources], [root / i for i in self.includes]

    def build_defines(self, host):
        """The -D definitions its C needs for `host`: {name: text}."""
        return {} if self.defines is None else dict(self.defines(host))
