"""`halpid` is a power monitor and watchdog for the HALPI2 computers.
It communicates with the HALPI2 controller, providing the "smart"
aspects of the operation."""

from importlib import metadata as importlib_metadata


def get_version() -> str:
    try:
        return importlib_metadata.version(__name__)
    except importlib_metadata.PackageNotFoundError:  # pragma: no cover
        return "unknown"


version: str = get_version()
