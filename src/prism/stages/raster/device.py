"""The raster stage on the card: one class, its handlers the passes the X280 thread
sends (COUNT, SUM, HIST, HSUM, PLACE, SETUP, FILL) and the empty tile's load."""

import komorebi as km

from prism.core import fields
from prism.core.compute import FRAME_COMPUTE
from prism.stages.raster import capacity
from prism.stages.raster.entries import (
    DirFrames,
    DirHead,
    DirItem,
    Heavy,
    HeavyCount,
    Range,
    View,
)
from prism.stages.raster.sizes import (
    AREA_ITEMS,
    COSTS_ITEM,
    DEFAULT,
    DIR_FRAME,
    DIR_IDS,
    HSUM_BLOCK,
    PAGE,
    PASS_OUT_PAGES,
    PLANES,
    SLOT_BYTES,
    SPROF_WORDS,
    SUM_BLOCK,
    TOTALS_BLOCK,
    VIEW_WORD,
    WORK_WORDS,
    capacity_constants,
)


class Raster(km.Program, compute=FRAME_COMPUTE):
    """The raster passes on every core of a group, each as the X280 thread sends it;
    its sizes those of the capacity it is made for (made)."""

    # the common fields' sizes (prism.core.fields), given at the make
    COMMAND_SPACE_WORDS = fields.CONSTANTS["COMMAND_SPACE_WORDS"]
    OUT_RING_PAGES = fields.CONSTANTS["OUT_RING_PAGES"]

    COUNTER_WORDS = km.constant(DEFAULT["COUNTER_WORDS"])  # COUNT's counters
    # COUNT's histograms, scratch
    KEPT_HIST_WORDS = km.constant(DEFAULT["KEPT_HIST_WORDS"])
    SLOT_WORDS = km.constant(DEFAULT["SLOT_WORDS"])  # SETUP's next slots page
    TILE_OF_WORDS = km.constant(DEFAULT["TILE_OF_WORDS"])  # PLACE: each item's tile
    COUNTER_ITEMS = km.constant(DEFAULT["COUNTER_ITEMS"])  # 64 B items a counters page
    SLOT_ITEMS = km.constant(DEFAULT["SLOT_ITEMS"])  # 64 B items a prefixes page
    ROW_ITEMS = km.constant(DEFAULT["ROW_ITEMS"])  # a counters page's rows, from item
    HEAVY_ITEMS = km.constant(DEFAULT["HEAVY_ITEMS"])  # heavy tiles a histograms page
    ITEM_WORDS = km.constant(DEFAULT["ITEM_WORDS"])  # SETUP's items table
    LOW_PAGES = km.constant(DEFAULT["LOW_PAGES"])  # PLACE: the items table's pages
    HIGH_FIRST = km.constant(DEFAULT["HIGH_FIRST"])  # PLACE: the frame words' page
    HIGH_PAGES = km.constant(DEFAULT["HIGH_PAGES"])  # PLACE: from there to the end

    # COUNT and SETUP
    work: km.L1[km.u32, 1, WORK_WORDS] = km.own(push=None, raw=True)
    # the pages a handler keeps to itself (common to the classes merged with it):
    # 1 COUNT's costs, put to its page; 2 PLACE's directory page
    own_page_1: fields.field("own_page_1") = fields.own("own_page_1")
    out: km.L1[km.u32, PASS_OUT_PAGES, 32, 32] = km.own(push="pack")
    command_space: fields.field("command_space") = fields.own("command_space")
    profile_page: km.L1[km.u32, 1, SPROF_WORDS] = km.own(push=None, raw=True)
    next_slots: km.L1[km.u32, 1, SLOT_WORDS] = km.own(push="mover_a", raw=True)
    item_words: km.L1[km.u32, 1, ITEM_WORDS] = km.own(push="mover_a", raw=True)
    # PLACE
    low: km.L1[km.u32, LOW_PAGES, 32, 32]
    high: km.L1[km.u32, HIGH_PAGES, 32, 32]
    tile_of: km.L1[km.u32, 1, TILE_OF_WORDS] = km.own(push=None, raw=True)
    own_page_2: fields.field("own_page_2") = fields.own("own_page_2")
    slots: km.L1[km.u32, 2, 32, 32] = km.own(push=None)
    # FILL
    empty: km.L1[km.u32, PLANES, 32, 32]
    out_ring: fields.field("out_ring") = fields.own("out_ring")
    handoff: km.L1[km.u32, 1, 32, 32] = km.own(push="mover_a")

    @km.handler
    def load_empty(self, empty_planes: km.Tensor):
        """The empty tile's planes (depth 0, the background, triangle -1) into their
        field, kept for FILL."""
        self.empty.fill(km.Stream(empty_planes.pages(0, PLANES)))

    @km.handler
    def count(
        self,
        mesh: km.Tensor,
        counters: km.Tensor,
        camera: km.Region,
        heavy: km.Region,
        grid: int,
        profile: km.Tensor,
    ):
        """COUNT: the blocks of the core's range (its page of the camera area, `camera`
        the area's address) through the vector unit; per tile entries, rows and histograms;
        `heavy` (bank, 0) but in the recount; the costs to the core's page, the
        profile's 128 bytes."""
        km.cxx(
            "setup_k::Started read_started;",
            on="mover_a",
            include=["../../kernels/passes/blocks.hpp"],
        )
        km.cxx(
            "setup_k::PackPass pack_pass{compute};",
            on="pack",
            include=["../../kernels/passes/pack.hpp"],
        )
        for span in camera.pages(1 + self.rank, 1).entries(Range, size=2, fixed=1):
            km.cxx(
                "pack_pass.start(setup_k::kHandlerCount, out, work, own_page_1, span_first, "
                "span_end, grid);",
                takes=[self.out, self.work, self.own_page_1, span, grid],
                on="pack",
            )
            for view in km.Stream(camera.items(first=0, count=1, size=64), pattern="A"):
                km.cxx("pack_pass.camera(view);", takes=[view], on="pack")
            for block in km.Stream(
                mesh.pages(span.first, span.end - span.first), pattern="A"
            ):
                km.cxx("pack_pass.block(block);", takes=[block], on="pack")
            km.cxx(
                "setup_k::reader_profile(profile_page, block_cycles, block_tiles, "
                "read_started.at);",
                takes=[block, self.profile_page],
                on="mover_a",
            )
        km.cxx("pack_pass.end(profile_page);", takes=[self.profile_page], on="pack")
        km.cxx(
            "if (const int done = setup_k::count_write(movement, {counters.word, 0, 0, "
            "grid, out, command_space, command_space, work}, heavy, profile_page, "
            "profile.word); done >= 0) {\n    return done != 0;\n}",
            takes=[
                counters,
                grid,
                self.out,
                self.command_space,
                self.work,
                heavy,
                self.profile_page,
                profile,
            ],
            on="mover_b",
            include=["../../kernels/passes/commands.hpp"],
        )
        costs_at = (1 + self.rank) * AREA_ITEMS + COSTS_ITEM
        camera.items(size=64).put(self.own_page_1[0], at=costs_at)
        camera.items(size=64).put(self.own_page_1[1], at=costs_at + 1)

    @km.handler
    def sum(
        self,
        counters: km.Tensor,
        prefixes: km.Tensor,
        sums: km.Region,
        counting: int,
        slices: int,
    ):
        """SUM: per slice of 16 tiles (the frame's `slices` over the cores), each
        counting core's prefix of its entries, then the slice's totals in `sums`."""
        km.cxx(
            "setup_k::SumState sum_state;",
            on="pack",
            include=["../../kernels/sums/sums.hpp"],
        )
        for turn in range((slices + self.size - 1 - self.rank) // self.size):
            part = self.rank + turn * self.size
            km.cxx("sum_state.zero();", on="pack")
            prefix = km.Stream(
                prefixes.items(
                    first=part, count=counting, size=64, step=self.SLOT_ITEMS
                ),
                write=True,
                block=SUM_BLOCK,
            )
            for entry, row in zip(
                km.Stream(
                    counters.items(
                        first=part, count=counting, size=64, step=self.COUNTER_ITEMS
                    ),
                    block=SUM_BLOCK,
                ),
                km.Stream(
                    counters.items(
                        first=self.ROW_ITEMS + part,
                        count=counting,
                        size=64,
                        step=self.COUNTER_ITEMS,
                    ),
                    block=SUM_BLOCK,
                ),
            ):
                km.cxx(
                    "sum_state.add(entry, row, prefix);",
                    takes=[entry, row, prefix],
                    on="pack",
                )
            totals = km.Stream(
                sums.items(first=part, count=2, size=64, step=slices),
                write=True,
                block=TOTALS_BLOCK,
            )
            km.cxx("sum_state.totals(totals);", takes=[totals], on="pack")

    @km.handler
    def hist(
        self,
        heavy: km.Region,
        histograms: km.Tensor,
        page_bytes: int,
        profile: km.Tensor,
    ):
        """HIST: each heavy tile's 64 bytes of the histograms COUNT kept, to this
        core's page of `histograms` (`page_bytes` each); the profile's 128 bytes."""
        km.cxx(
            "setup_k::HistState hist_state;",
            on="mover_b",
            include=["../../kernels/sums/hist.hpp"],
        )
        km.cxx(
            "hist_state.start(histograms.word, page_bytes, "
            "raster_space::kept_hist(get_write_ptr(command_space)));",
            takes=[histograms, page_bytes, self.command_space],
            on="mover_b",
        )
        for head in heavy.pages(0, 1).entries(HeavyCount, size=1, fixed=1):
            km.cxx(
                "if (!hist_state.fits(movement.args().control, head_count)) {\n"
                "    return true;\n}",
                takes=[head],
                on="mover_b",
            )
            for cut in heavy.pages(0, 1).entries(Heavy, first=1, size=1, count=0):
                km.cxx(
                    "hist_state.send(movement, cut_tile);", takes=[cut], on="mover_b"
                )
        km.cxx(
            "if (!hist_state.end(movement, get_write_ptr(profile_page), profile.word)) "
            "{\n    return false;\n}",
            takes=[self.profile_page, profile],
            on="mover_b",
        )

    @km.handler
    def hsum(
        self,
        heavy_tiles: int,
        histograms: km.Tensor,
        hprefix: km.Tensor,
        sums: km.Region,
        counting: int,
        slices: int,
    ):
        """HSUM: per heavy tile over the cores, each counting core's 16 starts and 16
        ends summed before it to `hprefix`, the tile's counts to `sums` after SUM's."""
        km.cxx(
            "setup_k::HsumState hsum_state;",
            on="pack",
            include=["../../kernels/sums/sums.hpp"],
        )
        for turn in range((heavy_tiles + self.size - 1 - self.rank) // self.size):
            tile = self.rank + turn * self.size
            km.cxx("hsum_state.zero();", on="pack")
            prefix = km.Stream(
                hprefix.items(
                    first=tile, count=counting, size=128, step=self.HEAVY_ITEMS
                ),
                write=True,
                block=HSUM_BLOCK,
            )
            for counts in km.Stream(
                histograms.items(
                    first=tile, count=counting, size=64, step=self.HEAVY_ITEMS
                ),
                block=HSUM_BLOCK,
            ):
                km.cxx(
                    "hsum_state.add(counts, prefix);", takes=[counts, prefix], on="pack"
                )
            total = km.Stream(
                sums.items(first=slices + tile, count=1, size=128), write=True
            )
            km.cxx("hsum_state.total(total);", takes=[total], on="pack")

    @km.handler
    def place(
        self,
        items: km.Region,
        directory: km.Tensor,
        fill_cores: int,
        lists: km.Tensor,
        grid: int,
        profile: km.Tensor,
    ):
        """PLACE: from the items region the middle pass left, each fill core's
        directory page and end slot, every core the headers of its items."""
        self.low.fill(km.Stream(items.pages(0, self.LOW_PAGES)))
        self.high.fill(km.Stream(items.pages(self.HIGH_FIRST, self.HIGH_PAGES)))
        cores = self.size
        high_first = self.HIGH_FIRST
        km.cxx(
            "setup_k::Started place_started;",
            on="mover_b",
            include=["../../kernels/sums/place.hpp"],
        )
        end_slot = km.cxx(
            "if (const int placed = setup_k::place(movement, {low, high, high_first, "
            "get_write_ptr(tile_of), get_write_ptr(own_page_2), get_write_ptr(slots), "
            "fill_cores, lists.word, grid}, cores, end_slot); placed >= 0) {\n"
            "    return placed != 0;\n}",
            takes=[
                self.low,
                self.high,
                high_first,
                self.tile_of,
                self.own_page_2,
                self.slots,
                fill_cores,
                lists,
                grid,
                cores,
            ],
            on="mover_b",
            gives=int,
        )
        if self.rank < fill_cores:
            directory.items(size=PAGE).put(self.own_page_2, at=self.rank)
            lists.items(size=SLOT_BYTES).put(self.slots, at=end_slot)
        km.cxx(
            "if (!setup_k::send_profile(movement, get_write_ptr(profile_page), "
            "profile.word, setup_k::kHandlerPlace, {}, place_started.at)) {\n"
            "    return false;\n}",
            takes=[self.profile_page, profile],
            on="mover_b",
        )

    @km.handler
    def setup(
        self,
        mesh: km.Tensor,
        lists: km.Tensor,
        camera: km.Region,
        slots: km.Tensor,
        list_slots: int,
        items: km.Region,
        profile: km.Tensor,
    ):
        """SETUP: the blocks of the core's range (its page of the camera area, `camera`
        the area's address) through the vector unit, each kept record to the next slot of every
        item its box reaches; the next slots from SUM's and HSUM's prefixes
        (kSetupPrefix in `list_slots`); the grid from the view's words."""
        km.cxx(
            "setup_k::Started read_started;",
            on="mover_a",
            include=["../../kernels/passes/blocks.hpp"],
        )
        km.cxx(
            "setup_k::PackPass pack_pass{compute};",
            on="pack",
            include=["../../kernels/passes/pack.hpp"],
        )
        for view in camera.pages(0, 1).entries(View, first=VIEW_WORD, size=2, fixed=1):
            km.cxx(
                "setup_k::setup_slots(movement, {slots.word, list_slots, items.word, "
                "next_slots, item_words, command_space}, items, view_grid);",
                takes=[
                    slots,
                    list_slots,
                    items,
                    self.next_slots,
                    self.item_words,
                    self.command_space,
                    view,
                ],
                on="mover_a",
                include=["../../kernels/passes/commands.hpp"],
            )
            for span in camera.pages(1 + self.rank, 1).entries(Range, size=2, fixed=1):
                km.cxx(
                    "pack_pass.start(setup_k::kHandlerSetup, out, work, work, "
                    "span_first, span_end, view_grid, false, "
                    "view_depth != 0);",
                    takes=[self.out, self.work, span, view],
                    on="pack",
                )
                for camera_page in km.Stream(
                    camera.items(first=0, count=1, size=64),
                    pattern="A",
                ):
                    km.cxx(
                        "pack_pass.camera(camera_page);", takes=[camera_page], on="pack"
                    )
                for block in km.Stream(
                    mesh.pages(span.first, span.end - span.first), pattern="A"
                ):
                    km.cxx("pack_pass.block(block);", takes=[block], on="pack")
                km.cxx(
                    "setup_k::reader_profile(profile_page, block_cycles, block_tiles, "
                    "read_started.at);",
                    takes=[block, self.profile_page],
                    on="mover_a",
                )
            km.cxx(
                "if (!setup_k::setup_write(movement, {lists.word, list_slots, view_grid, "
                "out, next_slots, item_words}, profile_page, profile.word)) {\n"
                "    return false;\n}",
                takes=[
                    lists,
                    list_slots,
                    view,
                    self.out,
                    self.next_slots,
                    self.item_words,
                    self.profile_page,
                    profile,
                ],
                on="mover_b",
                include=["../../kernels/passes/commands.hpp"],
            )
        km.cxx("pack_pass.end(profile_page);", takes=[self.profile_page], on="pack")

    @km.handler
    def setup_shaded(
        self,
        mesh: km.Tensor,
        shade: km.Tensor,
        lists: km.Tensor,
        camera: km.Region,
        slots: km.Tensor,
        list_slots: int,
        items: km.Region,
        profile: km.Tensor,
    ):
        """SETUP on a shaded frame: as setup, each block's shade block of `shade` read
        beside it, the corner values weighted by 1/z and each record's shade word."""
        km.cxx(
            "setup_k::Started read_started;",
            on="mover_a",
            include=["../../kernels/passes/blocks.hpp"],
        )
        km.cxx(
            "setup_k::PackPass pack_pass{compute};",
            on="pack",
            include=["../../kernels/passes/pack.hpp"],
        )
        for view in camera.pages(0, 1).entries(View, first=VIEW_WORD, size=2, fixed=1):
            km.cxx(
                "setup_k::setup_slots(movement, {slots.word, list_slots, items.word, "
                "next_slots, item_words, command_space}, items, view_grid);",
                takes=[
                    slots,
                    list_slots,
                    items,
                    self.next_slots,
                    self.item_words,
                    self.command_space,
                    view,
                ],
                on="mover_a",
                include=["../../kernels/passes/commands.hpp"],
            )
            for span in camera.pages(1 + self.rank, 1).entries(Range, size=2, fixed=1):
                km.cxx(
                    "pack_pass.start(setup_k::kHandlerSetup, out, work, work, "
                    "span_first, span_end, view_grid, true, "
                    "view_depth != 0);",
                    takes=[self.out, self.work, span, view],
                    on="pack",
                )
                for camera_page in km.Stream(
                    camera.items(first=0, count=1, size=64),
                    pattern="A",
                ):
                    km.cxx(
                        "pack_pass.camera(camera_page);", takes=[camera_page], on="pack"
                    )
                for block, shade_block in zip(
                    km.Stream(
                        mesh.pages(span.first, span.end - span.first), pattern="A"
                    ),
                    km.Stream(
                        shade.pages(span.first, span.end - span.first), pattern="A"
                    ),
                ):
                    km.cxx(
                        "pack_pass.block(block, shade_block);",
                        takes=[block, shade_block],
                        on="pack",
                    )
                km.cxx(  # the moves' tiles: a mesh and a shade block each; the mesh's
                    "setup_k::reader_profile(profile_page, block_cycles, "
                    "block_tiles / 2, read_started.at);",
                    takes=[block, self.profile_page],
                    on="mover_a",
                )
            km.cxx(
                "if (!setup_k::setup_write(movement, {lists.word, list_slots, view_grid, "
                "out, next_slots, item_words}, profile_page, profile.word)) {\n"
                "    return false;\n}",
                takes=[
                    lists,
                    list_slots,
                    view,
                    self.out,
                    self.next_slots,
                    self.item_words,
                    self.profile_page,
                    profile,
                ],
                on="mover_b",
                include=["../../kernels/passes/commands.hpp"],
            )
        km.cxx("pack_pass.end(profile_page);", takes=[self.profile_page], on="pack")

    @km.handler
    def fill(
        self,
        directory: km.Tensor,
        lists: km.Tensor,
        frame: km.Tensor,
        profile: km.Tensor,
        grid: int,
    ):
        """FILL: each core's list pages walked on the pack thread into its items'
        planes, written into the frame's pages (the empty tile's for an empty item);
        then its profile page."""
        km.cxx(
            "fill_k::ReaderClock reader_clock;",
            on="mover_a",
            include=["../../kernels/fill/write.hpp"],
        )
        km.cxx(
            "fill_k::Items written;",
            on="mover_b",
            include=["../../kernels/fill/write.hpp"],
        )
        km.cxx(
            "written.start(out_ring, empty);",
            takes=[self.out_ring, self.empty],
            on="mover_b",
        )
        for head in directory.pages(self.rank, 1).entries(DirHead, size=3, fixed=1):
            km.cxx(
                "fill_k::Walk walk{compute};",
                on="pack",
                include=["../../kernels/fill/walk.hpp"],
            )
            km.cxx(
                "walk.start(out_ring, grid);", takes=[self.out_ring, grid], on="pack"
            )
            km.cxx("reader_clock.move();", on="mover_a")
            for page in km.Stream(lists.pages(head.first, head.pages), pattern="A"):
                km.cxx("walk.page(page);", takes=[page], on="pack")
            km.cxx(
                "reader_clock.hand(handoff, page_cycles, page_tiles);",
                takes=[page, self.handoff],
                on="mover_a",
            )
            for frames in directory.pages(self.rank, 1).entries(
                DirFrames, first=DIR_FRAME, size=16, fixed=1
            ):
                km.cxx(
                    "if (!written.frame(movement, command, head_items, frames_pages, "
                    "frames_base0, frames_base1, frames_base2, frames_base3, "
                    "frames_base4, frames_base5, frames_base6, frames_base7, "
                    "frames_base8, frames_base9, frames_base10, frames_base11, "
                    "frames_base12, frames_base13, frames_base14)) {\n    return false;\n}",
                    takes=[head, frames],
                    on="mover_b",
                )
                for item in directory.pages(self.rank, 1).entries(
                    DirItem, first=DIR_IDS, size=1, count=2
                ):
                    km.cxx(
                        "if (const int wrote = written.item<Frame>(movement, command, "
                        "item_id); wrote >= 0) {\n    return wrote != 0;\n}",
                        takes=[item, frame],
                        on="mover_b",
                    )
            km.cxx("walk.end();", on="pack")
            km.cxx(
                "if (!written.profile<Profile>(movement, command, profile.word, "
                "handoff)) {\n    return false;\n}",
                takes=[profile, self.handoff],
                on="mover_b",
            )


def made(host):
    """The class made for a host's tensors and capacity, one command at a time."""
    return Raster(
        **host.examples,
        **capacity_constants(host.held),
        **fields.given(Raster, host.held),
        defines=capacity.capacity_defines(host.held) | fields.defines(host.held),
        session=host.session,
        depth=1,
    )
