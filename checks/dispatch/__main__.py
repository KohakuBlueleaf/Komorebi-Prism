"""The tile pull's choice (dp_choose) built with host gcc against a model of cores that
ask at random costs: every record handed exactly once under each policy; under
preference and order a core never refused while a record is left; under kept a core
gets only its slices; the same on four host threads at once. Exit 1 on a difference."""

import ctypes
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

from prism.core.headers import INCLUDE
from prism.program.dispatch import thread as dispatch
from prism_common.paths import build_root

HERE = Path(__file__).resolve().parent
SOURCES = (dispatch.RUNTIME / "dispatch_choose.c", HERE / "model.c")
SLICES_MOST = 1024
SLICE_RECORDS = dispatch.geometry.SLICE_RECORDS
NONE = 0xFFFFFFFF
RESULTS = []


def build():
    """The choice and the model as a library in the build root."""
    out = build_root() / "dispatch_choose_model.so"
    out.parent.mkdir(parents=True, exist_ok=True)
    command = ["gcc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-shared"]
    command += ["-fPIC", "-pthread", f"-DDP_SLICES_MOST={SLICES_MOST}u"]
    command += [f"-DTR_SLICE_RECORDS={SLICE_RECORDS}u"]
    command += [f"-I{HERE / 'include'}", f"-I{dispatch.RUNTIME}", f"-I{INCLUDE}"]
    subprocess.run([*command, *map(str, SOURCES), "-o", str(out)], check=True)
    library = ctypes.CDLL(str(out))
    pointer, word = ctypes.c_void_p, ctypes.c_uint32
    library.dpm_bytes.restype = word
    library.dpm_run.argtypes = [pointer, pointer, pointer, word, pointer, pointer]
    library.dpm_run.restype = word
    library.dpm_threads.argtypes = [pointer, pointer, pointer, pointer, pointer]
    library.dpm_threads.restype = word
    return library


def record(case, failures, **numbers):
    """A case's result kept and printed."""
    RESULTS.append({"case": case, "failures": failures, **numbers})
    print(json.dumps(RESULTS[-1]))


def slices_of(slices, seed, empty):
    """Records a slice (a share `empty` of the slices without any) and their weights,
    skewed as a frame's tiles are."""
    rng = np.random.default_rng(seed)
    records = rng.integers(1, SLICE_RECORDS + 1, slices).astype(np.uint32)
    records[rng.random(slices) < empty] = 0
    weights = np.array(
        [int((rng.pareto(1.2, n) * 40 + 1).sum()) for n in records], np.uint32
    )
    return records, weights


def setting_of(policy, near, first, count, slices, across, depth):
    """The model's setting words (`across`: the slices a row of the grid)."""
    words = (dispatch.POLICIES[policy], near, first, count, slices, across, depth)
    return np.array(words, np.uint32)


def run_case(library, policy, first, count, slices, seed, near=2, depth=2, empty=0.1):
    """One pull in the model of asking cores."""
    records, weights = slices_of(slices, seed, empty)
    setting = setting_of(policy, near, first, count, slices, 4, depth)
    who = np.full(slices * SLICE_RECORDS, NONE, np.uint32)
    stats = np.zeros(8, np.uint32)
    arrays = (setting, records, weights)
    code = library.dpm_run(
        *[a.ctypes.data for a in arrays], seed, who.ctypes.data, stats.ctypes.data
    )
    failures = [] if code == 0 else [f"the state refused ({code})"]
    failures += kept_failures(who, records, stats, policy, first, count)
    if policy != "kept" and stats[1]:
        failures.append(f"{int(stats[1])} cores refused while a record was left")
    if policy == "kept" and stats[2]:
        failures.append(f"{int(stats[2])} records of another rank's slice")
    name = f"model {policy}, cores {first}+{count}, {slices} slices, near {near}, "
    name += f"depth {depth}, seed {seed}"
    record(
        name,
        failures,
        records=int(records.sum()),
        handed=int(stats[4]),
        near=int(stats[3]),
        span=int(stats[7]),
    )


def kept_failures(who, records, stats, policy, first, count):
    """Every record handed once and nothing else; under kept, each by its rank."""
    failures = []
    table = who.reshape(len(records), SLICE_RECORDS)
    held = np.arange(SLICE_RECORDS)[None, :] < records[:, None]
    if stats[0]:
        failures.append(f"{int(stats[0])} records handed twice")
    if stats[6]:
        failures.append(f"{int(stats[6])} numbers out of the slices' records")
    if np.any(table[held] == NONE):
        failures.append(f"{int(np.sum(table[held] == NONE))} records never handed")
    if np.any(table[~held] != NONE):
        failures.append("a place past a slice's records handed")
    if policy == "kept":
        slices = np.repeat(np.arange(len(records)), SLICE_RECORDS).reshape(table.shape)
        ranks = table.astype(np.int64) - first
        if np.any(slices[held] % count != ranks[held]):
            failures.append("a record taken by a core it is not kept for")
    return failures


def threads_case(library, policy, first, count, slices, seed):
    """One pull with four host threads choosing at once, each for a quarter."""
    records, weights = slices_of(slices, seed, 0.05)
    setting = setting_of(policy, 3, first, count, slices, 4, 1)
    who = np.full(slices * SLICE_RECORDS, NONE, np.uint32)
    stats = np.zeros(8, np.uint32)
    arrays = (setting, records, weights, who, stats)
    code = library.dpm_threads(*[a.ctypes.data for a in arrays])
    failures = [] if code == 0 else [f"the state refused ({code})"]
    failures += kept_failures(who, records, stats, policy, first, count)
    name = f"threads {policy}, cores {first}+{count}, {slices} slices, seed {seed}"
    record(name, failures, records=int(records.sum()), handed=int(stats[4]))


def main():
    """Every case; exit 1 when one fails."""
    started = time.perf_counter()
    library = build()
    if library.dpm_bytes() != dispatch.state_bytes(
        dispatch.Capacity(1, SLICES_MOST, 1)
    ):
        record("state bytes", ["dp_choose_t's bytes differ from state_bytes"])
    for policy in dispatch.POLICIES:
        for seed in (1, 2, 3):
            run_case(library, policy, 0, 120, 130, seed)
            run_case(library, policy, 8, 112, 130, seed, depth=3)
        run_case(library, policy, 0, 120, 130, 4, near=0)
        run_case(library, policy, 0, 120, 130, 5, near=1000)
        run_case(library, policy, 0, 1, 40, 6, depth=1)
        run_case(library, policy, 0, 7, 500, 7)
        run_case(library, policy, 0, 128, SLICES_MOST, 8, empty=0.5)
        run_case(library, policy, 0, 120, 3, 9)
        run_case(library, policy, 0, 120, 130, 10, empty=1.0)
        for seed in (21, 22):
            threads_case(library, policy, 0, 120, 130, seed)
            threads_case(library, policy, 4, 116, SLICES_MOST, seed)
    failed = [r["case"] for r in RESULTS if r["failures"]]
    seconds = round(time.perf_counter() - started, 1)
    print(json.dumps({"cases": len(RESULTS), "failed": failed, "seconds": seconds}))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
