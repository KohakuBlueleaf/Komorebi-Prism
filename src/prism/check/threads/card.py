"""A frame of the threads' form on a loaded loop: its phases and policy set, run once
without the hosts' recoveries (a bad end leaves where it stood), the tensors written
and read page by page, and a check's record written outside the repository."""

import datetime
import json
from pathlib import Path

import komorebi as km
import numpy as np

from prism.check.threads import names
from prism.check.threads.model import pages, words_of
from prism.check.threads.standing import standing
from prism.core.implementation import hosted


def set_frame(loop, phases=0, policy=None):
    """The view's phases (a mask, 0 every one) and the tile pull's policy by name."""
    loaded = loop.loaded
    loaded.number(names.PHASES, int(phases))
    if policy is not None:
        if policy not in names.POLICIES:
            raise ValueError(f"policy {policy!r}, not one of {sorted(names.POLICIES)}")
        loaded.number(names.POLICY, names.POLICIES[policy])


def run_frame(loop, camera, phases=0, policy=None, picture=True, sends=True):
    """One frame of `camera` with `phases` and `policy`, no retry or reload, the hosts'
    commands sent first as the loop sends them when `sends` (else the FRAME command
    alone): {code, picture (None unless asked and 0), standing (None unless it ended
    badly)}."""
    camera = np.asarray(camera, dtype=np.float32)
    try:
        for host in loop.hosts():  # their numbers first, ours over them
            hosted(host, "view")(loop.loaded, camera, loop.size)
        set_frame(loop, phases, policy)
        code = loop.attempt(camera) if sends else loop.loaded.frame()
    except (km.KomorebiError, TimeoutError) as error:
        return {
            "code": None,
            "picture": None,
            "standing": standing(loop.loaded, None, error),
        }
    if code:
        return {"code": code, "picture": None, "standing": standing(loop.loaded, code)}
    shown = loop.picture() if picture else None
    return {
        "code": 0,
        "picture": None if shown is None else shown.copy(),
        "standing": None,
    }


def closed(loop):
    """The loop stopped unless a bad end stopped it: None, or the stop's error text."""
    if loop.loaded.result is not None:
        return None
    try:
        loop.stop()
    except km.KomorebiError as error:
        return str(error)
    return None


def write_words(session, tensor, words, first=0):
    """`words` written into `tensor` from page `first`, in whole pages; ValueError past
    its pages."""
    rows = pages(words, tensor.page_bytes)
    if first + len(rows) > tensor.pages:
        raise ValueError(
            f"{len(rows)} pages from page {first} pass the tensor's {tensor.pages}"
        )
    session.write(tensor, rows, first)


def read_words(session, tensor, count=None, first=0):
    """`count` pages of `tensor` from page `first` (None: to its end) as uint32 rows."""
    (rows,) = session.read(tensor, first=first, pages=count)  # a list: one tensor's
    return words_of(rows)


def write_per_core(session, tensor, image):
    """A page a core: row r of `image` (cores, words) into page r."""
    for rank, row in enumerate(image):
        write_words(session, tensor, row, rank)


def read_per_core(session, tensor, cores, words):
    """A page a core read back: (cores, words) uint32."""
    return read_words(session, tensor, cores)[:, :words]


def slots_of(session, tensor, slots, slot_words):
    """The first `slots` list slots of a lists tensor: (slots, slot_words) uint32."""
    flat = read_words(session, tensor).reshape(-1)
    return flat[: slots * slot_words].reshape(slots, slot_words)


def plain(value):
    """A numpy number or array as JSON takes it; anything else as its text."""
    return value.tolist() if hasattr(value, "tolist") else str(value)


def recorded(record, out):
    """`record` with the date written to the JSON file `out`; the record."""
    record = dict(record)
    record["date"] = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=1, default=plain) + "\n")
    return record
