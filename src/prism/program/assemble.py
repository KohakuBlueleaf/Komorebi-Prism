"""A pipeline's implementations assembled into one program for one scene on a session."""

from dataclasses import dataclass, field

import komorebi as km

from prism.core.implementation import hosted
from prism.core.resources import Layout
from prism.program.director import thread


class MissingSlot(KeyError):
    """A slot a host asked for that no host gives."""

    def __init__(self, slot):
        super().__init__(slot)
        self.slot = slot


def held_slots(pipeline, hosts):
    """{slot: (implementation, tensor)} of every host's `slots()`; refused for a slot
    two hosts give, naming both."""
    held = {}
    for owner, host in hosts.items():
        for slot, tensor in hosted(host, "slots")().items():
            if slot in held:
                raise ValueError(
                    f"pipeline {pipeline.name!r}: slot {slot!r} given by "
                    f"{held[slot][0]} and by {owner}"
                )
            held[slot] = (owner, tensor)
    return held


def connected(assembled):
    """Each host's `connect(assembled)` in order; a slot one asks for that no host
    gives refused, naming the slot and the implementation."""
    for owner, host in assembled.hosts.items():
        try:
            hosted(host, "connect")(assembled)
        except MissingSlot as missing:
            raise ValueError(
                f"pipeline {assembled.pipeline.name!r}: {owner} asks for slot "
                f"{missing.slot!r}, which no host gives"
            ) from None


@dataclass
class Assembled:
    """The one program, each implementation's host and made class by name, the options
    it was assembled with, and its thread's layout (None without a unit)."""

    pipeline: object
    program: object
    hosts: dict
    made: dict
    options: dict
    layout: Layout | None = None
    slots: dict = field(default_factory=dict)  # slot: (implementation, tensor)

    def slot(self, name):
        """The tensor of slot `name`, as the host holding it gives it; MissingSlot
        when no host gives it."""
        if name not in self.slots:
            raise MissingSlot(name)
        return self.slots[name][1]

    def handler(self, name, handler):
        """The object to submit for `handler` of the implementation `name`."""
        if name not in self.made:
            raise KeyError(
                f"pipeline {self.pipeline.name!r} has no implementation {name!r}; "
                f"it has {', '.join(self.made)}"
            )
        return getattr(self.made[name], handler)


def assemble(pipeline, session, scene, options):
    """Each implementation's host prepared and its class made; the program the class
    itself for one implementation, `km.merge` of the made classes for several; then,
    when an implementation has a unit, the thread's layout and the thread. An
    implementation without a class (`device` None) has its host and unit only; a
    pipeline with no class at all is refused. After every host's prepare(), the
    slots the hosts give are held and each host connected."""
    if all(i.device is None for i in pipeline.implementations):
        raise ValueError(
            f"pipeline {pipeline.name!r}: no implementation has a class "
            f"({', '.join(pipeline.names())})"
        )
    hosts, made = {}, {}
    for implementation in pipeline.implementations:
        host = implementation.host(session, scene, options)
        host.prepare()
        hosts[implementation.name] = host
        if implementation.device is not None:
            made[implementation.name] = implementation.device(host)
    classes = list(made.values())
    program = classes[0] if len(classes) == 1 else km.merge(*classes, session=session)
    assembled = Assembled(pipeline, program, hosts, made, dict(options))
    assembled.slots = held_slots(pipeline, hosts)
    connected(assembled)
    units = [
        (implementation.name, implementation.thread, hosts[implementation.name])
        for implementation in pipeline.implementations
        if implementation.thread is not None
    ]
    if units:
        writes = {i.name: i.writes for i in pipeline.implementations}
        assembled.layout = Layout(units, writes)
        thread.declare(assembled, assembled.layout)
    return assembled
