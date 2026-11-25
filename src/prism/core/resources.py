"""Assignment of the thread's resources: from a pipeline's units, its regions in order, the
place of every number, column, time and result, the thread commands' numbers; the text of
the generated header that names them. The layers a view and the views a frame are the
hosts'."""

from dataclasses import dataclass

import numpy as np
from komorebi.program import thread as km_thread

PAGE = km_thread.PAGE  # a region is whole pages
LINE = 64  # a shared region's offset, and a row's words, on whole lines
LINE_WORDS = LINE // 4
REGIONS_MAX = km_thread.layout()["KMX_REGIONS_MAX"]
TIMES_ROWS = 256  # the times region: a row a frame, the last ones
FRAME_COMMAND = "frame"  # the director's thread command, number 1
# the director's own numbers (name, words; the camera first, its words on a line), its
# columns and its row words (times, then results)
DIRECTOR_NUMBERS = (
    ("camera", 16),
    ("cores", 1),
    ("workers", 1),
    ("bank", 1),
    ("layers", 1),
    ("grid", 1),
    ("tiles", 1),
)
DIRECTOR_COLUMNS = ("depth",)  # whether the layer takes part in a DEPTH view
DIRECTOR_TIMES = ("frame",)
DIRECTOR_RESULTS = ("code", "number", "view", "layer")
DIRECTOR_REGIONS = ("numbers", "layers", "times")
DIRECTOR = "dr"


def macro_prefix(name):
    """The prefix of the layout's macros for `name`: DR for the director's, DR_<NAME>
    (upper-cased, dots as '_') for a unit's."""
    if name == DIRECTOR:
        return "DR"
    return f"DR_{name.upper().replace('.', '_')}"


def function_prefix(name):
    """A unit's C function prefix: its implementation's name, dots as '_'."""
    return name.replace(".", "_")


def give_macro(slot):
    """DR_GIVE_<SLOT>: the slot's name upper-cased, dots as '_'."""
    return f"DR_GIVE_{slot.upper().replace('.', '_')}"


def layers_of(units):
    """The layers a view of `units` (name, Unit, host): the most a host holds (its
    `layers`); a host with none counts one."""
    return max(
        [len(getattr(host, "layers", None) or ()) or 1 for *_, host in units] + [1]
    )


def views_of(units):
    """The views a frame of `units` (name, Unit, host): the eye's, then the most views
    of its own a host holds (its `views`); a host with none counts the eye's alone."""
    return 1 + max(
        [len(getattr(host, "views", None) or ()) for *_, host in units] + [0]
    )


