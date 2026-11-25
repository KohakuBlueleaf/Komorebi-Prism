"""Building the C++ helpers: the compiler, its flags, a rebuild when a source changed."""

import os
import shutil
import subprocess
from pathlib import Path

from prism_common.paths import build_root

NATIVE = Path(__file__).resolve().parent
COMMON = NATIVE / "common"
RASTER = NATIVE / "raster"
TRACE = NATIVE / "trace"
CXXFLAGS = ["-std=c++17", "-O3", "-ffp-contract=off", "-pthread"]


def find_cxx():
    """The C++ compiler: $CXX, else g++ or c++ on PATH, else None."""
    return os.environ.get("CXX") or shutil.which("g++") or shutil.which("c++")


def stale(binary, sources):
    """True when the binary is missing or older than any of the source files."""
    if not binary.exists():
        return True
    return any(Path(s).stat().st_mtime > binary.stat().st_mtime for s in sources)


def build(source, name, includes=(), shared=False):
    """Compiles one source file to <build root>/<name>; None if there is no compiler.
    shared: a shared library, for ctypes."""
    compiler = find_cxx()
    if compiler is None:
        return None
    out = build_root() / name
    deps = [source, *COMMON.glob("*.hpp"), *Path(source).parent.glob("*.hpp")]
    deps += [h for i in includes for h in Path(i).glob("*.hpp")]
    if stale(out, deps):
        flags = CXXFLAGS + (["-shared", "-fPIC"] if shared else [])
        inc = [f"-I{p}" for p in (COMMON, Path(source).parent, *includes)]
        subprocess.run([compiler, *flags, *inc, "-o", out, source], check=True)
    return out
