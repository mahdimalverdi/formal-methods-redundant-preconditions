"""Convenience wrapper for building the submission zip from the repo root."""

from __future__ import annotations

import sys

from tools.make_submission_zip import main


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

