"""Creates the submission zip file for the course project."""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path


INCLUDE_FILES = [
    "docs/final_report.md",
    "docs/final_report.tex",
    "docs/final_report.pdf",
    "docs/paper_template.tex",
    "docs/template_attribution.md",
    "docs/arsclassica_article_original.tex",
    "docs/arsclassica_structure_original.tex",
    "docs/arsclassica_structure_rtl.tex",
    "docs/arsclassica_sample.bib",
    "outputs/run_results.txt",
    "requirements.txt",
    "main.py",
    "fm_project/cli.py",
    "fm_project/redundancy_checker.py",
    "fm_project/simulation.py",
    "fm_project/group_redundancy.py",
    "make_submission_zip.py",
    "tools/make_submission_zip.py",
    "tools/install_vazir.py",
    "examples/sub.json",
    "examples/group_redundancy.json",
    "docs/papers/542aec51ce80853093c4dafd6d81b17a.pdf",
    "docs/papers/Nicola_Redundant_Preconditions.pdf",
    "fonts/Vazirmatn-Regular.ttf",
    "fonts/Vazirmatn-Bold.ttf",
    "outputs/simulation_report.json",
    "outputs/simulation_summary.txt",
    "outputs/group_redundancy_report.json",
]


def main(argv: list[str]) -> int:
    """Builds a zip file named `<EnglishName>_<StudentNumber>.zip`."""
    if len(argv) != 3:
        print(
            "Usage: python make_submission_zip.py <EnglishName> <StudentNumber>",
            file=sys.stderr,
        )
        print(
            "Example: python make_submission_zip.py AliRezaei 401234567",
            file=sys.stderr,
        )
        return 2

    english_name = argv[1].strip()
    student_number = argv[2].strip()
    if not english_name or not student_number:
        print("Name and student number must be non-empty.", file=sys.stderr)
        return 2

    zip_name = f"{english_name}_{student_number}.zip"
    root = Path(".").resolve()
    zip_path = root / zip_name

    missing = [p for p in INCLUDE_FILES if not (root / p).exists()]
    if missing:
        print("Missing required files:", file=sys.stderr)
        for p in missing:
            print(f"- {p}", file=sys.stderr)
        return 1

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel in INCLUDE_FILES:
            zf.write(root / rel, arcname=rel)

    print(zip_name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
