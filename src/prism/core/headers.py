"""Numbers read from C and C++ headers: `constexpr uint32_t` constants and `#define`s."""

import re
from pathlib import Path

# the device headers shared by every implementation's kernels and thread units
INCLUDE = Path(__file__).resolve().parent / "include"
CONSTEXPR = re.compile(r"constexpr\s+uint32_t\s+(k\w+)\s*=\s*(0x[0-9A-Fa-f]+|\d+)\s*;")
DEFINE = re.compile(
    r"^#define\s+(\w+)\s+(0x[0-9A-Fa-f]+|\d+\.\d*|\d+)u?\s*(?:/\*.*)?$", re.MULTILINE
)


def constexpr(path):
    """{name: int} of every `constexpr uint32_t kName = <int>;` of the header at `path`."""
    text = Path(path).read_text()
    return {name: int(value, 0) for name, value in CONSTEXPR.findall(text)}


def defined(path):
    """{name: number} of every `#define NAME <literal>` of the header at `path`: an int
    (decimal or hex, `u` allowed) or a float (a decimal point)."""
    text = Path(path).read_text()
    return {
        name: float(value) if "." in value else int(value, 0)
        for name, value in DEFINE.findall(text)
    }
