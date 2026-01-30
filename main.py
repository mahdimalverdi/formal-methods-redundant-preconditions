"""Convenience wrapper for running the CLI from the repo root."""

from __future__ import annotations

from absl import app

from fm_project.cli import main


if __name__ == "__main__":
    app.run(main)

