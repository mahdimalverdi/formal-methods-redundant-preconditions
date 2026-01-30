"""Simulation/benchmark generation for the bounded redundancy checker.

This module generates a synthetic benchmark inspired by the paper:
  "Detecting Redundant Preconditions" (Thoben, Wehrheim).

We create programs of the classic "Sub" shape where `N >= 0` is necessary for
the postcondition, then inject three kinds of redundant preconditions:
  - Independency: constrains an irrelevant input variable M
  - Implication: precondition implied by a stronger precondition
  - Range: a non-trivial upper bound that is unnecessary for correctness

We then compare three detectors (all bounded):
  - IC-like: checks whether a precondition is implied by the others
  - DC-like: syntactic dependency analysis from post vars through the program
  - VC (semantic): removes the precondition and re-checks the contract
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fm_project import redundancy_checker


@dataclass(frozen=True)
class SimulationCounts:
    """Counts of redundant preconditions (true vs detected)."""

    total_redundant: int
    detected_ic: int
    detected_dc: int
    detected_vc: int


def _sub_program() -> list[dict[str, Any]]:
    """Returns the toy program used across the benchmark."""
    return [
        {"assign": {"x": "0"}},
        {"assign": {"y": "N"}},
        {"assign": {"z": "M"}},
        {
            "while": {
                "cond": "x < N",
                "body": [
                    {"assign": {"x": "x + 1"}},
                    {"assign": {"y": "y - 1"}},
                    {"assign": {"z": "z - 1"}},
                ],
            }
        },
    ]


def _build_spec(*, n_min: int, n_max: int, m_min: int, m_max: int) -> dict[str, Any]:
    """Builds a JSON spec dictionary for the benchmark."""
    # Necessary: N >= 0 (otherwise, y stays N and y==0 can fail)
    # Redundant (implication): N >= n_min, implied by N >= 0 because n_min <= 0
    # Redundant (range): N <= n_max_redundant, unnecessary for post but non-trivial
    # Redundant (indep): M >= 0, irrelevant to y==0
    n_max_redundant = 3
    if n_max_redundant >= n_max:
        raise ValueError("n_max must be > 3 for non-trivial range precondition.")

    return {
        "inputs": {
            "N": {"min": n_min, "max": n_max},
            "M": {"min": m_min, "max": m_max},
        },
        "step_limit": 10000,
        "pre": [
            "N >= 0",  # necessary
            f"N >= {n_min}",  # implication redundant
            f"N <= {n_max_redundant}",  # range redundant
            "M >= 0",  # independency redundant
        ],
        "post": ["y == 0"],
        "program": _sub_program(),
    }


def _ic_like_detected(
    *,
    pre: list[str],
    input_ranges: dict[str, dict[str, int]],
) -> set[int]:
    detected: set[int] = set()
    for idx, p in enumerate(pre):
        others = [x for j, x in enumerate(pre) if j != idx]
        if redundancy_checker.implies_bounded(
            antecedent=others,
            consequent=p,
            input_ranges=input_ranges,
        ):
            detected.add(idx)
    return detected


def _assigned_vars(program: list[dict[str, Any]]) -> set[str]:
    assigned: set[str] = set()
    for stmt in program:
        if "assign" in stmt:
            assigned.update(stmt["assign"].keys())
        elif "while" in stmt:
            assigned |= _assigned_vars(stmt["while"].get("body", []))
        elif "if" in stmt:
            assigned |= _assigned_vars(stmt["if"].get("then", []))
            assigned |= _assigned_vars(stmt["if"].get("else", []))
    return assigned


def _dependency_sources_for_post(
    *,
    program: list[dict[str, Any]],
    post: list[str],
) -> set[str]:
    """Computes vars that syntactically influence vars in post (DC-like)."""
    post_vars: set[str] = set()
    for a in post:
        post_vars |= redundancy_checker.vars_in_expr(a)

    forward: dict[str, set[str]] = {}

    def add_edge(src: str, dst: str) -> None:
        forward.setdefault(src, set()).add(dst)

    def walk(block: list[dict[str, Any]]) -> None:
        for stmt in block:
            if "assign" in stmt:
                assigns = stmt["assign"]
                for dst, expr in assigns.items():
                    for src in redundancy_checker.vars_in_expr(str(expr)):
                        add_edge(src, dst)
            elif "while" in stmt:
                w = stmt["while"]
                cond_vars = redundancy_checker.vars_in_expr(str(w["cond"]))
                body = w.get("body", [])
                body_assigned = _assigned_vars(body)
                for cv in cond_vars:
                    for av in body_assigned:
                        add_edge(cv, av)
                walk(body)
            elif "if" in stmt:
                i = stmt["if"]
                cond_vars = redundancy_checker.vars_in_expr(str(i["cond"]))
                then = i.get("then", [])
                els = i.get("else", [])
                assigned = _assigned_vars(then) | _assigned_vars(els)
                for cv in cond_vars:
                    for av in assigned:
                        add_edge(cv, av)
                walk(then)
                walk(els)

    walk(program)

    # Reverse reachability from post vars.
    reverse: dict[str, set[str]] = {}
    for src, dsts in forward.items():
        for dst in dsts:
            reverse.setdefault(dst, set()).add(src)

    reachable: set[str] = set(post_vars)
    queue: list[str] = list(post_vars)
    while queue:
        v = queue.pop()
        for src in reverse.get(v, set()):
            if src not in reachable:
                reachable.add(src)
                queue.append(src)

    return reachable


def _dc_like_detected(
    *,
    program: list[dict[str, Any]],
    pre: list[str],
    post: list[str],
) -> set[int]:
    influencing_vars = _dependency_sources_for_post(program=program, post=post)
    detected: set[int] = set()
    for idx, p in enumerate(pre):
        if redundancy_checker.vars_in_expr(p).isdisjoint(influencing_vars):
            detected.add(idx)
    return detected


def _vc_detected(
    *,
    program: list[dict[str, Any]],
    pre: list[str],
    post: list[str],
    input_ranges: dict[str, dict[str, int]],
    step_limit: int,
) -> set[int]:
    detected: set[int] = set()
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
            detected.add(idx)
    return detected


def run_simulation(*, num_programs: int, seed: int) -> dict[str, Any]:
    """Runs the synthetic benchmark and returns a JSON-serializable report."""
    rng = random.Random(seed)

    totals = {
        "true": {"independency": 0, "implication": 0, "range": 0},
        "ic": {"independency": 0, "implication": 0, "range": 0},
        "dc": {"independency": 0, "implication": 0, "range": 0},
        "vc": {"independency": 0, "implication": 0, "range": 0},
    }

    for i in range(num_programs):
        # Keep implication condition implied by N >= 0 by choosing n_min <= 0.
        n_min = rng.choice([-5, -4, -3, -2, -1, 0])
        n_max = rng.choice([6, 7, 8, 9, 10])
        m_min = rng.choice([-5, -4, -3])
        m_max = rng.choice([3, 4, 5])

        spec = _build_spec(n_min=n_min, n_max=n_max, m_min=m_min, m_max=m_max)
        program = spec["program"]
        pre: list[str] = list(spec["pre"])
        post: list[str] = list(spec["post"])
        input_ranges: dict[str, dict[str, int]] = dict(spec["inputs"])
        step_limit = int(spec.get("step_limit", 10000))

        # Indices:
        # 0: necessary, 1: implication redundant, 2: range redundant, 3: independency redundant
        true_types = {1: "implication", 2: "range", 3: "independency"}
        for t in true_types.values():
            totals["true"][t] += 1

        ic = _ic_like_detected(pre=pre, input_ranges=input_ranges)
        dc = _dc_like_detected(program=program, pre=pre, post=post)
        vc = _vc_detected(
            program=program,
            pre=pre,
            post=post,
            input_ranges=input_ranges,
            step_limit=step_limit,
        )

        for idx, t in true_types.items():
            if idx in ic:
                totals["ic"][t] += 1
            if idx in dc:
                totals["dc"][t] += 1
            if idx in vc:
                totals["vc"][t] += 1

    return {
        "num_programs": num_programs,
        "seed": seed,
        "totals": totals,
    }


def write_outputs(
    *, report: dict[str, Any], json_path: Path, text_path: Path
) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    text_path.parent.mkdir(parents=True, exist_ok=True)

    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    t = report["totals"]
    lines = [
        f"Programs: {report['num_programs']}",
        f"Seed: {report['seed']}",
        "",
        "Detected redundant preconditions (count of true redundant of each type):",
        "",
        "type           true   IC-like   DC-like   VC(semantic)",
        f"independency   {t['true']['independency']:>4}   {t['ic']['independency']:>7}   {t['dc']['independency']:>7}   {t['vc']['independency']:>11}",
        f"implication    {t['true']['implication']:>4}   {t['ic']['implication']:>7}   {t['dc']['implication']:>7}   {t['vc']['implication']:>11}",
        f"range          {t['true']['range']:>4}   {t['ic']['range']:>7}   {t['dc']['range']:>7}   {t['vc']['range']:>11}",
        "",
        f"total          {sum(t['true'].values()):>4}   {sum(t['ic'].values()):>7}   {sum(t['dc'].values()):>7}   {sum(t['vc'].values()):>11}",
        "",
    ]
    text_path.write_text("\n".join(lines), encoding="utf-8")

