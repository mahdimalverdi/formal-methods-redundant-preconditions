"""absl-based CLI entrypoint for the project.

This module wires command-line flags (via absl.flags) to the core analysis in
`fm_project.redundancy_checker`.
"""

from __future__ import annotations

import sys
from pathlib import Path

from absl import app, flags

from fm_project import redundancy_checker
from fm_project import simulation
from fm_project import group_redundancy


FLAGS = flags.FLAGS

flags.DEFINE_string(
    "spec",
    None,
    (
        "Path to spec JSON (e.g. examples/sub.json). "
        "If omitted, first positional arg is used."
    ),
)
flags.DEFINE_integer(
    "step_limit",
    None,
    "Optional override for step_limit in the spec file.",
)
flags.DEFINE_bool(
    "simulate",
    False,
    "Run the synthetic simulation benchmark instead of analyzing a spec.",
)
flags.DEFINE_integer("sim_n", 39, "Number of benchmark programs to simulate.")
flags.DEFINE_integer("sim_seed", 1, "Random seed for simulation benchmark.")
flags.DEFINE_bool(
    "group",
    False,
    "After analyzing a spec, also compute a bounded group-redundancy report.",
)


def main(argv: list[str]) -> None:
    """Runs bounded redundancy checks or the simulation benchmark."""
    if FLAGS.simulate:
        report = simulation.run_simulation(num_programs=FLAGS.sim_n, seed=FLAGS.sim_seed)
        simulation.write_outputs(
            report=report,
            json_path=Path("outputs/simulation_report.json"),
            text_path=Path("outputs/simulation_summary.txt"),
        )
        print("Wrote outputs/simulation_report.json and outputs/simulation_summary.txt")
        sys.exit(0)

    spec = FLAGS.spec
    if spec is None:
        if len(argv) < 2:
            raise app.UsageError(
                "Missing spec path. Provide --spec or a positional argument."
            )
        spec = argv[1]

    exit_code = redundancy_checker.analyze(
        Path(spec),
        step_limit_override=FLAGS.step_limit,
    )
    if exit_code == 0 and FLAGS.group:
        import json

        config = json.loads(Path(spec).read_text(encoding="utf-8"))
        program = config["program"]
        pre = list(config.get("pre", []))
        post = list(config.get("post", []))
        input_ranges = config["inputs"]
        step_limit = int(config.get("step_limit", 10000))
        if FLAGS.step_limit is not None:
            step_limit = int(FLAGS.step_limit)

        gr = group_redundancy.analyze_group_redundancy(
            program=program,
            pre=pre,
            post=post,
            input_ranges=input_ranges,
            step_limit=step_limit,
        )
        out = Path("outputs/group_redundancy_report.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(
                {
                    "single_redundant_indices": gr.single_redundant_indices,
                    "greedy_group_indices": gr.greedy_group_indices,
                    "all_single_is_group_redundant": gr.all_single_is_group_redundant,
                    "counterexample_if_not_group": gr.counterexample_if_not_group,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"Wrote {out}")
    sys.exit(exit_code)


if __name__ == "__main__":
    app.run(main)
