"""The sun's shadow map of a loaded loop: its host, its pages read back or cleared, two
maps judged byte for byte."""

import numpy as np

from prism.stages.direct.shadow_pcf.model.region import map_pages

SHADOW = "direct.shadow_pcf"  # the sun's pass's implementation


def shadow_host(loop):
    """The loaded run's host of the sun's pass (None: the program has none)."""
    return loop.loaded.hosts.get(SHADOW)


def map_of(loop):
    """The shadow map's pages read back: (pages, page bytes) uint8."""
    host = shadow_host(loop)
    (got,) = loop.loaded.session.read(host.target, pages=map_pages(host.lights))
    return np.array(got, dtype=np.uint8)


def cleared(loop):
    """The shadow map's pages written with zeros (nothing left of another run)."""
    host = shadow_host(loop)
    pages = map_pages(host.lights)
    zeros = np.zeros((pages, host.target.page_bytes), dtype=np.uint8)
    loop.loaded.session.write(host.target, zeros, 0)


def judged(got, want):
    """Two maps byte for byte: the pages and bytes that differ, the first page."""
    differ = got != want
    pages = np.nonzero(differ.any(axis=1))[0]
    return {
        "equal": not differ.any(),
        "bytes_differ": int(differ.sum()),
        "pages_differ": len(pages),
        "first_page": int(pages[0]) if len(pages) else None,
        "nonzero_pages": int(got.any(axis=1).sum()),
    }