def lines(words):
    """`words` rounded up to whole lines."""
    return -(-words // LINE_WORDS) * LINE_WORDS


def pages(bytes_):
    """`bytes_` rounded up to whole pages."""
    return -(-bytes_ // PAGE) * PAGE


@dataclass(frozen=True)
class Place:
    """A named place: its owner (a unit's name, or the director's), its word and its
    words; `layered`: a layer unit's time or result, once a layer (`word` layer 0's)."""

    owner: str
    word: int
    words: int = 1
    layered: bool = False


class Layout:
    """The thread's resources for `units`, a list of (implementation name, Unit, host)
    in the pipeline's order, `writes` {implementation name: the slots it writes};
    ValueError with the names and numbers when they do not fit."""

    def __init__(self, units, writes=None):
        self.units = list(units)
        self.layers = layers_of(self.units)
        self.views = views_of(self.units)
        self.areas = self.layers * self.views  # a (view, layer) each: a layers row
        self.writes = dict(writes or {})
        self.read = {}  # (taker, slot): (the unit, its Unit) whose columns it reads
        self.numbers, self.columns, self.times, self.results = {}, {}, {}, {}
        self.regions = {}  # name: (owner, id, at, bytes, Region or None)
        self.commands = {FRAME_COMMAND: (DIRECTOR, None, 1)}
        self.place_numbers()
        self.place_rows()
        self.place_regions()
        self.place_commands()
        self.gives = self.place_gives()
        self.defines = self.place_defines()

    def named(self, table, name, place, kind):
        """`place` under `name` in `table`, refused when another asked for it."""
        if name in table:
            raise ValueError(
                f"thread layout: {kind} {name!r} asked by {table[name].owner} and by "
                f"{place.owner}"
            )
        table[name] = place

    def place_numbers(self):
        """The director's numbers, then each unit's, a word each."""
        word = 0
        for name, words in DIRECTOR_NUMBERS:
            self.named(self.numbers, name, Place(DIRECTOR, word, words), "number")
            word += words
        for owner, unit, _ in self.units:
            for name in unit.numbers:
                self.named(self.numbers, name, Place(owner, word), "number")
                word += 1
        self.number_words = word

    def place_rows(self):
        """A layer's row: the director's columns, then each unit's; a times row: the director's time, the
        frame units' times, the director's results, the frame units' results, then a
        block a layer: the layer units' times, then their results."""
        word = 0
        for name in DIRECTOR_COLUMNS:
            self.named(self.columns, name, Place(DIRECTOR, word), "column")
            word += 1
        for owner, unit, _ in self.units:
            for name in unit.columns:
                self.named(self.columns, name, Place(owner, word), "column")
                word += 1
        self.layer_words = lines(word)
        rows = [(DIRECTOR, DIRECTOR_TIMES, DIRECTOR_RESULTS, False)]
        rows += [
            (owner, unit.times, unit.results, unit.layer)
            for owner, unit, _ in self.units
        ]
        word = 0
        for layered in (False, True):
            first = word
            for kind, table in (("time", self.times), ("result", self.results)):
                for owner, times, results, layer in rows:
                    if layer != layered:
                        continue
                    for name in times if kind == "time" else results:
                        place = Place(owner, word, layered=layered)
                        self.named(table, name, place, kind)
                        word += 1
        self.times_layer_words = word - first  # a layer's block, the last
        word += self.times_layer_words * (self.layers - 1)
        for name in self.times.keys() & self.results.keys():
            raise ValueError(f"thread layout: {name!r} is both a time and a result")
        self.times_words = lines(word)

    def row_words(self, place):
        """The words of a times row holding `place`: one a layer for a layer unit's."""
        if not place.layered:
            return [place.word]
        stride = self.times_layer_words
        return [place.word + layer * stride for layer in range(self.layers)]

    def place_regions(self):
        """Each unit's own regions, then the director's; a shared one in the numbers
        region after the numbers, on a line of its own."""
        shared_at = lines(self.number_words) * 4
        own, shared = [], []
        for owner, unit, host in self.units:
            for name, region in unit.regions.items():
                if name in DIRECTOR_REGIONS or name in self.regions:
                    first = self.regions.get(name, (DIRECTOR,))[0]
                    raise ValueError(
                        f"thread layout: region {name!r} asked by {first} and by {owner}"
                    )
                bytes_ = region.size(host, self.areas)
                if bytes_ <= 0:
                    raise ValueError(
                        f"thread layout: {owner}'s region {name!r} is empty"
                    )
                if region.own:
                    own.append((name, owner, bytes_, region))
                else:
                    shared.append((name, owner, shared_at, bytes_, region))
                    shared_at += -(-bytes_ // LINE) * LINE
                self.regions[name] = (owner,)
        self.regions = {}
        for index, (name, owner, bytes_, region) in enumerate(own):
            self.regions[name] = (owner, index, 0, bytes_, region)
        number_id = len(own)
        director = {
            "numbers": pages(shared_at),
            "layers": pages(4 * self.layer_words * self.areas),
            "times": pages(4 * self.times_words * TIMES_ROWS),
        }
        for index, name in enumerate(DIRECTOR_REGIONS):
            self.regions[name] = (DIRECTOR, number_id + index, 0, director[name], None)
        for name, owner, at, bytes_, region in shared:
            self.regions[name] = (owner, number_id, at, bytes_, region)
        count = len(own) + len(DIRECTOR_REGIONS)
        if count > REGIONS_MAX:
            names = ", ".join(name for name, *_ in own)
            raise ValueError(
                f"thread layout: {count} regions (the units' {names}; the director's "
                f"{len(DIRECTOR_REGIONS)}), Komorebi's threads hold {REGIONS_MAX}"
            )
        self.check_places()

    def check_places(self):
        """Every place inside its region's bytes."""
        tables = (
            (self.numbers, "numbers", 1),
            (self.columns, "layers", self.areas),
            (self.times, "times", TIMES_ROWS),
            (self.results, "times", TIMES_ROWS),
        )
        for table, region, rows in tables:
            bytes_ = self.regions[region][3] // rows
            if region != "numbers":
                bytes_ = 4 * (
                    self.layer_words if region == "layers" else self.times_words
                )
            for name, place in table.items():
                end = 4 * (self.row_words(place)[-1] + place.words)
                if end > bytes_:
                    raise ValueError(
                        f"thread layout: {place.owner}'s {name!r} ends at byte {end}, "
                        f"past the {bytes_} of its {region} row"
                    )
        numbers_bytes = self.regions["numbers"][3]
        for name, (owner, _, at, bytes_, _) in self.regions.items():
            if at and at + bytes_ > numbers_bytes:
                raise ValueError(
                    f"thread layout: {owner}'s region {name!r} ends at byte "
                    f"{at + bytes_}, past the numbers region's {numbers_bytes}"
                )

    def place_commands(self):
        """The thread commands: `frame` 1, then each unit's served ones in order."""
        number = 2
        for owner, unit, _ in self.units:
            for name in unit.serves:
                if name in self.commands:
                    raise ValueError(
                        f"thread layout: command {name!r} served by "
                        f"{self.commands[name][0]} and by {owner}"
                    )
                self.commands[name] = (owner, None, number)
                number += 1

    def sharer_of(self, slot):
        """(the unit, its Unit) that shares `slot`'s columns and whose implementation
        writes it, or None."""
        for owner, unit, _ in self.units:
            if slot in unit.shares and slot in self.writes.get(owner, ()):
                return owner, unit
        return None

    def place_gives(self):
        """{slot: (giver, C function)} of every slot a unit takes from a unit that
        gives it by a function; a taken slot whose writer shares columns is read from
        exactly those (`read`); refused for a slot given twice, or taken and given or
        shared by none, naming the units."""
        givers = {}
        for owner, unit, _ in self.units:
            for slot, function in unit.given(function_prefix(owner)).items():
                if slot in givers:
                    raise ValueError(
                        f"thread layout: slot {slot!r} given by {givers[slot][0]} and "
                        f"by {owner}"
                    )
                givers[slot] = (owner, function)
        out = {}
        for owner, unit, _ in self.units:
            for slot in unit.takes:
                sharer = self.sharer_of(slot)
                if sharer is not None and sharer[0] != owner:
                    self.read[owner, slot] = sharer
                    if slot not in givers:
                        continue
                if slot not in givers:
                    writers = [
                        o for o, _, _ in self.units if slot in self.writes.get(o, ())
                    ]
                    raise ValueError(
                        f"thread layout: {owner} takes slot {slot!r}, which no unit of "
                        f"the pipeline gives or shares columns of (written by "
                        f"{', '.join(writers) or 'none'})"
                    )
                out[slot] = givers[slot]
        return out

    def place_defines(self):
        """The units' build-time defines {name: value}; refused for a name two units
        give or one that is also a layout macro, naming both."""
        macros, out, given = set(self.macros()), {}, {}
        for owner, unit, host in self.units:
            for name, value in unit.build_defines(host).items():
                if name in given:
                    raise ValueError(
                        f"thread layout: define {name} given by {given[name]} and by "
                        f"{owner}"
                    )
                if name in macros:
                    raise ValueError(
                        f"thread layout: {owner}'s define {name} is also a layout macro"
                    )
                out[name], given[name] = value, owner
        return out

    def counts(self):
        """The layout's counts: regions, numbers, columns, times, results, words."""
        return {
            "regions": len({entry[1] for entry in self.regions.values()}),
            "numbers": len(self.numbers),
            "columns": len(self.columns),
            "times": len(self.times),
            "results": len(self.results),
            "number_words": self.number_words,
            "layer_words": self.layer_words,
            "times_words": self.times_words,
        }

    def region_values(self):
        """The thread's regions for program.thread, in id order: {name: bytes or first
        words}; the shared ones' contents in the numbers region."""
        out, numbers = {}, None
        for name, (owner, index, at, bytes_, region) in self.regions.items():
            host = self.host_of(owner)
            given = region is not None and region.contents is not None
            if at or (region is not None and not region.own):
                if given:
                    if numbers is None:
                        numbers = np.zeros(self.regions["numbers"][3] // 4, np.uint32)
                    words = np.asarray(region.contents(host), np.uint32).reshape(-1)
                    numbers[at // 4 : at // 4 + len(words)] = words
                continue
            if given:
                words = np.zeros(-(-bytes_ // 4), np.uint32)
                first = np.asarray(region.contents(host), np.uint32).reshape(-1)
                words[: len(first)] = first
                out[name] = words
            else:
                out[name] = bytes_
        if numbers is not None:
            out["numbers"] = numbers
        return out

    def host_of(self, owner):
        """The host of the unit `owner` (None for the director)."""
        for name, _, host in self.units:
            if name == owner:
                return host
        return None

    def handlers(self):
        """The thread commands {name: number} for program.thread."""
        return {name: number for name, (_, _, number) in self.commands.items()}

    def macros(self):
        """The layout's macros in order: {name: value}."""
        out = {
            "DR_LAYERS": self.layers,
            "DR_VIEWS": self.views,
            "DR_LAYER_WORDS": self.layer_words,
            "DR_TIMES_WORDS": self.times_words,
            "DR_TIMES_LAYER_WORDS": self.times_layer_words,
            "DR_TIMES_ROWS": TIMES_ROWS,
            "DR_NUMBER_WORDS": self.number_words,
            "DR_REGIONS": self.counts()["regions"],
        }
        kinds = (
            (self.numbers, "N"),
            (self.columns, "L"),
            (self.times, "T"),
            (self.results, "R"),
        )
        for table, letter in kinds:
            for name, place in table.items():
                macro = f"{macro_prefix(place.owner)}_{letter}_{name.upper()}"
                out[macro] = place.word
                if place.words > 1:
                    out[f"{macro}_WORDS"] = place.words
        for (taker, slot), (_, unit) in self.read.items():
            taken = f"{macro_prefix(taker)}_TAKES_{slot.upper().replace('.', '_')}"
            for name in unit.shares[slot]:
                out[f"{taken}_{name.upper()}"] = self.columns[name].word
        for name, (owner, index, at, bytes_, _) in self.regions.items():
            macro = f"{macro_prefix(owner)}_REGION_{name.upper()}"
            out[macro], out[f"{macro}_AT"], out[f"{macro}_BYTES"] = index, at, bytes_
        for name, (owner, _, number) in self.commands.items():
            out[f"{macro_prefix(owner)}_COMMAND_{name.upper()}"] = number
        return out

    def header(self):
        """The text of pipeline.h: every place, region and command as a macro; each
        slot taken as DR_GIVE_<SLOT>, its giver's function, and DR_GIVES_DECLARED, the
        givers' declarations (for director.h, after its types)."""
        out = [
            "/* Generated by prism.core.resources: the thread's layout. */",
            "#pragma once",
            "",
        ]
        out += [f"#define {name} {value}u" for name, value in self.macros().items()]
        functions = sorted({function for _, function in self.gives.values()})
        out += [
            f"#define {give_macro(slot)} {function}"
            for slot, (_, function) in self.gives.items()
        ]
        declared = " ".join(f"uint32_t {f}(dr_frame_t* frame);" for f in functions)
        out.append(f"#define DR_GIVES_DECLARED {declared}".rstrip())
        return "\n".join(out) + "\n"
