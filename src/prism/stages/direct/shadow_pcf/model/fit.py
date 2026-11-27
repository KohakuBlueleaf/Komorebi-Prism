"""The page of maps on the host: the whole map's record and each fitted map's, two halves
of them (the frames read one, a redraw writes the other; the lamps' faces' records after
them, the same in both), the fits kept while they hold the eye's slices, the FIT
commands a redraw asks for and the half they swap in."""

import numpy as np

from prism.stages.direct.shadow_pcf.model.maps import (
    FIT,
    PAGE,
    WHOLE,
    coarse_pages,
    level_count,
    map_pages,
    maps_words,
    record_at,
    record_words,
)
from prism_reference.direct import shadow_cascade as cascade
from prism_reference.direct.lights import shadow_side

LOOKUP_MARGIN = 4  # texels in from a fitted map's edge a point needs (cascade_shadow's)


def bias_of(lights, texel):
    """A map's depth bias for a texel of `texel` world units, the lights' in texels."""
    distance = float(lights["shadow_texel"] * lights["shadow_camera"][12])
    texels = float(lights["shadow_bias"]) * distance**2 / float(lights["shadow_texel"])
    return np.float32(texels * float(texel) / distance**2)


class Fits:
    """`count` maps of `side` fitted to the eye's slices widened by `margin`, the reach
    `reach` (None: the scene box's along the view), with their levels when `levels`;
    `scene` the frame's scene, `first_view` the first fitted view's index, `grid` a
    fitted view's (grid word, tiles)."""

    def __init__(self, scene, count, side, margin, levels, reach, first_view, grid):
        corners = scene["positions"]
        box = np.stack([corners.min(0), corners.max(0)])
        self.scene = {**scene, "positions": box}  # the box's corners: the fits read it
        self.count = count
        self.side = side
        self.margin = margin
        self.levels = levels
        self.reach = reach
        self.first_view = first_view
        self.grid = grid
        self.tail = []  # the records after the fitted maps' in both halves (faces')
        self.half = 0  # the half the frames read
        self.cameras = [None] * count  # each fitted map's camera in that half
        self.places = [0] * count  # each fitted map's pages (0 or 1) in that half
        self.asked = []  # the FIT commands of the redraw: (record, half, last)
        self.redraws = []  # each redraw: the maps drawn again
        self.next = (self.cameras, self.places)  # the redraw's, swapped in at its last

    def fit_pages(self, whole_side):
        """The fitted tensor's pages: two places of each fitted map's pages, then with
        the levels the coarse levels' pages (the whole map's, then two places of each
        fitted map's)."""
        maps = 2 * self.count * map_pages(self.side)
        if not self.levels:
            return maps
        return (
            maps + coarse_pages(whole_side) + 2 * self.count * coarse_pages(self.side)
        )

    def slot_count(self, whole_side):
        """The slots (and tops) of the maps' tiles: the whole map's, then two places of
        each fitted map's; none without the levels."""
        if not self.levels:
            return 0
        return map_pages(whole_side) + 2 * self.count * map_pages(self.side)

    def first_of(self, index, place):
        """The first page of fitted map `index`'s pages at `place`."""
        return (2 * index + place) * map_pages(self.side)

    def coarse_first(self, whole_side, index=None, place=0):
        """The first page of a map's coarse levels: the whole map's (`index` None), else
        fitted map `index`'s at `place`."""
        base = 2 * self.count * map_pages(self.side)
        if index is None:
            return base
        return (
            base
            + coarse_pages(whole_side)
            + (2 * index + place) * coarse_pages(self.side)
        )

    def slot_first(self, whole_side, index=None, place=0):
        """The first slot of a map's tiles: the whole map's (`index` None), else fitted
        map `index`'s at `place`."""
        if index is None:
            return 0
        return map_pages(whole_side) + (2 * index + place) * map_pages(self.side)

    def level_record(self, fitted, side, slot, coarse):
        """A record's levels' words: its levels, slots, tops and coarse pages."""
        if not self.levels:
            return {}
        return {
            "levels": level_count(side),
            "levels_tensor": fitted["slots"].address,
            "levels_first": slot,
            "tops": fitted["tops"].address,
            "coarse_tensor": fitted["maps"].address,
            "coarse_first": coarse,
        }

    def whole_record(self, lights, target, fitted):
        """The whole map's record: in the light pages `target`, its levels in the
        tensors `fitted` (maps, slots, tops)."""
        side = shadow_side(lights)
        record = {
            "tensor": target.address,
            "first": 0,
            "across": side // PAGE,
            "down": side // PAGE,
            "side": side,
            "texel": lights["shadow_texel"],
            "bias": lights["shadow_bias"],
            "kind": WHOLE,
        }
        record |= self.level_record(fitted, side, 0, self.coarse_first(side))
        return record_words(lights["shadow_camera"], record)

    def fit_record(self, lights, fitted, index, camera, place):
        """Fitted map `index`'s record at `place`, `camera` None: no map."""
        if camera is None:
            return record_words(np.zeros(16, np.float32), {"kind": FIT, "which": index})
        whole_side = shadow_side(lights)
        centre = (self.scene["positions"].min(0) + self.scene["positions"].max(0)) / 2
        distance = float(np.linalg.norm(lights["shadow_camera"][0:3] - centre))
        texel = np.float32(distance / camera[12])
        record = {
            "tensor": fitted["maps"].address,
            "first": self.first_of(index, place),
            "across": self.side // PAGE,
            "down": self.side // PAGE,
            "side": self.side,
            "grid": self.grid[0],
            "tiles": self.grid[1],
            "texel": texel,
            "bias": bias_of(lights, texel),
            "margin": LOOKUP_MARGIN,
            "kind": FIT,
            "which": index,
            "view": self.first_view + index,
        }
        record |= self.level_record(
            fitted,
            self.side,
            self.slot_first(whole_side, index, place),
            self.coarse_first(whole_side, index, place),
        )
        return record_words(camera, record)

    def records(self):
        """The records a half: the whole map's, the fitted maps', the tail's."""
        return 1 + self.count + len(self.tail)

    def half_records(self, lights, target, fitted, cameras, places):
        """A half's records: the whole map's, then each fitted map's, then the tail."""
        out = [self.whole_record(lights, target, fitted)]
        for index, (camera, place) in enumerate(zip(cameras, places, strict=True)):
            out.append(self.fit_record(lights, fitted, index, camera, place))
        return out + list(self.tail)

    def words(self, lights, target, fitted):
        """The page of maps' words: both halves as the frames read now (no fit yet)."""
        records = self.half_records(lights, target, fitted, self.cameras, self.places)
        pages = fitted["maps"].pages if fitted else 0
        return maps_words(self.records(), pages, [records, records])

    def half_words(self, lights, target, fitted, cameras, places, half):
        """(byte, words) of half `half`'s records in the page of maps."""
        records = self.half_records(lights, target, fitted, cameras, places)
        at = record_at(self.records(), half, 0)
        return 4 * at, np.concatenate(records)

    def view_of(self, camera, size):
        """The frame's scene at `camera` and `size` as the fit reads it."""
        return {**self.scene, "camera": camera, "size": tuple(size)}

    def first_cameras(self, sun):
        """The fitted cameras of the scene's own camera (the views' sizes for lists)."""
        view = {**self.scene}
        cameras, _ = cascade.cascade_cameras(
            view, sun, self.count, self.side, self.reach, self.margin
        )
        return cameras

    def gone(self, lights, target, fitted):
        """The sun moved: the other half with no fitted map (its whole map's record at
        the new sun), the half the SUN command swaps in; (half, byte, words)."""
        half = 1 - self.half
        self.cameras = [None] * self.count
        self.asked = []
        at, words = self.half_words(
            lights, target, fitted, self.cameras, self.places, half
        )
        return half, at, words

    def swapped(self, half):
        """The frames read `half` from now."""
        self.half = half

    def follow(self, lights, target, fitted, camera, size):
        """The eye at `camera`: when no redraw is asked and a fit does not hold its
        slice, the other half's records with those maps fitted again at their other
        pages, and the FIT commands that draw them, the last one swapping; (byte, words)
        of that half, or None."""
        if self.asked or not self.count:
            return None
        view = self.view_of(camera, size)
        cameras, again = cascade.kept_cameras(
            self.cameras,
            view,
            lights["sun_direction"],
            self.side,
            self.reach,
            self.margin,
        )
        if not any(again):
            return None
        half = 1 - self.half
        places = [1 - p if a else p for p, a in zip(self.places, again, strict=True)]
        drawn = [index for index, a in enumerate(again) if a]
        self.asked = [(1 + index, half, int(index == drawn[-1])) for index in drawn]
        self.next = (cameras, places)
        self.redraws.append(drawn)
        return self.half_words(lights, target, fitted, cameras, places, half)

    def served(self, code):
        """The first FIT asked came back with `code`: taken off when 0; the half its
        last one swapped in read from then on."""
        if code or not self.asked:
            return
        _, half, last = self.asked.pop(0)
        if last:
            self.half = half
            self.cameras, self.places = self.next
