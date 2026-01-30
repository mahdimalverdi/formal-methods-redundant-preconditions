"""Generates a set of realistic, human-like example specs.

The project uses a tiny JSON-defined language (see `fm_project/redundancy_checker`)
to analyze redundant preconditions. This script generates many small specs that
look like "human-authored" programming tasks (validation, clamping, counters,
simple loops) rather than purely random variations.
"""

from __future__ import annotations

import json
import random
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from absl import app
from absl import flags

# Allow running both as `python -m tools.generate_examples` and
# as `python tools/generate_examples.py` from the repo root.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from fm_project import redundancy_checker  # pylint: disable=wrong-import-position


_FLAGS = flags.FLAGS

flags.DEFINE_integer("count", 100, "Number of specs to generate.")
flags.DEFINE_integer("seed", 1, "Random seed (used only to pick from curated sets).")
flags.DEFINE_string(
    "out_dir",
    "examples/generated",
    "Output directory for `ex_###.json` files (created if missing).",
)
flags.DEFINE_bool(
    "validate",
    True,
    "Validate each generated spec with the bounded executor (recommended).",
)
flags.DEFINE_bool(
    "overwrite",
    True,
    "Overwrite existing `ex_###.json` files if they exist.",
)


JsonObject = dict[str, Any]


@dataclass(frozen=True)
class _Scenario:
    key: str
    title: str
    story: str
    spec: JsonObject
    expected_redundant_pre: list[str]


def _write_json(path: Path, obj: JsonObject) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _validate_spec(spec: JsonObject) -> None:
    result = redundancy_checker.run_contract(
        program=list(spec["program"]),
        pre=list(spec.get("pre", [])),
        post=list(spec.get("post", [])),
        input_ranges=dict(spec["inputs"]),
        step_limit=int(spec.get("step_limit", 10000)),
    )
    if result.violations != 0 or result.nontermination != 0:
        raise ValueError(
            "Generated spec is invalid under its own bounded domain: "
            f"violations={result.violations}, nontermination={result.nontermination}"
        )


def _scenario_clamp_temperature(rng: random.Random) -> _Scenario:
    min_ok, max_ok = rng.choice([(-40, 85), (-20, 60), (0, 100), (10, 40)])
    temp_name, out_name = rng.choice(
        [
            ("temp_c", "temp_safe"),
            ("sensor_temp", "clamped_temp"),
            ("room_temp", "temp_ok"),
        ]
    )

    spec: JsonObject = {
        "title": f"Clamp a temperature reading to [{min_ok}, {max_ok}]",
        "story": (
            "A temperature sensor may temporarily report values outside the safe "
            "operating range. Clamp the reading so downstream logic never sees "
            "out-of-range temperatures."
        ),
        "category": "sanitization/clamp",
        "inputs": {temp_name: {"min": min_ok - 30, "max": max_ok + 40}},
        "step_limit": 200,
        "pre": [
            f"{temp_name} >= {min_ok - 200}",
            f"{temp_name} <= {max_ok + 200}",
            f"{temp_name} >= {min_ok - 30}",
            f"{temp_name} <= {max_ok + 40}",
        ],
        "post": [
            (
                f"{out_name} >= {min_ok} and {out_name} <= {max_ok} and ("
                f"({temp_name} < {min_ok} and {out_name} == {min_ok}) or "
                f"({temp_name} > {max_ok} and {out_name} == {max_ok}) or "
                f"({temp_name} >= {min_ok} and {temp_name} <= {max_ok} and "
                f"{out_name} == {temp_name})"
                ")"
            )
        ],
        "program": [
            {"assign": {out_name: temp_name}},
            {
                "if": {
                    "cond": f"{temp_name} < {min_ok}",
                    "then": [{"assign": {out_name: f"{min_ok}"}}],
                    "else": [
                        {
                            "if": {
                                "cond": f"{temp_name} > {max_ok}",
                                "then": [{"assign": {out_name: f"{max_ok}"}}],
                                "else": [],
                            }
                        }
                    ],
                }
            },
        ],
    }

    expected = [
        f"{temp_name} >= {min_ok - 200}",
        f"{temp_name} <= {max_ok + 200}",
    ]
    return _Scenario(
        key="clamp_temperature",
        title=str(spec["title"]),
        story=str(spec["story"]),
        spec=spec,
        expected_redundant_pre=expected,
    )


