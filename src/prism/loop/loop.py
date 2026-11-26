"""A pipeline kept loaded: a frame a camera, a change of size, the hosts' recoveries, and
every frame's times row kept across reloads."""

import time
from dataclasses import dataclass, replace

import komorebi as km
import numpy as np

from prism.core.implementation import command_of, hosted
from prism.loop import capacity
from prism.program.form import form_of
from prism_reference.scene.camera import with_size


@dataclass
class Frame:
    """A frame's final code, its picture when asked (None otherwise), the index of its
    times row (Loop.times), the retries and reloads it took."""

    code: int
    picture: object = None
    row: int = -1
    retries: int = 0
    reloads: int = 0


class Loop:
    """`pipeline` loaded on `session` for `scene` (its WIDTH x HEIGHT view) at `size`,
    assembled and loaded by its form (prism.program.form, chosen once): `frame(camera)`
    a frame, `resize(size)`, `times()` after `stop()`."""

    def __init__(self, pipeline, session, scene, size, options):
        self.pipeline, self.session, self.scene = pipeline, session, scene
        self.form = form_of(pipeline)
        self.size = tuple(int(n) for n in size)
        self.options = dict(options)
        self.held = None
        self.loaded = self.stopped = None
        self.rows = []  # the times rows of the loads before this one
        self.beside = []  # (host, Command, handle) submitted beside the frames
        self.reloads, self.retries, self.sizes = [], 0, [self.size]
        self.recoveries = []  # each retry's record: the code, what changed, ms
        self.load()
        self.held = capacity.held_of(capacity.needs(self.hosts(), self.size))

    @classmethod
    def open(cls, pipeline, session, scene, size, options):
        """The loop with its first load done."""
        return cls(pipeline, session, scene, size, options)

    @property
    def assembled(self):
        return self.loaded.assembled

    def hosts(self):
        """The hosts in the pipeline's order."""
        return list(self.loaded.hosts.values())

    def load(self):
        """Assembled for the size at the capacity held, and loaded; a refusal for the
        capacity as CapacityRefused with the refusal's numbers."""
        options = self.options | {"size": self.size, "capacity": self.held}
        scene = with_size(self.scene, self.size)
        try:
            assembled = self.form.assemble(self.pipeline, self.session, scene, options)
            self.loaded = self.form.load(assembled, self.session)
        except (ValueError, km.KomorebiError) as error:
            if self.held is None:
                raise
            raise capacity.CapacityRefused(self.size, self.held, error) from error

    def kept(self):
        """The loaded run stopped, its times rows kept (a row lost to the ring: None);
        ValueError when the run ended with an error."""
        loaded = self.loaded
        if self.stopped is loaded:
            return
        self.collect(wait=True)
        result, self.stopped = loaded.stop(), loaded
        rows = loaded.times()
        self.rows += [None] * (loaded.served - len(rows)) + rows
        if result["error_name"] != "none":
            raise km.KomorebiError(f"the run ended with {result['error_name']}")

    def reload(self, held, why):
        """Stopped, assembled and loaded again at `held` with the options the hosts
        raised; its record (why, size, capacity, seconds)."""
        began = time.perf_counter()
        self.kept()
        self.options = dict(self.loaded.options)
        self.held = held
        self.load()
        self.reloads.append(
            {
                "why": why,
                "size": list(self.size),
                "capacity": [held.tiles, held.wide],
                "s": round(time.perf_counter() - began, 3),
            }
        )

    def collect(self, wait=False):
        """The commands beside the frames whose events have come (`wait`: each one,
        waited for), each served to its host in turn: the first code that is not 0."""
        first = 0
        for entry in list(self.beside):
            host, command, handle = entry
            if wait:
                code = self.loaded.answer(handle)
            else:
                code = self.loaded.arrived(handle)
            if code is None:
                continue
            self.beside.remove(entry)
            hosted(host, "served")(self.loaded, command.name, code)
            first = first or code
        return first

    def attempt(self, camera):
        """The hosts' views in order, the commands beside the frames that came back
        served, the commands the hosts ask for (one beside the frames submitted; the
        first code that is not 0 ends the attempt with it), then the FRAME command:
        its code."""
        for host in self.hosts():
            hosted(host, "view")(self.loaded, camera, self.size)
        code = self.collect()
        if code:
            return code
        for host in self.hosts():
            for asked in hosted(host, "commands")(self.loaded):
                command = command_of(asked)
                if command.beside:
                    handle = self.loaded.submit(command.name, command.args)
                    self.beside.append((host, command, handle))
                    continue
                code = self.loaded.serve(command.name, command.args, command.row)
                hosted(host, "served")(self.loaded, command.name, code)
                if code:
                    return code
        return self.loaded.frame()

    def recovery(self, code):
        """The first answer of the hosts' recover in order and its host, or (None,
        None)."""
        for host in self.hosts():
            answer = hosted(host, "recover")(self.loaded, code)
            if answer is not None:
                return answer, host
        return None, None

    def frame(self, camera, picture=False):
        """A frame of `camera` (16,) float32 at the size: on a code the hosts'
        recovery, a retry and a reload at most once each; its Frame."""
        camera = np.asarray(camera, dtype=np.float32)
        code, retries, reloads = self.attempt(camera), 0, 0
        while code:
            began = time.perf_counter()
            answer, host = self.recovery(code)
            if answer == "retry" and not retries:
                retries, self.retries = 1, self.retries + 1
                ms = round((time.perf_counter() - began) * 1e3, 3)
                record = {"code": code, "ms": ms}
                self.recoveries.append(record | hosted(host, "recovered")())
            elif answer == "reload" and not reloads:
                asked = capacity.needs(self.hosts(), self.size)
                reloads = 1
                self.reload(capacity.held_of(asked, self.held), f"code {code}")
            else:
                break
            code = self.attempt(camera)
        row = len(self.rows) + self.loaded.served - 1
        out = Frame(code, None, row, retries, reloads)
        if picture and code == 0:
            out.picture = self.picture().copy()  # a Frame keeps its own picture
        return out

    def picture(self):
        """The last frame's picture: of the last host in the pipeline's order whose
        `pictures` is true (no other host is asked), valid until the next frame (a
        host may keep one image); None when none gives one."""
        for host in reversed(self.hosts()):
            if getattr(host, "pictures", False):
                return host.picture(self.loaded)
        return None

    def resize(self, size):
        """The next frames at `size` (W, H): a reload only when the capacity held does
        not cover the hosts' needs; True when it reloaded."""
        size = tuple(int(n) for n in size)
        held = capacity.reload_to(self.held, self.hosts(), size)
        self.size = size
        self.sizes.append(size)
        if held is not None:
            self.reload(held, "size")
        return held is not None

    def controls(self):
        """Every host's controls in the pipeline's order, each named
        `<implementation>.<name>`."""
        return [
            replace(control, name=f"{implementation}.{control.name}")
            for implementation, host in self.loaded.hosts.items()
            for control in hosted(host, "controls")()
        ]

    def set(self, name, value):
        """The control `name` (`<implementation>.<name>`) set to `value`: None when
        applied live, "reload" when it was loaded again (its record in reloads);
        ValueError (TypeError: of a wrong type) with the reason when unknown, out of
        its limits or refused."""
        for implementation, host in self.loaded.hosts.items():
            if not name.startswith(f"{implementation}."):
                continue
            own = {control.name: control for control in hosted(host, "controls")()}
            control = own.get(name[len(implementation) + 1 :])
            if control is None:
                continue
            answer = hosted(host, "set")(
                self.loaded, control.name, control.checked(value)
            )
            if answer == "reload":
                self.reload(self.held, f"control {name}")
            elif answer is not None:
                raise ValueError(answer)
            return answer
        raise ValueError(f"no control {name!r}")

    def stop(self):
        """The run stopped, its times rows kept."""
        self.kept()

    def times(self):
        """Every times row of the frames served (each attempt's), in order; after
        stop()."""
        return list(self.rows)
