"""A loaded program's code and L1: each kernel's text, data and bss and each handler's
text, read from the ELF files its build left with the toolchain that built them; the
load's L1 budget table as rows."""

import os
import re
import subprocess
from pathlib import Path

from komorebi import _env
from komorebi.device import native
from komorebi.dsl.first_use import reserve_of

KERNELS = {"brisc": "reader", "ncrisc": "writer", "trisc0": "unpack"}
KERNELS |= {"trisc1": "math", "trisc2": "pack"}
CASE = re.compile(r"case (kHandler\w+): \{")
ROW = re.compile(r"^(\S+)\s+(\d+)\s+(0x[0-9a-f]+)")
LAMBDA = "kernel_main()::{lambda(km_command_t const&)#1}::operator()"  # the switch
FUNCTIONS = 12  # the largest functions listed a kernel


def run(tool, *args):
    """A toolchain tool's output."""
    return subprocess.run(
        [str(tool), *map(str, args)], capture_output=True, text=True, check=True
    ).stdout


def cache_roots():
    """tt-metal's kernel caches (TT_METAL_CACHE, else the user's cache folder)."""
    base = Path(os.environ.get("TT_METAL_CACHE") or Path.home() / ".cache")
    return sorted(base.glob("tt-metal-cache*/kernels"))


def elves(folder):
    """{RISC: ELF} of the kernels built from the build folder `folder` (the newest
    when several builds of it are cached)."""
    found = {}
    for root in cache_roots():
        for dephash in root.glob("*/*/*/*.o.dephash"):
            risc = dephash.parent.name
            elf = dephash.parent / f"{risc}.elf"
            if risc not in KERNELS or not elf.is_file():
                continue
            if str(folder) not in dephash.read_text(errors="replace"):
                continue
            if risc not in found or elf.stat().st_mtime > found[risc].stat().st_mtime:
                found[risc] = elf
    return found


def cases(source):
    """[(first line, handler)] of the command switch's cases in a generated source."""
    out = []
    for number, line in enumerate(source.read_text().splitlines(), 1):
        match = CASE.search(line)
        if match:
            name = match.group(1)[len("kHandler") :]
            out.append((number, re.sub(r"(?<!^)([A-Z])", r"_\1", name).lower()))
    return out


def handler_text(tool, elf, source, symbols):
    """{handler: text bytes} of the command switch's body in `elf`: each address of the
    line table charged to the case of `source` its last line of `source` lies in."""
    start, size = next(
        ((at, n) for name, at, n in symbols if LAMBDA in name), (None, None)
    )
    if start is None:
        return {}
    rows, current = [], None
    lines = run(tool / "riscv-tt-elf-readelf", "--debug-dump=decodedline", elf)
    for line in lines.splitlines():
        line = line.rstrip()
        if line.endswith(":") and "/" in line:
            current = line[:-1]
            continue
        match = ROW.match(line)
        if match and start <= int(match.group(3), 16) < start + size:
            own = current is not None and Path(current).name == source.name
            rows.append((int(match.group(3), 16), int(match.group(2)) if own else 0))
    rows.sort()
    switch = cases(source)
    out, case = {}, "dispatch"
    for index, (at, number) in enumerate(rows):
        if number:
            before = [name for first, name in switch if first <= number]
            case = before[-1] if before else "dispatch"
        end = rows[index + 1][0] if index + 1 < len(rows) else start + size
        out[case] = out.get(case, 0) + end - at
    return out


def symbols_of(tool, elf):
    """[(name, address, size)] of the ELF's text symbols."""
    out = []
    for line in run(
        tool / "riscv-tt-elf-nm", "-S", "-C", "--size-sort", elf
    ).splitlines():
        parts = line.split(maxsplit=3)
        if len(parts) == 4 and parts[2] in "tTwW":
            out.append((parts[3], int(parts[0], 16), int(parts[1], 16)))
    return out


def code_sizes(loaded):
    """Each kernel's text, data and bss bytes, its handlers' text in the command switch
    and its largest functions; None when the build's ELF files are not found."""
    folder = Path(loaded.assembled.program.built.folder)
    tool = _env.sfpi_bin(native.metal_tree(loaded.session.tree))
    found = elves(folder)
    if not found:
        return None
    out = {}
    for risc, elf in sorted(found.items()):
        text, data, bss = map(int, run(tool / "riscv-tt-elf-size", elf).split()[6:9])
        source = folder / (
            "compute.cpp" if risc.startswith("trisc") else "movement.cpp"
        )
        symbols = symbols_of(tool, elf)
        largest = sorted(symbols, key=lambda one: -one[2])[:FUNCTIONS]
        out[KERNELS[risc]] = {
            "risc": risc,
            "text": text,
            "data": data,
            "bss": bss,
            "handlers": handler_text(tool, elf, source, symbols),
            "functions": [[name, size] for name, _, size in largest],
        }
    return out


def l1_rows(loaded, trace):
    """The load's L1 budget table of a core as [what, bytes] rows, its total and the
    bytes the runtime leaves for them (as the load prints it)."""
    session, most = reserve_of(loaded.session)
    rows = session.l1_rows(loaded.assembled.program, trace)
    rows[2:2] = [(f"slots: service (reader), 1 x {most:,} B (at most)", most)]
    rows = [[what, int(size)] for what, size in rows]
    rows.append(["total", sum(size for _, size in rows)])
    return {"rows": rows, "free": int(loaded.session.l1()[1])}
