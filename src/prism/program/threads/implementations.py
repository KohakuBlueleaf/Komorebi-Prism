"""The threads' form's implementations, registered as `<stage name>.threads`, each under
its stage's own name (the macros the steps' frame words read): the frame (geometry and
the tile thread's records), the texture, the light, the display, the transport without
its unit, the field's update as the job thread's job."""

from dataclasses import replace

from prism.check.threads.whole import check
from prism.core.implementation import IMPLEMENTATIONS, Implementation
from prism.program.threads import units
from prism.program.threads.host import ThreadsHost
from prism.program.threads.hosts import (
    FieldJobHost,
    LightThreadsHost,
    ShowThreadsHost,
    TransportThreadsHost,
)
from prism.stages.direct.light import LIGHT as STAGE_LIGHT
from prism.stages.indirect.field_update import FIELD_UPDATE
from prism.stages.indirect.field_update.graph import JOB
from prism.stages.indirect.transport import TRANSPORT
from prism.stages.material.texture import TEXTURE as STAGE_TEXTURE
from prism.stages.material.texture.host import TextureHost
from prism.stages.post.show import SHOW as STAGE_SHOW

SUFFIX = ".threads"  # a threads' form implementation's registered name: stage + it


def registered(implementation):
    """`implementation` registered under its name and SUFFIX."""
    return IMPLEMENTATIONS.register(implementation.name + SUFFIX, implementation)


FRAME = registered(
    Implementation(
        name="raster",
        fills=("raster",),
        reads=("scene.mesh", "view.camera"),
        writes=("frame.visibility", "frame.lists"),
        device=None,
        host=ThreadsHost,
        check=check,
        thread=None,
    )
)

TEXTURE = registered(
    replace(
        STAGE_TEXTURE, device=None, host=TextureHost, check=check, thread=units.MATERIAL
    )
)

LIGHT = registered(
    replace(
        STAGE_LIGHT,
        device=None,
        host=LightThreadsHost,
        check=check,
        thread=units.LIGHT,
    )
)

# with the job thread: the field's version by the slots its frame unit gives
LIGHT_FIELD = IMPLEMENTATIONS.register(
    "direct.light.threads_field",
    replace(
        LIGHT,
        reads=(*STAGE_LIGHT.reads, "light.field", "light.field_scale"),
        thread=units.LIGHT_FIELD,
    ),
)

SHOW = registered(
    replace(
        STAGE_SHOW, device=None, host=ShowThreadsHost, check=check, thread=units.POST
    )
)

TRANSPORT_THREADS = registered(
    replace(TRANSPORT, host=TransportThreadsHost, thread=None)
)

FIELD_JOB = registered(
    replace(
        FIELD_UPDATE,
        writes=("light.field", "light.field_scale"),
        host=FieldJobHost,
        thread=None,
    )
)

# {implementation: its Job} of the implementations that run on the job thread
JOBS = {FIELD_JOB.name: JOB}
