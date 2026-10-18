"""Single source of truth for the application and Python package version."""

__version__ = "0.31.0"


def build_info(revision: str) -> dict[str, str | None]:
    return {"version": __version__, "revision": revision or None}
