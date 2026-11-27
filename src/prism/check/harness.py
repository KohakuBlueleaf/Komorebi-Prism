"""A check run on a loaded program, written as one JSON record."""

import datetime
import json
import time
from pathlib import Path

from komorebi.bench import power


def card_of(loaded):
    """The card the loaded program runs on."""
    card = loaded.session.card
    return power.visible_card() if card is None else card


def read_text(path):
    """A sysfs file's text, stripped; None when it cannot be read."""
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


def pcie_link(card=None):
    """Card `card`'s (None: the visible card's) PCI address and its PCIe link speed
    now and at most, from sysfs; None for what cannot be read."""
    card = power.visible_card() if card is None else card
    entry = (
        power.SYS / "class" / "tenstorrent" / f"tenstorrent!{power.driver_number(card)}"
    )
    device = (entry / "device").resolve()
    return {
        "address": device.name if device.exists() else None,
        "current": read_text(device / "current_link_speed"),
        "max": read_text(device / "max_link_speed"),
    }


def run(check, loaded, out):
    """`check(loaded)` run; its numbers with the seconds it took, the card's clock and
    PCIe link before and after and the date, written to the JSON file `out` and
    returned."""
    card = card_of(loaded)
    clock = [power.aiclk_mhz(card)]
    link = [pcie_link(card)]
    started = time.perf_counter()
    numbers = check(loaded)
    seconds = time.perf_counter() - started
    clock.append(power.aiclk_mhz(card))
    link.append(pcie_link(card))
    record = {
        "check": f"{check.__module__}.{check.__qualname__}",
        "pipeline": loaded.assembled.pipeline.name,
        "numbers": numbers,
        "seconds": seconds,
        "card": card,
        "aiclk_mhz": clock,
        "pcie_link": link,
        "date": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=1, default=float) + "\n")
    return record
