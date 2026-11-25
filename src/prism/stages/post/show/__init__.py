"""The frame converted for display: SHOW's 8-bit picture on the card, pushed to the
host."""

from prism.core.implementation import IMPLEMENTATIONS, Implementation
from prism.stages.post.show.check import check
from prism.stages.post.show.device import made
from prism.stages.post.show.host import ShowHost
from prism.stages.post.show.unit import UNIT

SHOW = IMPLEMENTATIONS.register(
    "post.show",
    Implementation(
        name="post.show",
        fills=("post",),
        reads=("frame.visibility",),
        writes=("display.picture",),
        device=made,
        host=ShowHost,
        check=check,
        thread=UNIT,
    ),
)
