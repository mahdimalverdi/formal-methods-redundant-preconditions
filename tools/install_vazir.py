"""Installs Vazir font files under fonts/.

This script downloads the latest release of the Vazir family (Vazirmatn) from
GitHub and extracts `Vazirmatn-Regular.ttf` and `Vazirmatn-Bold.ttf` into
`fonts/`.

Usage:
  .venv/bin/python tools/install_vazir.py
"""

from __future__ import annotations

import json
import os
import zipfile
from pathlib import Path
from typing import Iterable
from urllib.request import Request, urlopen


GITHUB_API_LATEST = "https://api.github.com/repos/rastikerdar/vazir-font/releases/latest"


class InstallError(RuntimeError):
    pass


def _http_get_json(url: str) -> dict:
    req = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "fm-project-vazir-installer",
        },
    )
    with urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _download(url: str, dst: Path) -> None:
    req = Request(url, headers={"User-Agent": "fm-project-vazir-installer"})
    with urlopen(req, timeout=300) as resp:
        dst.write_bytes(resp.read())


def _pick_zip_asset(release: dict) -> tuple[str, str]:
    assets = release.get("assets", [])
    if not isinstance(assets, list):
        raise InstallError("Unexpected GitHub API response: assets is not a list.")

    candidates: list[tuple[str, str]] = []
    for asset in assets:
        name = asset.get("name")
        url = asset.get("browser_download_url")
        if not isinstance(name, str) or not isinstance(url, str):
            continue
        if name.lower().endswith(".zip"):
            candidates.append((name, url))

    if not candidates:
        raise InstallError("No .zip assets found in latest Vazir release.")

    # Prefer the 'Vazir.zip' style asset if present.
    candidates.sort(key=lambda x: (x[0].lower() != "vazir.zip", x[0].lower()))
    return candidates[0]


def _find_first(names: Iterable[str], *, suffix: str, target_basename: str) -> str | None:
    for n in names:
        if not n.lower().endswith(suffix.lower()):
            continue
        if Path(n).name.lower() == target_basename.lower():
            return n
    return None


def install() -> None:
    root = Path(__file__).resolve().parents[1]
    fonts_dir = root / "fonts"
    fonts_dir.mkdir(parents=True, exist_ok=True)

    release = _http_get_json(GITHUB_API_LATEST)
    asset_name, url = _pick_zip_asset(release)

    archive_path = Path("/tmp") / f"vazir-{os.getpid()}.zip"
    _download(url, archive_path)

    with zipfile.ZipFile(archive_path, "r") as zf:
        names = zf.namelist()
        regular = _find_first(names, suffix=".ttf", target_basename="Vazirmatn-Regular.ttf")
        bold = _find_first(names, suffix=".ttf", target_basename="Vazirmatn-Bold.ttf")

        if regular is None or bold is None:
            raise InstallError(
                "Could not locate Vazirmatn-Regular.ttf and Vazirmatn-Bold.ttf in downloaded zip."
            )

        (fonts_dir / "Vazirmatn-Regular.ttf").write_bytes(zf.read(regular))
        (fonts_dir / "Vazirmatn-Bold.ttf").write_bytes(zf.read(bold))

    print("Installed fonts/Vazirmatn-Regular.ttf and fonts/Vazirmatn-Bold.ttf")


def main() -> None:
    install()


if __name__ == "__main__":
    main()
