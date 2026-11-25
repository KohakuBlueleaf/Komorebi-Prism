"""`build(choice, REGISTRY)`: a name, dotted path, dict, class or instance resolved once."""

import importlib

USE = "use"


def located(path):
    """The object a dotted path `"pkg.mod:attr"` names."""
    module, _, attr = path.partition(":")
    if not attr:
        raise ValueError(f"{path!r}: a dotted path is 'package.module:attribute'")
    target = importlib.import_module(module)
    for part in attr.split("."):
        target = getattr(target, part)
    return target


def resolved(name, registry):
    """A registered name, or a dotted path when it holds a colon."""
    return located(name) if ":" in name else registry.get(name)


def build(choice, registry, **given):
    """`choice` resolved once: a registered name or a dotted path, a dict
    `{"use": <name or path>, ...options}`, a class (made with the options and `given`)
    or an instance (returned as it is)."""
    options = {}
    if isinstance(choice, dict):
        if USE not in choice:
            raise ValueError(f"{choice!r}: a dict choice names its target in {USE!r}")
        options = {key: value for key, value in choice.items() if key != USE}
        choice = choice[USE]
    target = resolved(choice, registry) if isinstance(choice, str) else choice
    if isinstance(target, type):
        return target(**options, **given)
    if options:
        raise ValueError(
            f"{registry.kind} {target!r} is an instance: it takes no options "
            f"({', '.join(options)})"
        )
    return target
