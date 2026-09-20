"""Run the full three-way benchmark (plus OCCAM) and write raw results."""
import argparse, time
from pathlib import Path
from occam import context
from occam.eval.harness import run_benchmark, consolidate, PIPELINES

ap = argparse.ArgumentParser()
ap.add_argument("--questions", default="eval_public.jsonl")
ap.add_argument("--out", default="artifacts/results_public.jsonl")
ap.add_argument("--limit", type=int, default=0)
ap.add_argument("--workers", type=int, default=6)
ap.add_argument("--rpm", type=int, default=300)
ap.add_argument("--pipelines", default=",".join(PIPELINES))
ap.add_argument("--resume", action="store_true",
                help="continue an interrupted run; off by default because a "
                     "checkpoint written by different code silently mixes versions")
args = ap.parse_args()

ctx = context.load()
qs = context.questions(args.questions)
if args.limit:
    qs = qs[:args.limit]
pipes = tuple(p.strip() for p in args.pipelines.split(",") if p.strip())
print(f"  running {len(qs)} questions x {len(pipes)} pipelines = {len(qs)*len(pipes)} runs")

t0 = time.time()
ck = Path(args.out + ".partial")
if not args.resume and ck.exists():
    ck.unlink()
scored = run_benchmark(qs, ctx.graph, ctx.index, ctx.llm,
                       pipelines=pipes, workers=args.workers, rpm=args.rpm,
                       checkpoint=ck, resume=args.resume)
path = consolidate(ck, args.out)
print(f"  wrote {path} in {time.time()-t0:.0f}s")
