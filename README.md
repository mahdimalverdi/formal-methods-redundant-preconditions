# Formal Methods Project — Redundant Preconditions

This repository is a small educational project inspired by the paper:
**“Detecting Redundant Preconditions”** (Nicola Thoben, Heike Wehrheim, FormaliSE 2025).

It contains:
- A bounded checker for redundant preconditions (toy JSON language).
- A synthetic simulation benchmark (IC-like / DC-like / VC).
- A **novelty for presentation**: *group redundancy analysis with an explicit counterexample input* when single-redundant preconditions are **not** group-redundant.
- A Persian RTL LaTeX report using the Vazir family font.

## Quickstart (code)

Create a virtualenv and install dependencies:
```bash
python3.12 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

Run the basic example:
```bash
.venv/bin/python main.py --spec examples/sub.json
```

Run the “range redundancy” example:
```bash
.venv/bin/python main.py --spec examples/range_redundancy.json
```

Run the simulation benchmark (writes to `outputs/`):
```bash
.venv/bin/python main.py --simulate --sim_n=39 --sim_seed=1
```

Run group-redundancy analysis (writes `outputs/group_redundancy_report.json`):
```bash
.venv/bin/python main.py --spec examples/group_redundancy.json --group
```

## Example set (100 realistic specs)

Generate a human-like set of diverse examples under `examples/generated/`:
```bash
.venv/bin/python -m tools.generate_examples --count 100 --seed 7 --out_dir examples/generated --validate --overwrite
```

Summarize the generated suite (writes to `outputs/`):
```bash
.venv/bin/python -m tools.summarize_generated_examples
```

## LaTeX report (RTL + Vazir)

The report source is:
- `docs/final_report.tex`

Install Vazir family fonts locally into `fonts/`:
```bash
.venv/bin/python tools/install_vazir.py
```

Install a local `tectonic` binary under `tools/bin/`:
```bash
.venv/bin/python tools/install_tectonic.py
```

Build the PDF:
```bash
tools/bin/tectonic -X compile --synctex --outdir docs docs/final_report.tex
```

## Submission ZIP

Create the course submission zip:
```bash
.venv/bin/python make_submission_zip.py MahdiMalverdi 404443150
```

Note: the submission zip expects the paper/slides PDFs to exist under `docs/papers/`.
Those are not committed to GitHub.

## Template attribution

See `docs/template_attribution.md`.
