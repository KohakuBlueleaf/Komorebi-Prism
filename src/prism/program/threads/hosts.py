"""The stage-wise hosts as the threads' form holds them: the light's numbers of its
threads' unit, the display always given as a slot, the field's update as a job (its
numbers in the job thread's region, no thread command)."""

from prism.stages.direct.light.host import LightHost
from prism.stages.direct.light.model.terms import light_pages
from prism.stages.indirect.field_update.host import FieldUpdateHost
from prism.stages.post.show.host import ShowHost


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


class FieldJobHost(FieldUpdateHost):
    """The field update's host as the job thread's job: its numbers go to the job's
    region (FieldGraph), it sends no thread command."""

    def bind(self, loaded):
        """The run kept; no numbers of a frame thread's unit."""
        self.loaded = loaded

    def commands(self, loaded):
        """None: the kept graph runs the update."""
        return []