def _scenario_abs_delta(rng: random.Random) -> _Scenario:
    delta_name, out_name = rng.choice(
        [("delta", "abs_delta"), ("err", "err_mag"), ("offset", "offset_mag")]
    )
    bound = rng.choice([10, 20, 50, 100])
    spec: JsonObject = {
        "title": "Absolute value of an error signal",
        "story": (
            "Convert a signed error signal into its magnitude so it can be compared "
            "against a threshold."
        ),
        "category": "arithmetic/abs",
        "inputs": {delta_name: {"min": -bound - 20, "max": bound + 20}},
        "step_limit": 50,
        "pre": [
            f"{delta_name} >= {-bound}",
            f"{delta_name} <= {bound}",
            f"{delta_name} >= {-bound - 100}",
            f"{delta_name} <= {bound + 100}",
        ],
        "post": [
            (
                f"{out_name} >= 0 and ("
                f"({delta_name} >= 0 and {out_name} == {delta_name}) or "
                f"({delta_name} < 0 and {out_name} == -{delta_name})"
                ")"
            )
        ],
        "program": [
            {
                "if": {
                    "cond": f"{delta_name} < 0",
                    "then": [{"assign": {out_name: f"-{delta_name}"}}],
                    "else": [{"assign": {out_name: delta_name}}],
                }
            }
        ],
    }
    expected = [
        f"{delta_name} >= {-bound - 100}",
        f"{delta_name} <= {bound + 100}",
    ]
    return _Scenario(
        key="abs_delta",
        title=str(spec["title"]),
        story=str(spec["story"]),
        spec=spec,
        expected_redundant_pre=expected,
    )


def _scenario_remainder_by_subtraction(rng: random.Random) -> _Scenario:
    amount_name, size_name = rng.choice([("amount", "bucket"), ("total", "chunk")])
    rem_name, q_name = rng.choice([("rem", "q"), ("left", "count")])
    max_amount = rng.choice([20, 30, 40])
    max_size = rng.choice([6, 8, 10])
    spec: JsonObject = {
        "title": "Remainder by repeated subtraction (packing items)",
        "story": (
            "A warehouse packs items into fixed-size boxes. Compute how many full "
            "boxes fit and how many items remain unpacked using repeated subtraction."
        ),
        "category": "loop/arithmetic",
        "inputs": {
            amount_name: {"min": -2, "max": max_amount},
            size_name: {"min": -1, "max": max_size},
        },
        "step_limit": 400,
        "pre": [
            f"{amount_name} >= 0",
            f"{size_name} > 0",
            f"{amount_name} >= -10",
            f"{size_name} >= 1",
        ],
        "post": [
            (
                f"{amount_name} == {q_name}*{size_name} + {rem_name} and "
                f"{rem_name} >= 0 and {rem_name} < {size_name}"
            )
        ],
        "program": [
            {"assign": {rem_name: amount_name, q_name: "0"}},
            {
                "while": {
                    "cond": f"{rem_name} >= {size_name}",
                    "body": [
                        {"assign": {rem_name: f"{rem_name} - {size_name}"}},
                        {"assign": {q_name: f"{q_name} + 1"}},
                    ],
                }
            },
        ],
    }
    expected = [
        f"{amount_name} >= -10",
        f"{size_name} >= 1",
    ]
    return _Scenario(
        key="remainder_by_subtraction",
        title=str(spec["title"]),
        story=str(spec["story"]),
        spec=spec,
        expected_redundant_pre=expected,
    )


def _scenario_sum_first_n(rng: random.Random) -> _Scenario:
    n_name = rng.choice(["n", "n_days", "n_items", "n_requests"])
    s_name = rng.choice(["sum", "total", "acc"])
    i_name = rng.choice(["i", "k", "idx"])
    max_n = rng.choice([10, 15, 20, 25])

    spec: JsonObject = {
        "title": "Sum of the first N integers (loop invariant style)",
        "story": (
            "Compute the sum 1+2+...+N using a loop, then check the classic closed "
            "form relation 2*sum == N*(N+1)."
        ),
        "category": "loop/summation",
        "inputs": {n_name: {"min": -5, "max": max_n}},
        "step_limit": 800,
        "pre": [
            f"{n_name} >= 0",
            f"{n_name} <= {max_n}",
            f"{n_name} >= -100",
            f"{n_name} <= {max_n + 100}",
        ],
        "post": [f"2*{s_name} == {n_name}*({n_name} + 1) and {i_name} == {n_name} + 1"],
        "program": [
            {"assign": {s_name: "0", i_name: "1"}},
            {
                "while": {
                    "cond": f"{i_name} <= {n_name}",
                    "body": [
                        {"assign": {s_name: f"{s_name} + {i_name}"}},
                        {"assign": {i_name: f"{i_name} + 1"}},
                    ],
                }
            },
        ],
    }
    expected = [f"{n_name} >= -100", f"{n_name} <= {max_n + 100}"]
    return _Scenario(
        key="sum_first_n",
        title=str(spec["title"]),
        story=str(spec["story"]),
        spec=spec,
        expected_redundant_pre=expected,
    )


