"""The repository's rules, checked over every Python file: import direction between
packages, file length, ASCII source, imports inside functions. Exit 1 on a violation."""

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TREES = ("src", "apps", "checks", "scripts", "configs")
SOFT_LINES = 600
HARD_LINES = 1000

# Top-level names a package must not import, and the subtrees excepted from that.
FORBIDDEN = {
    "prism_common": (
        "komorebi",
        "prism",
        "prism_reference",
        "prism_cli",
        "prism_viewer",
    ),
    "prism_reference": ("komorebi", "prism", "prism_cli", "prism_viewer"),
    "prism": ("prism_cli", "prism_viewer"),
}
ALLOWED = {}


def package_of(path):
    """The top-level package a file belongs to, or None outside `src/`."""
    parts = path.relative_to(ROOT).parts
    return parts[1] if parts[0] == "src" and len(parts) > 2 else None


def imported(tree):
    """Each import of a module: (dotted name, line, True when inside a function)."""
    found = []

    def walk(node, inside):
        for child in ast.iter_child_nodes(node):
            deeper = inside or isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef)
            if isinstance(child, ast.Import):
                found.extend(
                    (alias.name, child.lineno, inside) for alias in child.names
                )
            elif (
                isinstance(child, ast.ImportFrom) and child.level == 0 and child.module
            ):
                found.append((child.module, child.lineno, inside))
            walk(child, deeper)

    walk(tree, False)
    return found


def allowed(package, name):
    """True when `package` may import the module `name`."""
    top = name.split(".")[0]
    if top not in FORBIDDEN.get(package, ()):
        return True
    return any(
        name == ok or name.startswith(ok + ".") for ok in ALLOWED.get(package, ())
    )


def check(path):
    """The violations of one file, as (line, text)."""
    raw = path.read_bytes()
    issues = []
    if not raw.isascii():
        issues.append((0, "non-ASCII source"))
    text = raw.decode("utf-8")
    lines = text.count("\n") + 1
    if lines > HARD_LINES:
        issues.append((0, f"{lines} lines (hard max {HARD_LINES})"))
    package = package_of(path)
    for name, line, inside in imported(ast.parse(text)):
        if inside:
            issues.append((line, f"import of {name} inside a function"))
        if package and not allowed(package, name):
            issues.append((line, f"{package} must not import {name}"))
    return issues, lines


def main():
    failed, long_files = 0, []
    files = sorted(p for tree in TREES for p in (ROOT / tree).rglob("*.py"))
    for path in files:
        issues, lines = check(path)
        if SOFT_LINES < lines <= HARD_LINES:
            long_files.append((path, lines))
        for line, text in issues:
            failed += 1
            print(f"{path.relative_to(ROOT)}:{line}: {text}")
    for path, lines in long_files:
        print(f"note: {path.relative_to(ROOT)}: {lines} lines (max {SOFT_LINES})")
    print(f"{len(files)} files, {failed} violations")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
