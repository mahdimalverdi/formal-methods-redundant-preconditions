"""Bounded checker for redundant preconditions.

This is a small educational prototype inspired by:
  "Detecting Redundant Preconditions" (Thoben, Wehrheim).

It evaluates a tiny JSON-defined language by enumerating inputs in a bounded
domain, then checks which preconditions can be removed without violating the
postconditions (within that bounded domain).
"""

from __future__ import annotations

import ast
import itertools
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


class UnsafeExpressionError(ValueError):
    """Raised when the expression contains disallowed syntax."""


_ALLOWED_AST_NODES = (
    ast.Expression,
    ast.BoolOp,
    ast.BinOp,
    ast.UnaryOp,
    ast.Compare,
    ast.Name,
    ast.Constant,
    ast.Load,
    ast.And,
    ast.Or,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Mod,
    ast.USub,
    ast.UAdd,
    ast.Not,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
)


def _ensure_allowed_node(node: ast.AST) -> None:
    """Validates that an AST contains only safe/allowed nodes."""
    for sub in ast.walk(node):
        if not isinstance(sub, _ALLOWED_AST_NODES):
            raise UnsafeExpressionError(f"Disallowed syntax: {type(sub).__name__}")


def vars_in_expr(expr: str) -> set[str]:
    """Returns variable names referenced by an expression."""
    tree = ast.parse(expr, mode="eval")
    _ensure_allowed_node(tree)
    names: set[str] = set()
    for sub in ast.walk(tree):
        if isinstance(sub, ast.Name):
            names.add(sub.id)
    return names


def eval_expr(expr: str, env: dict[str, Any]) -> Any:
    """Safely evaluates a restricted expression over `env`."""
    tree = ast.parse(expr, mode="eval")
    _ensure_allowed_node(tree)

    def go(node: ast.AST) -> Any:
        match node:
            case ast.Expression(body=body):
                return go(body)
            case ast.Constant(value=value):
                return value
            case ast.Name(id=name):
                if name not in env:
                    raise KeyError(f"Unknown variable: {name}")
                return env[name]
            case ast.UnaryOp(op=op, operand=operand):
                value = go(operand)
                if isinstance(op, ast.Not):
                    return not bool(value)
                if isinstance(op, ast.USub):
                    return -value
                if isinstance(op, ast.UAdd):
                    return +value
                raise UnsafeExpressionError(f"Unsupported unary op: {type(op).__name__}")
            case ast.BinOp(left=left, op=op, right=right):
                a = go(left)
                b = go(right)
                if isinstance(op, ast.Add):
                    return a + b
                if isinstance(op, ast.Sub):
                    return a - b
                if isinstance(op, ast.Mult):
                    return a * b
                if isinstance(op, ast.Mod):
                    return a % b
                raise UnsafeExpressionError(f"Unsupported bin op: {type(op).__name__}")
            case ast.BoolOp(op=op, values=values):
                if isinstance(op, ast.And):
                    return all(bool(go(v)) for v in values)
                if isinstance(op, ast.Or):
                    return any(bool(go(v)) for v in values)
                raise UnsafeExpressionError(f"Unsupported bool op: {type(op).__name__}")
            case ast.Compare(left=left, ops=ops, comparators=comparators):
                current = go(left)
                for cmp_op, rhs_node in zip(ops, comparators, strict=True):
                    rhs = go(rhs_node)
                    ok: bool
                    if isinstance(cmp_op, ast.Eq):
                        ok = current == rhs
                    elif isinstance(cmp_op, ast.NotEq):
                        ok = current != rhs
                    elif isinstance(cmp_op, ast.Lt):
                        ok = current < rhs
                    elif isinstance(cmp_op, ast.LtE):
                        ok = current <= rhs
                    elif isinstance(cmp_op, ast.Gt):
                        ok = current > rhs
                    elif isinstance(cmp_op, ast.GtE):
                        ok = current >= rhs
                    else:
                        raise UnsafeExpressionError(
                            f"Unsupported compare op: {type(cmp_op).__name__}"
                        )
                    if not ok:
                        return False
                    current = rhs
                return True
            case _:
                raise UnsafeExpressionError(f"Unsupported node: {type(node).__name__}")

    return go(tree)


@dataclass(frozen=True)
class RunResult:
    """Summary of a bounded run over all enumerated inputs."""

    considered_inputs: int
    satisfying_pre: int
    violations: int
    nontermination: int