def _scenario_min_two_values(rng: random.Random) -> _Scenario:
    a_name, b_name = rng.choice([("a", "b"), ("x", "y"), ("left", "right")])
    out_name = rng.choice(["m", "min_val", "min_ab"])
    max_abs = rng.choice([5, 10, 20])
    spec: JsonObject = {
        "title": "Minimum of two values",
        "story": (
            "Pick the smaller of two candidate values (e.g., two shipping offers) "
            "and store it as the chosen minimum."
        ),
        "category": "branch/min",
        "inputs": {
            a_name: {"min": -max_abs, "max": max_abs},
            b_name: {"min": -max_abs, "max": max_abs},
        },
        "step_limit": 80,
        "pre": [
            f"{a_name} >= {-max_abs}",
            f"{b_name} >= {-max_abs}",
            f"{a_name} >= {-max_abs - 10}",
            f"{b_name} >= {-max_abs - 10}",
        ],
        "post": [
            (
                f"{out_name} <= {a_name} and {out_name} <= {b_name} and ("
                f"({a_name} <= {b_name} and {out_name} == {a_name}) or "
                f"({a_name} > {b_name} and {out_name} == {b_name})"
                ")"
            )
        ],
        "program": [
            {
                "if": {
                    "cond": f"{a_name} <= {b_name}",
                    "then": [{"assign": {out_name: a_name}}],
                    "else": [{"assign": {out_name: b_name}}],
                }
            }
        ],
    }
    expected = [f"{a_name} >= {-max_abs - 10}", f"{b_name} >= {-max_abs - 10}"]
    return _Scenario(
        key="min_two_values",
        title=str(spec["title"]),
        story=str(spec["story"]),
        spec=spec,
        expected_redundant_pre=expected,
    )


def _scenario_normalize_minutes(rng: random.Random) -> _Scenario:
    in_name, out_name = rng.choice(
        [("minute_offset", "minute"), ("raw_minute", "normalized_minute")]
    )
    bound = rng.choice([120, 300, 720])
    spec: JsonObject = {
        "title": "Normalize minutes into a clock minute (0..59)",
        "story": (
            "Given a minute offset (possibly outside 0..59), normalize it to the "
            "equivalent clock minute."
        ),
        "category": "arithmetic/mod",
        "inputs": {in_name: {"min": -bound, "max": bound}},
        "step_limit": 50,
        "pre": [
            f"{in_name} >= {-bound}",
            f"{in_name} <= {bound}",
            f"{in_name} >= {-10000}",
            f"{in_name} <= {10000}",
        ],
        "post": [f"{out_name} >= 0 and {out_name} < 60"],
        "program": [{"assign": {out_name: f"{in_name} % 60"}}],
    }
    expected = [f"{in_name} >= {-10000}", f"{in_name} <= {10000}"]
    return _Scenario(
        key="normalize_minutes",
        title=str(spec["title"]),
        story=str(spec["story"]),
        spec=spec,
        expected_redundant_pre=expected,
    )


def _scenario_range_validator(rng: random.Random) -> _Scenario:
    value_name = rng.choice(["age", "score", "level"])
    flag_name = rng.choice(["is_valid", "ok", "valid"])
    lo, hi = rng.choice([(0, 120), (0, 100), (1, 10)])
    extra_lo, extra_hi = rng.choice([(-999, 999), (-100, 200), (-10, 300)])
    spec: JsonObject = {
        "title": f"Validate that `{value_name}` is within [{lo}, {hi}]",
        "story": (
            "Set a boolean-like flag for whether an input value falls in the "
            "acceptable range."
        ),
        "category": "validation/range",
        "inputs": {value_name: {"min": extra_lo, "max": extra_hi}},
        "step_limit": 100,
        "pre": [
            f"{value_name} >= {extra_lo}",
            f"{value_name} <= {extra_hi}",
            f"{value_name} >= {lo - 1000}",
            f"{value_name} <= {hi + 1000}",
        ],
        "post": [
            (
                f"({flag_name} == 1 and {value_name} >= {lo} and {value_name} <= {hi}) "
                f"or ({flag_name} == 0 and ({value_name} < {lo} or {value_name} > {hi}))"
            )
        ],
        "program": [
            {
                "if": {
                    "cond": f"{value_name} >= {lo} and {value_name} <= {hi}",
                    "then": [{"assign": {flag_name: "1"}}],
                    "else": [{"assign": {flag_name: "0"}}],
                }
            }
        ],
    }
    expected = [f"{value_name} >= {lo - 1000}", f"{value_name} <= {hi + 1000}"]
    return _Scenario(
        key="range_validator",
        title=str(spec["title"]),
        story=str(spec["story"]),
        spec=spec,
        expected_redundant_pre=expected,
    )


