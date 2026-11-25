"""The tables of entries the raster class reads: a directory page's head, items and frame
words, and the heavy tiles' page."""

import komorebi as km


class DirHead(km.Entry):
    """A core's directory page, words 0 to 2: its first list page, their count and its
    items' count."""

    first: int
    pages: int
    items: int


class DirItem(km.Entry):
    """An item of the directory page (from word kDirIds): its tile, empty bit and rows."""

    id: int


class DirFrames(km.Entry):
    """The frame's tensors (from word kDirFrame): pages each, then each one's address."""

    pages: int
    base0: int
    base1: int
    base2: int
    base3: int
    base4: int
    base5: int
    base6: int
    base7: int
    base8: int
    base9: int
    base10: int
    base11: int
    base12: int
    base13: int
    base14: int


class HeavyCount(km.Entry):
    """The heavy tiles' page, word 0: their count."""

    count: int


class Heavy(km.Entry):
    """A tile HIST writes (the heavy page's words from word 1)."""

    tile: int


class View(km.Entry):
    """The view's words in the camera area (kViewAt): the frame's grid (a8 bits)."""

    grid: int


class Range(km.Entry):
    """A core's page of the camera area, words 0 and 1: its blocks [first, end)."""

    first: int
    end: int