def _iter_inputs(input_ranges: dict[str, dict[str, int]]) -> Iterable[dict[str, int]]:
    """Generates all input environments from inclusive integer ranges."""
    names = sorted(input_ranges.keys())
    ranges = []
    for name in names:
        spec = input_ranges[name]
        lo = int(spec["min"])
        hi = int(spec["max"])
        if lo > hi:
            raise ValueError(f"Bad range for {name}: min > max")
        ranges.append(range(lo, hi + 1))
    for values in itertools.product(*ranges):
        yield dict(zip(names, values, strict=True))


def run_contract(
    *,
    program: list[dict[str, Any]],
    pre: list[str],
    post: list[str],
    input_ranges: dict[str, dict[str, int]],
    step_limit: int,
) -> RunResult:
    """Executes the program for all bounded inputs and checks the contract."""
    considered = 0
    sat_pre = 0
    violations = 0
    nonterm = 0

    def exec_block(block: list[dict[str, Any]], state: dict[str, Any]) -> int:
        """Executes a list of statements and returns step count."""
        steps = 0
        for stmt in block:
            if "assign" in stmt:
                assigns = stmt["assign"]
                if not isinstance(assigns, dict):
                    raise ValueError("assign must be an object")
                for name, expr in assigns.items():
                    state[name] = eval_expr(str(expr), state)
                    steps += 1
            elif "while" in stmt:
                w = stmt["while"]
                cond = str(w["cond"])
                body = w.get("body", [])
                if not isinstance(body, list):
                    raise ValueError("while.body must be a list")
                while bool(eval_expr(cond, state)):
                    steps += 1
                    steps += exec_block(body, state)
                    if steps > step_limit:
                        return steps
            elif "if" in stmt:
                i = stmt["if"]
                cond = str(i["cond"])
                then = i.get("then", [])
                els = i.get("else", [])
                if not isinstance(then, list) or not isinstance(els, list):
                    raise ValueError("if.then and if.else must be lists")
                steps += 1
                if bool(eval_expr(cond, state)):
                    steps += exec_block(then, state)
                else:
                    steps += exec_block(els, state)
            else:
                raise ValueError(f"Unknown statement: {stmt}")
            if steps > step_limit:
                return steps
        return steps

    for inp in _iter_inputs(input_ranges):
        considered += 1
        state: dict[str, Any] = dict(inp)
        try:
            if pre and not all(bool(eval_expr(p, state)) for p in pre):
                continue
            sat_pre += 1
            steps = exec_block(program, state)
            if steps > step_limit:
                nonterm += 1
                continue
            if post and not all(bool(eval_expr(a, state)) for a in post):
                violations += 1
        except (KeyError, UnsafeExpressionError, ValueError, ZeroDivisionError):
            violations += 1

    return RunResult(
        considered_inputs=considered,
        satisfying_pre=sat_pre,
        violations=violations,
        nontermination=nonterm,
    )


def find_counterexample(
    *,
    program: list[dict[str, Any]],
    pre: list[str],
    post: list[str],
    input_ranges: dict[str, dict[str, int]],
    step_limit: int,
) -> dict[str, int] | None:
    """Returns one bounded counterexample input if the contract fails.

    A counterexample is an input that satisfies the preconditions but either:
      - exceeds the step limit (nontermination), or
      - violates a postcondition at termination, or
      - triggers an evaluation/runtime error in this prototype.
    """

    def exec_block(block: list[dict[str, Any]], state: dict[str, Any]) -> int:
        steps = 0
        for stmt in block:
            if "assign" in stmt:
                assigns = stmt["assign"]
                if not isinstance(assigns, dict):
                    raise ValueError("assign must be an object")
                for name, expr in assigns.items():
                    state[name] = eval_expr(str(expr), state)
                    steps += 1
            elif "while" in stmt:
                w = stmt["while"]
                cond = str(w["cond"])
                body = w.get("body", [])
                if not isinstance(body, list):
                    raise ValueError("while.body must be a list")
                while bool(eval_expr(cond, state)):
                    steps += 1
                    steps += exec_block(body, state)
                    if steps > step_limit:
                        return steps
            elif "if" in stmt:
                i = stmt["if"]
                cond = str(i["cond"])
                then = i.get("then", [])
                els = i.get("else", [])
                if not isinstance(then, list) or not isinstance(els, list):
                    raise ValueError("if.then and if.else must be lists")
                steps += 1
                if bool(eval_expr(cond, state)):
                    steps += exec_block(then, state)
                else:
                    steps += exec_block(els, state)
            else:
                raise ValueError(f"Unknown statement: {stmt}")
            if steps > step_limit:
                return steps
        return steps

    for inp in _iter_inputs(input_ranges):
        state: dict[str, Any] = dict(inp)
        try:
            if pre and not all(bool(eval_expr(p, state)) for p in pre):
                continue
            steps = exec_block(program, state)
            if steps > step_limit:
                return inp
            if post and not all(bool(eval_expr(a, state)) for a in post):
                return inp
        except (KeyError, UnsafeExpressionError, ValueError, ZeroDivisionError):
            return inp

    return None


