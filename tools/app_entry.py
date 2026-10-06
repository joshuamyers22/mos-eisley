"""Frozen application entry point; no paid requests during setup or installation."""

from mos_eisley.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
