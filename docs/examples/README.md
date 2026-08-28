# Example artifacts from a frozen-fixture bake-off / research run.

These files are produced offline from `bakeoff/fixtures/v0` (no network, no
tokens). Re-run:

```bash
python3 bakeoff/run_bakeoff.py
python3 tmoe run-research --offline --out docs/examples/research_report.json
```

Then copy `bakeoff/results/summary.json` and the equity curves here if you
want to refresh the committed snapshot.

`bakeoff_report.md` is a human-readable interpretation. It does **not**
claim to beat ATD.
