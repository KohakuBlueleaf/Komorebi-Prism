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


def run(check, loaded, out):
    """`check(loaded)` run; its numbers with the seconds it took, the card's clock
    before and after and the date, written to the JSON file `out` and returned."""
    card = card_of(loaded)
    clock = [power.aiclk_mhz(card)]
    started = time.perf_counter()
    numbers = check(loaded)
    seconds = time.perf_counter() - started
    clock.append(power.aiclk_mhz(card))
    record = {
        "check": f"{check.__module__}.{check.__qualname__}",
        "pipeline": loaded.assembled.pipeline.name,
        "numbers": numbers,
        "seconds": seconds,
        "card": card,
        "aiclk_mhz": clock,
        "date": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=1, default=float) + "\n")
    return record
