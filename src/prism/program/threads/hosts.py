"""The stage-wise hosts as the threads' form holds them: the light's numbers of its
threads' unit, the display always given as a slot, the transport's apply as a queued
command's words, the field's update as the job thread's job run by a kept graph."""

from prism.program.jobs.frame import COMMAND as WANTS
from prism.program.jobs.host import JobThread
from prism.stages.direct.light.host import LightHost
from prism.stages.direct.light.model.sun import sun_lights
from prism.stages.direct.light.model.terms import light_pages
from prism.stages.indirect.field_update.graph import FieldGraph
from prism.stages.indirect.field_update.host import FieldUpdateHost
from prism.stages.indirect.transport.host import TransportHost
from prism.stages.post.show.host import ShowHost

APPLY = "apply"  # the transport's handler the graph queues
IRRADIANCE = "elements.irradiance"  # the slot the transport's implementation writes


class LightThreadsHost(LightHost):
    """LIGHT's host with the light step's numbers (the light pages, the glass layer,
    the field's first page and a half's pages) in place of the surfaces'."""

    def thread_numbers(self):
        """The threads' light unit's numbers (0 for a field it does not hold)."""
        glass = self.glass and "glass" in self.order
        first, pages = 0, 0
        if self.field is not None:
            first = int(self.first["field"])
            pages = len(self.field["pages"])
        return {
            "light_pages": self.pages.address,
            "light_glass": 1 + self.order.index("glass") if glass else 0,
            "light_field_first": first,
            "light_field_pages": pages,
        }

    def prepare(self):
        """As LIGHT's, with each part's first page of the light pages kept."""
        super().prepare()
        self.first = light_pages(self.lights, self.field)[1]


class ShowThreadsHost(ShowHost):
    """SHOW's host whose display is always given (slot display.picture): the post
    step writes it."""

    def slots(self):
        """The display tensor as display.picture."""
        return {"display.picture": self.tensors["display"]}


class TransportThreadsHost(TransportHost):
    """The transport's host with no thread unit: its apply is queued by the field
    update's graph on the cores the allocator finds."""

    def bind(self, loaded):
        """Nothing: no number of a thread unit."""

    def apply_args(self, handler):
        """The command words of `handler` (its apply) on the tensors held."""
        return handler.args(*self.words(APPLY))


def transport_of(assembled):
    """(name, host) of the implementation that writes IRRADIANCE with a class."""
    for implementation in assembled.pipeline.implementations:
        if (
            IRRADIANCE in implementation.writes
            and implementation.name in assembled.made
        ):
            return implementation.name, assembled.hosts[implementation.name]
    raise ValueError(
        f"pipeline {assembled.pipeline.name!r}: no class writes {IRRADIANCE}"
    )


class FieldJobHost(FieldUpdateHost):
    """The field update's host as the job thread's job: its numbers in the job's
    region, its graph (FieldGraph) made and kept on the run, no thread command."""

    def bind(self, loaded):
        """The job thread of the run, the graph of the update (the frame thread's
        job_wants, the transport's apply on its cores), its numbers, its upload."""
        self.loaded = loaded
        assembled = loaded.assembled
        name, transport = transport_of(assembled)
        apply = assembled.handler(name, APPLY)
        self.graph = FieldGraph(
            self,
            JobThread(loaded.run, assembled.jobs),
            loaded.run,
            assembled.layout.handlers()[WANTS],
            apply,
            transport.apply_args(apply),
            transport.cores,
        )
        self.graph.write_numbers(self.written())
        self.graph.graph_for(self.bounces)

    def commands(self, loaded):
        """None: an update that ended taken; when the loop's sun or the bounces are
        not the field's and none runs, the graph started for the lights at the sun."""
        self.graph.served()
        if self.graph.handle is not None:
            return []
        sun = loaded.options.get("sun")
        sun = None if sun is None else tuple(float(n) for n in sun)
        if (sun, self.bounces) == self.made:
            return []
        lights = self.own_lights
        if sun is not None:
            lights = sun_lights(self.own_lights, self.box, *sun)
        self.lights = lights
        self.graph.start(lights, sun, self.bounces)
        return []
