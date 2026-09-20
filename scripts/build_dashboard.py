"""Render the metrics dashboard from the raw result files.

Writes two builds from one source: docs/index.html is the standalone page
GitHub Pages serves (GitHub will not render an .html file from the repo view,
so the dashboard needs a real URL), and the fragment is for hosts that supply
their own document skeleton.
"""
from occam.eval.dashboard import build
from occam.eval.report import load_rows, summary_text

PUB, HID = "artifacts/results_public.jsonl", "artifacts/results_hidden.jsonl"

page = build(PUB, HID, "docs/index.html")
print(f"  wrote {page} ({page.stat().st_size/1024:.0f} KB)  -> GitHub Pages entry point")
frag = build(PUB, HID, "artifacts/dashboard.fragment.html", fragment=True)
print(f"  wrote {frag} (embeddable variant)")
open("artifacts/summary.txt", "w").write(summary_text(load_rows(PUB)))
print("  wrote artifacts/summary.txt")
