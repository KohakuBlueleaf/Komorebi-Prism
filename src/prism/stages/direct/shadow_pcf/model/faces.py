"""The lamps' faces on the host: each face of the reference's lamp maps a record of the
page of maps after the fitted maps' (the same in both halves), its map and levels in the
unit's own tensors after the fitted maps', and the LAMPS commands that draw the faces
not drawn, as many a command as the time a face takes allows."""

import numpy as np

from prism.stages.direct.shadow_pcf.model.maps import (
    FACE,
    coarse_pages,
    level_count,
    map_pages,
    record_words,
    tiles_of,
)
from prism_reference.direct.lamp_maps import lamp_faces

LAMPS_SECONDS = 0.5  # a LAMPS command's views at most: half the director's give-up


class Faces:
    """The lamp faces of `lights` (none without lamps), with their levels when
    `levels`; `first_view` the first face's view, `first_record` its record's index."""

    def __init__(self, lights, levels, first_view, first_record):
        self.faces = lamp_faces(lights)
        self.levels = levels
        self.first_view = first_view
        self.first_record = first_record
        self.firsts = []  # each face's (first page, first coarse page, first slot)
        self.left = []  # the faces not drawn in the loaded run, in order
        self.count = 1  # the faces the next LAMPS command draws
        self.asked = None  # the LAMPS command sent: (first record, faces)

    def sizes(self):
        """Each face's (width, height)."""
        return [tuple(int(v) for v in face["size"]) for face in self.faces]

    def pages(self):
        """The faces' pages and, with the levels, their coarse levels' pages."""
        maps = sum(map_pages(*size) for size in self.sizes())
        if not self.levels:
            return maps
        return maps + sum(coarse_pages(*size) for size in self.sizes())

    def slots(self):
        """The slots (and tops) of the faces' tiles; none without the levels."""
        return sum(map_pages(*size) for size in self.sizes()) if self.levels else 0

    def place(self, first, slot):
        """The faces' pages from page `first` of the maps' tensor (their maps, then
        their coarse levels) and their slots from slot `slot`."""
        sizes = self.sizes()
        coarse = first + sum(map_pages(*size) for size in sizes)
        self.firsts = []
        for size in sizes:
            self.firsts.append((first, coarse, slot))
            first += map_pages(*size)
            coarse += coarse_pages(*size)
            slot += map_pages(*size)

    def records(self, fitted, grid_of):
        """Each face's record words: in the tensors `fitted`, `grid_of(size)` a view's
        (grid word, tiles)."""
        out = []
        within = {}
        for index, (face, size, (first, coarse, slot)) in enumerate(
            zip(self.faces, self.sizes(), self.firsts, strict=True)
        ):
            across, down = tiles_of(*size)
            grid, tiles = grid_of(size)
            lamp = int(face["lamp"])
            which = (lamp << 8) | within.get(lamp, 0)
            within[lamp] = within.get(lamp, 0) + 1
            record = {
                "tensor": fitted["maps"].address,
                "first": first,
                "across": across,
                "down": down,
                "side": size[0],
                "grid": grid,
                "tiles": tiles,
                "kind": FACE,
                "which": which,
                "view": self.first_view + index,
            }
            if self.levels:
                record |= {
                    "levels": level_count(*size),
                    "levels_tensor": fitted["slots"].address,
                    "levels_first": slot,
                    "tops": fitted["tops"].address,
                    "coarse_tensor": fitted["maps"].address,
                    "coarse_first": coarse,
                }
            out.append(record_words(face["camera"], record))
        return out

    def cameras(self):
        """Each face's camera (16,) float32."""
        return [np.asarray(face["camera"], np.float32) for face in self.faces]

    def restart(self):
        """A run loaded: every face not drawn, one face the first command."""
        self.left = list(range(len(self.faces)))
        self.count, self.asked = 1, None

    def command(self):
        """The next LAMPS command's words (first record, faces), or None."""
        if not self.left:
            return None
        self.asked = (self.first_record + self.left[0], min(self.count, len(self.left)))
        return self.asked

    def served(self, code, seconds):
        """The LAMPS command asked came back with `code` after `seconds`: its faces
        drawn when 0, the next command's faces from the time one took."""
        if code or self.asked is None:
            return
        drawn = self.asked[1]
        self.left = self.left[drawn:]
        self.count = max(1, int(LAMPS_SECONDS * drawn / max(seconds, 1e-6)))
        self.asked = None
