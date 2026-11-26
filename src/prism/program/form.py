"""The assembly a pipeline takes, chosen once from its implementations: the threads'
form's when one implementation's host is the threads' frame host, else the stage-wise
form's; each named by dotted paths, resolved when chosen."""

from collections.abc import Callable
from dataclasses import dataclass

from prism_common.build import located

# {form: (its assembly, its load)} as dotted paths
FORMS = {
    "stage-wise": ("prism.program.assemble:assemble", "prism.program.loaded:load"),
    "threads": (
        "prism.program.threads.assemble:assembled",
        "prism.program.threads.assemble:load",
    ),
}


@dataclass(frozen=True)
class Form:
    """A form's name, its assembly `assemble(pipeline, session, scene, options)` and its
    load `load(assembled, session)`."""

    name: str
    assemble: Callable
    load: Callable


def form_of(pipeline):
    """The threads' Form when an implementation's host is the threads' frame host (its
    `threads` true), else the stage-wise Form."""
    threads = any(getattr(i.host, "threads", False) for i in pipeline.implementations)
    name = "threads" if threads else "stage-wise"
    assemble, load = FORMS[name]
    return Form(name, located(assemble), located(load))
