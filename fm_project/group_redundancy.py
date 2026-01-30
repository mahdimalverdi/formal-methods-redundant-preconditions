"""Group redundancy analysis for bounded contracts.

This module adds a presentation-friendly 'new contribution' on top of the paper:
we explicitly analyze *group redundancy* in a bounded setting and produce a
concrete counterexample when single-redundant preconditions are not
group-redundant together.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fm_project import redundancy_checker


@dataclass(frozen=True)
class GroupRedundancyReport:
    """Results for single vs. group redundancy."""

    single_redundant_indices: list[int]
    greedy_group_indices: list[int]
    all_single_is_group_redundant: bool
    counterexample_if_not_group: dict[str, int] | None


def _holds(
    *,
    program: list[dict[str, Any]],
    pre: list[str],
    post: list[str],
    input_ranges: dict[str, dict[str, int]],
    step_limit: int,
) -> bool:
    rr = redundancy_checker.run_contract(
        program=program,
        pre=pre,
        post=post,
        input_ranges=input_ranges,
        step_limit=step_limit,
    )
    return rr.violations == 0 and rr.nontermination == 0


def analyze_group_redundancy(
    *,
    program: list[dict[str, Any]],
    pre: list[str],
    post: list[str],
    input_ranges: dict[str, dict[str, int]],
    step_limit: int,
) -> GroupRedundancyReport:
    """Computes single redundancy and a greedy group-redundant set."""
    single: list[int] = []
    for i in range(len(pre)):
        reduced = [p for j, p in enumerate(pre) if j != i]
        if _holds(
            program=program,
            pre=reduced,
            post=post,
            input_ranges=input_ranges,
            step_limit=step_limit,
        ):
            single.append(i)

    # Greedy maximal removable set (a group that can be removed together).
    remaining = list(range(len(pre)))
    removed: list[int] = []
    changed = True
    while changed:
        changed = False
        for i in list(remaining):
            trial = [pre[j] for j in remaining if j != i]
            if _holds(
                program=program,
                pre=trial,
                post=post,
                input_ranges=input_ranges,
                step_limit=step_limit,
            ):
                remaining.remove(i)
                removed.append(i)
                changed = True

    all_single_removed = [pre[i] for i in range(len(pre)) if i not in single]
    all_single_is_group = _holds(
        program=program,
        pre=all_single_removed,
        post=post,
        input_ranges=input_ranges,
        step_limit=step_limit,
    )

    counterexample = None
    if single and not all_single_is_group:
        counterexample = redundancy_checker.find_counterexample(
            program=program,
            pre=all_single_removed,
            post=post,
            input_ranges=input_ranges,
            step_limit=step_limit,
        )

    return GroupRedundancyReport(
        single_redundant_indices=single,
        greedy_group_indices=sorted(removed),
        all_single_is_group_redundant=all_single_is_group,
        counterexample_if_not_group=counterexample,
    )

