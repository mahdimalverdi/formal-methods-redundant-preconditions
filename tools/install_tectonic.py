"""Installs a local `tectonic` binary under tools/bin/.

This avoids needing a system TeX Live installation (latexmk/xelatex/pdflatex).

Usage:
  .venv/bin/python tools/install_tectonic.py

After installation, LaTeX Workshop is configured (via .vscode/settings.json)
to build using `${workspaceFolder}/tools/bin/tectonic`.
"""

from __future__ import annotations

import json
import os
import stat
import tarfile
import urllib.request
from pathlib import Path


GITHUB_API_LATEST = (
    "https://api.github.com/repos/tectonic-typesetting/tectonic/releases/latest"
)


class InstallError(RuntimeError):
    pass


def _http_get_json(url: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "fm-project-tectonic-installer",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _download(url: str, dst: Path) -> None:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "fm-project-tectonic-installer"},
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        dst.write_bytes(resp.read())


def _pick_asset(release: dict) -> tuple[str, str]:
    assets = release.get("assets", [])
    if not isinstance(assets, list):
        raise InstallError("Unexpected GitHub API response: assets is not a list.")

    candidates: list[tuple[str, str]] = []
    for a in assets:
        name = a.get("name")
        url = a.get("browser_download_url")
        if not isinstance(name, str) or not isinstance(url, str):
            continue
        # Prefer glibc builds for standard Linux.
        if name.endswith(".tar.gz") and "x86_64-unknown-linux-gnu" in name:
            candidates.append((name, url))
        elif name.endswith(".tar.gz") and "unknown-linux-gnu" in name:
            candidates.append((name, url))

    if not candidates:
        raise InstallError("No suitable linux-gnu tar.gz asset found in latest release.")

    # Prefer the most specific match first.
    candidates.sort(key=lambda x: ("x86_64-unknown-linux-gnu" not in x[0], x[0]))
    return candidates[0]


def install() -> Path:
    root = Path(__file__).resolve().parents[1]
    bin_dir = root / "tools" / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)

    release = _http_get_json(GITHUB_API_LATEST)
    tag = release.get("tag_name", "unknown")
    asset_name, url = _pick_asset(release)

    archive_path = Path("/tmp") / asset_name
    _download(url, archive_path)

    extracted_dir = Path("/tmp") / f"tectonic-extract-{os.getpid()}"
    extracted_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, "r:gz") as tf:
        tf.extractall(extracted_dir)

    # Find the binary inside the extracted directory.
    binary_candidates = list(extracted_dir.rglob("tectonic"))
    if not binary_candidates:
        raise InstallError("Downloaded archive did not contain a `tectonic` binary.")

    src = binary_candidates[0]
    dst = bin_dir / "tectonic"
    dst.write_bytes(src.read_bytes())
    dst.chmod(dst.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    print(f"Installed {dst} from {asset_name} ({tag})")
    return dst


def main() -> None:
    install()


if __name__ == "__main__":
    main()