def _implies_bounded(
    *,
    antecedent: list[str],
    consequent: str,
    input_ranges: dict[str, dict[str, int]],
) -> bool:
    """Checks (bounded) whether antecedent implies consequent."""
    for inp in _iter_inputs(input_ranges):
        env: dict[str, Any] = dict(inp)
        if antecedent and not all(bool(eval_expr(p, env)) for p in antecedent):
            continue
        if not bool(eval_expr(consequent, env)):
            return False
    return True


def implies_bounded(
    *, antecedent: list[str], consequent: str, input_ranges: dict[str, dict[str, int]]
) -> bool:
    """Public wrapper for bounded implication checks (IC-like)."""
    return _implies_bounded(
        antecedent=antecedent,
        consequent=consequent,
        input_ranges=input_ranges,
    )


def _fmt_pct(n: int, d: int) -> str:
    """Formats n/d as a percentage with 2 decimal places."""
    if d <= 0:
        return "n/a"
    return f"{(100.0 * n / d):.2f}%"


def analyze(path: Path, *, step_limit_override: int | None = None) -> int:
    """Loads a JSON spec, runs checks, and prints a human-readable report."""
    if not path.exists():
        raise FileNotFoundError(path)

    config = json.loads(path.read_text(encoding="utf-8"))
    program = config["program"]
    pre = list(config.get("pre", []))
    post = list(config.get("post", []))
    input_ranges = config["inputs"]
    step_limit = int(config.get("step_limit", 10000))
    if step_limit_override is not None:
        step_limit = int(step_limit_override)

    base = run_contract(
        program=program,
        pre=pre,
        post=post,
        input_ranges=input_ranges,
        step_limit=step_limit,
    )

    print(f"Spec: {path}")
    print(f"Inputs considered: {base.considered_inputs}")
    pct = _fmt_pct(base.satisfying_pre, base.considered_inputs)
    print(f"Inputs satisfying pre: {base.satisfying_pre} ({pct})")
    print(f"Violations (bounded): {base.violations}")
    print(f"Nontermination (step_limit={step_limit}): {base.nontermination}")
    print("")

    if base.violations > 0:
        print("NOTE: Base contract has violations under this bounded domain.")
        print("")

    if pre:
        print("Single precondition redundancy (bounded verifier-based check):")
        redundant: list[int] = []
        for i, p in enumerate(pre, start=1):
            reduced_pre = [x for j, x in enumerate(pre, start=1) if j != i]
            rr = run_contract(
                program=program,
                pre=reduced_pre,
                post=post,
                input_ranges=input_ranges,
                step_limit=step_limit,
            )
            is_redundant = rr.violations == 0
            status = "REDUNDANT" if is_redundant else "NEEDED"
            print(f"- pre{i}: {status} | {p}")
            if is_redundant:
                redundant.append(i)
        if not redundant:
            print("- none")
        print("")

        print("Implication checking (bounded, IC-like):")
        for i, p in enumerate(pre, start=1):
            others = [x for j, x in enumerate(pre, start=1) if j != i]
            ok = _implies_bounded(
                antecedent=others,
                consequent=p,
                input_ranges=input_ranges,
            )
            status = "IMPLIED" if ok else "NOT implied"
            print(f"- pre{i}: {status} | {p}")
        print("")

    if post:
        print("Variable usage (syntactic):")
        pre_vars = sorted(set().union(*(vars_in_expr(p) for p in pre))) if pre else []
        post_vars = (
            sorted(set().union(*(vars_in_expr(a) for a in post))) if post else []
        )
        print(f"- vars(pre): {pre_vars}")
        print(f"- vars(post): {post_vars}")
        print("")

    return 0
