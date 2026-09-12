"""Skill Quality Lab command-line toolkit."""

try:
    from ._version import __version__
except ModuleNotFoundError:
    from importlib.metadata import PackageNotFoundError, version

    try:
        __version__ = version("skill-quality-lab")
    except PackageNotFoundError:
        __version__ = "0.0.0.dev0"
