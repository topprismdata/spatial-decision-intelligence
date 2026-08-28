# Analysis utilities

These standalone scripts generate reports, inspect QA rules, and run the
cross-encoder rerank stage. They are kept separate from the production entry
point `run.py` and the reusable modules under `src/`.

Run them from the repository root or with a path such as
`python scripts/analysis/generate_dashboard.py`; each script resolves the
repository root before reading `data/` and writing `outputs/`.