def _scenario_order_pair(rng: random.Random) -> _Scenario:
    start_name, end_name = rng.choice([("start", "end"), ("from_", "to")])
    lo_name, hi_name = rng.choice([("lo", "hi"), ("begin", "finish")])
    bound = rng.choice([20, 50, 100])
    spec: JsonObject = {
        "title": "Order a pair of bounds (swap if needed)",
        "story": (
            "Users may enter a range in any order. Normalize it so the output always "
            "satisfies lo <= hi."
        ),
        "category": "branch/swap",
        "inputs": {
            start_name: {"min": -bound, "max": bound},
            end_name: {"min": -bound, "max": bound},
        },
        "step_limit": 100,
        "pre": [
            f"{start_name} >= {-bound}",
            f"{end_name} >= {-bound}",
            f"{start_name} >= {-bound - 100}",
            f"{end_name} >= {-bound - 100}",
        ],
        "post": [
            (
                f"{lo_name} <= {hi_name} and ("
                f"({start_name} <= {end_name} and {lo_name} == {start_name} and "
                f"{hi_name} == {end_name}) or "
                f"({start_name} > {end_name} and {lo_name} == {end_name} and "
                f"{hi_name} == {start_name})"
                ")"
            )
        ],
        "program": [
            {
                "if": {
                    "cond": f"{start_name} <= {end_name}",
                    "then": [{"assign": {lo_name: start_name, hi_name: end_name}}],
                    "else": [{"assign": {lo_name: end_name, hi_name: start_name}}],
                }
            }
        ],
    }
    expected = [f"{start_name} >= {-bound - 100}", f"{end_name} >= {-bound - 100}"]
    return _Scenario(
        key="order_pair",
        title=str(spec["title"]),
        story=str(spec["story"]),
        spec=spec,
        expected_redundant_pre=expected,
    )


def _scenario_capped_increment(rng: random.Random) -> _Scenario:
    counter_name = rng.choice(["count", "counter", "retries"])
    out_name = rng.choice(["next", "new_count", "updated"])
    cap = rng.choice([3, 5, 10])
    spec: JsonObject = {
        "title": f"Capped increment (do not exceed {cap})",
        "story": (
            "Increment a counter only if it is below a fixed limit (e.g., max retry "
            "attempts)."
        ),
        "category": "branch/cap",
        "inputs": {counter_name: {"min": -2, "max": cap + 3}},
        "step_limit": 80,
        "pre": [
            f"{counter_name} >= 0",
            f"{counter_name} <= {cap + 3}",
            f"{counter_name} >= -100",
            f"{counter_name} <= {cap + 999}",
        ],
        "post": [
            (
                f"({counter_name} < {cap} and {out_name} == {counter_name} + 1) or "
                f"({counter_name} >= {cap} and {out_name} == {counter_name})"
            )
        ],
        "program": [
            {
                "if": {
                    "cond": f"{counter_name} < {cap}",
                    "then": [{"assign": {out_name: f"{counter_name} + 1"}}],
                    "else": [{"assign": {out_name: counter_name}}],
                }
            }
        ],
    }
    expected = [f"{counter_name} >= -100", f"{counter_name} <= {cap + 999}"]
    return _Scenario(
        key="capped_increment",
        title=str(spec["title"]),
        story=str(spec["story"]),
        spec=spec,
        expected_redundant_pre=expected,
    )


_SCENARIO_FACTORIES = [
    _scenario_clamp_temperature,
    _scenario_abs_delta,
    _scenario_remainder_by_subtraction,
    _scenario_sum_first_n,
    _scenario_min_two_values,
    _scenario_normalize_minutes,
    _scenario_range_validator,
    _scenario_order_pair,
    _scenario_capped_increment,
]


def _build_examples(*, count: int, seed: int) -> list[_Scenario]:
    rng = random.Random(seed)
    scenarios: list[_Scenario] = []
    for _ in range(count):
        factory = rng.choice(_SCENARIO_FACTORIES)
        scenarios.append(factory(rng))
    return scenarios


def main(argv: list[str]) -> None:
    del argv  # unused (absl handles flags)

    out_dir = Path(_FLAGS.out_dir)
    scenarios = _build_examples(count=int(_FLAGS.count), seed=int(_FLAGS.seed))

    for index, scenario in enumerate(scenarios, start=1):
        file_id = f"ex_{index:03d}"
        out_path = out_dir / f"{file_id}.json"
        if out_path.exists() and not _FLAGS.overwrite:
            continue

        spec = dict(scenario.spec)
        spec["id"] = file_id
        spec["expected_redundant_pre"] = list(scenario.expected_redundant_pre)
        _write_json(out_path, spec)
        if _FLAGS.validate:
            _validate_spec(spec)

    print(f"Wrote {len(scenarios)} examples to {out_dir}")


if __name__ == "__main__":
    app.run(main)
