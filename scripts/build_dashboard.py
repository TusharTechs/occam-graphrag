"""Render the metrics dashboard from the raw result files."""
from occam.eval.dashboard import build
from occam.eval.report import load_rows, summary_text

PUB, HID = "artifacts/results_public.jsonl", "artifacts/results_hidden.jsonl"
out = build(PUB, HID, "artifacts/dashboard.html")
print(f"  wrote {out} ({out.stat().st_size/1024:.0f} KB)")
frag = build(PUB, HID, "artifacts/dashboard.fragment.html", fragment=True)
print(f"  wrote {frag} (shareable variant)")
open("artifacts/summary.txt", "w").write(summary_text(load_rows(PUB)))
print("  wrote artifacts/summary.txt")
