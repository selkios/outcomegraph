"""Importable wrapper for the `og` entrypoint script."""

from __future__ import annotations

from pathlib import Path
import sys

_OG_SCRIPT = Path(__file__).with_name("og")
_OG_CODE = compile(_OG_SCRIPT.read_text(encoding="utf-8"), str(_OG_SCRIPT), "exec")
exec(_OG_CODE, globals(), globals())


def og_cli() -> None:
    """UV console-script entrypoint for `og`."""
    raise SystemExit(main(sys.argv[1:]))


def ogd_cli() -> None:
    """UV console-script entrypoint for daemon wrapper usage."""
    og_cli()
