"""Summarize results over the generated example suite.

This script computes simple statistics over `examples/generated/*.json` using the
same bounded redundancy checks as the CLI (VC-style removal check + IC-like
bounded implication check).

It is intentionally lightweight: it produces aggregate numbers suitable for the
final report without dumping per-example traces.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from absl import app
from absl import flags

# Allow running both as `python -m tools.summarize_generated_examples` and
# as `python tools/summarize_generated_examples.py` from the repo root.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from fm_project import redundancy_checker  # pylint: disable=wrong-import-position


_FLAGS = flags.FLAGS

flags.DEFINE_string(
    "examples_dir",
    "examples/generated",
    "Directory containing generated example JSON specs.",
)
flags.DEFINE_integer(
    "limit",
    0,
    "If >0, process only the first N examples (lexicographic).",
)
flags.DEFINE_string(
    "out_json",
    "outputs/generated_examples_summary.json",
    "Path for JSON output.",
)
flags.DEFINE_string(
    "out_txt",
    "outputs/generated_examples_summary.txt",
    "Path for human-readable output.",
)


JsonObject = dict[str, Any]


@dataclass(frozen=True)
class _ExampleCounts:
    num_pre: int
    needed: int
    redundant: int
    ic_implied: int


def _load_spec(path: Path) -> JsonObject:
    return json.loads(path.read_text(encoding="utf-8"))


def _analyze_one(path: Path) -> _ExampleCounts:
    spec = _load_spec(path)
    program = list(spec["program"])
    pre = list(spec.get("pre", []))
    post = list(spec.get("post", []))
    input_ranges = dict(spec["inputs"])
    step_limit = int(spec.get("step_limit", 10000))

    redundant_indices: set[int] = set()
    for idx in range(len(pre)):
        reduced = [x for j, x in enumerate(pre) if j != idx]
        rr = redundancy_checker.run_contract(
            program=program,
            pre=reduced,
            post=post,
            input_ranges=input_ranges,
            step_limit=step_limit,
        )
        if rr.violations == 0 and rr.nontermination == 0:
            redundant_indices.add(idx)

    implied_indices: set[int] = set()
    for idx, p in enumerate(pre):
        others = [x for j, x in enumerate(pre) if j != idx]
        if redundancy_checker.implies_bounded(
            antecedent=others,
            consequent=p,
            input_ranges=input_ranges,
        ):
            implied_indices.add(idx)

    redundant = len(redundant_indices)
    needed = len(pre) - redundant
    return _ExampleCounts(
        num_pre=len(pre),
        needed=needed,
        redundant=redundant,
        ic_implied=len(implied_indices),
    )


def _mean(values: list[int]) -> float:
    if not values:
        return 0.0
    return float(sum(values)) / float(len(values))


def main(argv: list[str]) -> None:
    del argv  # unused (absl handles flags)

    examples_dir = Path(_FLAGS.examples_dir)
    paths = sorted(p for p in examples_dir.glob("ex_*.json") if p.is_file())
    if int(_FLAGS.limit) > 0:
        paths = paths[: int(_FLAGS.limit)]

    if not paths:
        raise app.UsageError(f"No examples found under {examples_dir}")

    counts: list[_ExampleCounts] = []
    for p in paths:
        counts.append(_analyze_one(p))

    num_pre = [c.num_pre for c in counts]
    needed = [c.needed for c in counts]
    redundant = [c.redundant for c in counts]
    implied = [c.ic_implied for c in counts]

    summary: JsonObject = {
        "examples_dir": str(examples_dir),
        "num_examples": len(counts),
        "avg_pre": _mean(num_pre),
        "avg_needed": _mean(needed),
        "avg_redundant": _mean(redundant),
        "avg_ic_implied": _mean(implied),
        "count_all_pre_redundant": sum(1 for c in counts if c.needed == 0),
        "count_has_needed_pre": sum(1 for c in counts if c.needed > 0),
        "min_pre": min(num_pre),
        "max_pre": max(num_pre),
        "min_needed": min(needed),
        "max_needed": max(needed),
        "min_redundant": min(redundant),
        "max_redundant": max(redundant),
    }

    out_json = Path(_FLAGS.out_json)
    out_txt = Path(_FLAGS.out_txt)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_txt.parent.mkdir(parents=True, exist_ok=True)

    out_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        f"Generated examples dir: {examples_dir}",
        f"Examples: {summary['num_examples']}",
        "",
        "Averages:",
        f"- #pre: {summary['avg_pre']:.2f}",
        f"- needed: {summary['avg_needed']:.2f}",
        f"- redundant: {summary['avg_redundant']:.2f}",
        f"- IC-like implied: {summary['avg_ic_implied']:.2f}",
        "",
        "Counts:",
        f"- all preconditions redundant: {summary['count_all_pre_redundant']}",
        f"- has at least one needed precondition: {summary['count_has_needed_pre']}",
        "",
        "Ranges:",
        f"- pre: [{summary['min_pre']}, {summary['max_pre']}]",
        f"- needed: [{summary['min_needed']}, {summary['max_needed']}]",
        f"- redundant: [{summary['min_redundant']}, {summary['max_redundant']}]",
        "",
    ]
    out_txt.write_text("\n".join(lines), encoding="utf-8")

    print(f"Wrote {out_json} and {out_txt}")


if __name__ == "__main__":
    app.run(main)

