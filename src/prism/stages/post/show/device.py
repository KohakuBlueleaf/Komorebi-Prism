"""SHOW on the card: one class, its handlers `show` (the frame's colour as 8-bit pixels
into the display) and `copy` (plane 0 word for word into pages of another tensor), on
the movers, each item's planes read by mover A and written by mover B."""

import komorebi as km

from prism.core import fields
from prism.core.compute import FRAME_COMPUTE
from prism.stages.post.show.entries import DirFrames, DirHead, DirItem
from prism.stages.post.show.model.table import SHOW
from prism.stages.raster import capacity
from prism.stages.raster.model import numbers

K = numbers.K
PAGE_WORDS = SHOW["kShowPageBytes"] // 4  # a planes or scratch page
PLANE_PAGES = SHOW["kShowPages"]  # two items of three planes
SCRATCH_PAGES = SHOW["kShowScratchPages"]  # two converted pages, profile, buckets
DIR_FRAME = K["kDirFrame"]  # a directory page's frame words
DIR_IDS = K["kDirIds"]  # a directory page's items
# mover A's frame words of a directory page (kDirFrameMax tensors)
READER_FRAME = (
    "if (!reader.frame(item_planes, frames_pages, frames_base0, frames_base1, frames_base2, "
    "frames_base3, frames_base4, frames_base5, frames_base6, frames_base7, "
    "frames_base8, frames_base9, frames_base10, frames_base11, frames_base12, "
    "frames_base13, frames_base14)) {\n    return true;\n}"
)
fields.need("show_scratch", "post.show", lambda held: 4 * SCRATCH_PAGES * PAGE_WORDS)


class Show(km.Program, compute=FRAME_COMPUTE):
    """SHOW and COPY on every core of a group, each core its directory's items."""

    # the common field's size (prism.core.fields), given at the make
    COMMAND_SPACE_WORDS = fields.CONSTANTS["COMMAND_SPACE_WORDS"]

    thresholds: km.L1[km.u32, 1, 32, 32]  # the thresholds, from the table's region
    item_planes: km.L1[km.u32, PLANE_PAGES, PAGE_WORDS] = km.own(
        push="mover_a", raw=True
    )
    command_space: fields.field("command_space") = fields.own("command_space")

    @km.handler
    def show(
        self,
        directory: km.Tensor,
        display: km.Tensor,
        profile: km.Tensor,
        show_table: km.Region,
        display_pages: int,
    ):
        """SHOW: each item of the core's directory page, its colour planes converted
        by the thresholds to R, G, B, 255 in its tile's page of `display` (of
        `display_pages`); the writer's profile page."""
        self.thresholds.fill(km.Stream(show_table.pages(0, 1)))
        km.cxx(
            "show_k::Reader reader;",
            on="mover_a",
            include=["../../kernels/read.hpp"],
        )
        km.cxx(
            "show_k::Writer writer;",
            on="mover_b",
            include=["../../kernels/profile.hpp"],
        )
        km.cxx(
            "writer.start(item_planes, show_space::scratch(get_write_ptr(command_space)));\nwriter.table(thresholds);",
            takes=[self.item_planes, self.command_space, self.thresholds],
            on="mover_b",
        )
        for head in directory.pages(self.rank, 1).entries(DirHead, size=3, fixed=1):
            for frames in directory.pages(self.rank, 1).entries(
                DirFrames, first=DIR_FRAME, size=16, fixed=1
            ):
                km.cxx(
                    READER_FRAME,
                    takes=[frames, self.item_planes],
                    on="mover_a",
                )
                km.cxx(
                    "if (!writer.frame(movement, command, head_items, frames_pages)) "
                    "{\n    return false;\n}",
                    takes=[head, frames],
                    on="mover_b",
                )
                for item in directory.pages(self.rank, 1).entries(
                    DirItem, first=DIR_IDS, size=1, count=2
                ):
                    km.cxx(
                        "if (!reader.item(movement, command, item_id, "
                        "show_k::kShowFirstPlane, show_k::kShowPlanes)) {\n"
                        "    return true;\n}",
                        takes=[item],
                        on="mover_a",
                    )
                    km.cxx(
                        "if (const int wrote = writer.item(movement, command, item_id, "
                        "display.word, 0, kGridDefault, display_pages, false); "
                        "wrote >= 0) {\n    return wrote != 0;\n}",
                        takes=[item, display, display_pages],
                        on="mover_b",
                    )
        km.cxx(
            "if (!show_k::send_profile(movement, command, writer, profile.word)) {\n"
            "    return false;\n}",
            takes=[profile],
            on="mover_b",
        )

    @km.handler
    def copy(
        self,
        directory: km.Tensor,
        target: km.Tensor,
        first: int,
        across: int,
        target_pages: int,
    ):
        """COPY: each item of the core's directory page, its plane 0 word for word,
        row-major, to page first + (tile / 32) across + tile mod 32 of `target` (of
        `target_pages`)."""
        km.cxx(
            "show_k::Reader reader;",
            on="mover_a",
            include=["../../kernels/read.hpp"],
        )
        km.cxx(
            "show_k::Writer writer;",
            on="mover_b",
            include=["../../kernels/profile.hpp"],
        )
        km.cxx(
            "writer.start(item_planes, show_space::scratch(get_write_ptr(command_space)));",
            takes=[self.item_planes, self.command_space],
            on="mover_b",
        )
        for head in directory.pages(self.rank, 1).entries(DirHead, size=3, fixed=1):
            for frames in directory.pages(self.rank, 1).entries(
                DirFrames, first=DIR_FRAME, size=16, fixed=1
            ):
                km.cxx(
                    READER_FRAME,
                    takes=[frames, self.item_planes],
                    on="mover_a",
                )
                km.cxx(
                    "if (!writer.frame(movement, command, head_items, frames_pages)) "
                    "{\n    return false;\n}",
                    takes=[head, frames],
                    on="mover_b",
                )
                for item in directory.pages(self.rank, 1).entries(
                    DirItem, first=DIR_IDS, size=1, count=2
                ):
                    km.cxx(
                        "if (!reader.item(movement, command, item_id, 0, 1)) {\n"
                        "    return true;\n}",
                        takes=[item],
                        on="mover_a",
                    )
                    km.cxx(
                        "if (const int wrote = writer.item(movement, command, item_id, "
                        "target.word, first, across, target_pages, true); "
                        "wrote >= 0) {\n    return wrote != 0;\n}",
                        takes=[item, target, first, across, target_pages],
                        on="mover_b",
                    )
        km.cxx(
            "if (!writer.sent(movement, command)) {\n    return false;\n}",
            on="mover_b",
        )


def made(host):
    """The class made for a host's tensors and capacity, one command at a time."""
    return Show(
        **host.examples,
        **fields.given(Show, host.held),
        defines=capacity.capacity_defines(host.held) | fields.defines(host.held),
        session=host.session,
        depth=1,
    )
