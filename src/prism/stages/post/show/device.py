"""SHOW on the card: one class, its handlers `show` (the frame's colour as 8-bit pixels
into the display) and `copy` (plane 0 word for word into pages of another tensor), on
the movers, each item's planes read by mover A and written by mover B; with a file's
view transform on, `show`'s items through the pack CPU's fetch on their way."""

import komorebi as km

from prism.core import fields
from prism.core.compute import FRAME_COMPUTE
from prism.stages.post.show.entries import DirFrames, DirHead, DirItem
from prism.stages.post.show.model.table import SHOW
from prism.stages.post.show.model.view import VIEW
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
# SHOW's part of the command space: the scratch pages, the view's slots, work, words
SLOTS_AT = 4 * SCRATCH_PAGES * PAGE_WORDS
WORK_AT = SLOTS_AT + VIEW["kViewSlots"] * VIEW["kViewPageBytes"]
WORDS_AT = WORK_AT + VIEW["kViewWorkBytes"]
SPACE_DEFINES = {
    "PRISM_SHOW_VIEW_SLOTS_AT": str(SLOTS_AT),
    "PRISM_SHOW_VIEW_WORK_AT": str(WORK_AT),
    "PRISM_SHOW_VIEW_WORDS_AT": str(WORDS_AT),
}
fields.need(
    "show_scratch", "post.show", lambda held: WORDS_AT + VIEW["kViewRegionBytes"]
)
# the pack CPU's state, its items converted to their end, the unpack CPU's service
PACK = (
    "const uint32_t space = compute_mail::write_ptr(command_space);\n"
    "show_view::Packer packer{show_view::waits_of(compute.control()), "
    "reinterpret_cast<const uint32_t*>(show_space::view_words(space)), viewed, "
    "texel_asks, texel_dones, show_space::view_slots(space), "
    "show_space::view_work(space), show_space::scratch(space) + kViewCountsByte, {}};"
    "\npacker.count();\n"
    "if (packer.items_of(view_items)) {\n"
    "    compute_mail::end_mails();\n"
    "}"
)


class Show(km.Program, compute=FRAME_COMPUTE):
    """SHOW and COPY on every core of a group, each core its directory's items."""

    # the common field's size (prism.core.fields), given at the make
    COMMAND_SPACE_WORDS = fields.CONSTANTS["COMMAND_SPACE_WORDS"]

    thresholds: km.L1[km.u32, 1, 32, 32]  # the thresholds, from the table's region
    item_planes: km.L1[km.u32, PLANE_PAGES, PAGE_WORDS] = km.own(
        push="mover_a", raw=True
    )
    view_items: km.L1[km.u32, 2, 16] = km.own(push="mover_a", raw=True)
    viewed: km.L1[km.u32, 2, 16] = km.own(push="pack", raw=True)
    texel_asks: fields.field("texel_asks") = fields.own("texel_asks")
    texel_dones: fields.field("texel_dones") = fields.own("texel_dones")
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
        """SHOW: each item of the core's directory page, its colour planes (through
        the view after the thresholds when it is on) converted by the thresholds to R, G, B,
        255 in its tile's page of `display` (of `display_pages`); the writer's profile
        page."""
        self.thresholds.fill(km.Stream(show_table.pages(0, 1)))
        km.cxx(
            "show_k::Reader reader;\n"
            "texel_pages::AskBuffers asks = {};\n"
            "show_view::Served served = {};",
            on="mover_a",
            include=[
                "../../kernels/read.hpp",
                "../../kernels/view_show.hpp",
                "../../kernels/space.hpp",
            ],
        )
        km.cxx(
            "asks = {texel_asks, texel_dones, "
            "show_space::view_slots(get_write_ptr(command_space))};\n"
            "served = show_view::served_of(movement, show_table, "
            "show_space::view_words(get_write_ptr(command_space)), true);\n"
            "if (!show_view::hand(movement, view_items, served.on, 0)) {\n"
            "    return false;\n}",
            takes=[
                show_table,
                self.texel_asks,
                self.texel_dones,
                self.command_space,
                self.view_items,
            ],
            on="mover_a",
        )
        km.cxx(
            PACK,
            takes=[
                self.view_items,
                self.viewed,
                self.texel_asks,
                self.texel_dones,
                self.command_space,
            ],
            on="pack",
            include=["../../kernels/view_show.hpp", "../../kernels/space.hpp"],
        )
        km.cxx(
            "compute_mail::serve_mails(show_view::waits_of(compute.control()));",
            on="unpack",
            include=["../../kernels/view_show.hpp"],
        )
        km.cxx(
            "show_k::Writer writer;\nbool viewing = false;",
            on="mover_b",
            include=["../../kernels/profile.hpp", "../../kernels/view_show.hpp"],
        )
        km.cxx(
            "const uint32_t scratch = show_space::scratch(get_write_ptr(command_space));"
            "\nviewing = show_view::served_of(movement, show_table, scratch, false).on;\n"
            "writer.start(item_planes, scratch);\n"
            "writer.table(thresholds);",
            takes=[
                self.item_planes,
                show_table,
                self.command_space,
                self.thresholds,
            ],
            on="mover_b",
            include=["../../kernels/view_show.hpp"],
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
                        "const uint32_t planes_at = get_write_ptr(item_planes);\n"
                        "if (!reader.item(movement, command, item_id, "
                        "show_k::kShowFirstPlane, show_k::kShowPlanes)) {\n"
                        "    return true;\n}\n"
                        "if (served.on && !show_view::serve_item(movement, "
                        "command, view_items, item_id, planes_at, asks, served.base)) "
                        "{\n    return false;\n}",
                        takes=[item, self.view_items, self.item_planes],
                        on="mover_a",
                    )
                    km.cxx(
                        "if (viewing && !show_view::viewed_wait(movement, viewed)) {\n"
                        "    return false;\n}\n"
                        "if (const int wrote = writer.item(movement, command, item_id, "
                        "display.word, 0, kGridDefault, kGridDefault, display_pages, false); "
                        "wrote >= 0) {\n    return wrote != 0;\n}",
                        takes=[item, display, display_pages, self.viewed],
                        on="mover_b",
                    )
        km.cxx(
            "if (served.on && !show_view::hand(movement, view_items, "
            "show_view::kItemsEnd, 0)) {\n    return false;\n}",
            takes=[self.view_items],
            on="mover_a",
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
        grid: int,
    ):
        """COPY: each item of the core's directory page, its plane 0 word for word,
        row-major, to page first + (tile / TX) across + tile mod TX of `target` (of
        `target_pages`), TX the view's tiles a row (its grid word, grid.h)."""
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
                        "target.word, first, grid_of(grid).across, across, target_pages, true); "
                        "wrote >= 0) {\n    return wrote != 0;\n}",
                        takes=[item, target, first, across, target_pages, grid],
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
        defines=capacity.capacity_defines(host.held)
        | fields.defines(host.held)
        | SPACE_DEFINES,
        session=host.session,
        depth=1,
    )
