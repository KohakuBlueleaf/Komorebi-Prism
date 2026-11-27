"""Runs the texture lookups' check (no card); one JSON line with `ok`, exit 1 on a
difference."""

import json
import sys
import time

from checks.surface import record
from checks.texture_lookup.cases import lookup_cases


def main():
    """Runs every case."""
    started = time.perf_counter()
    lookup_cases()
    different = [r for r in record.RESULTS if not r["equal"]]
    summary = {
        "ok": not different,
        "cases": len(record.RESULTS),
        "different": different,
    }
    summary["seconds"] = round(time.perf_counter() - started, 2)
    print(json.dumps(summary))
    return 1 if different else 0


if __name__ == "__main__":
    sys.exit(main())
