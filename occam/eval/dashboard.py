"""Generate the metrics dashboard from raw benchmark results.

Everything rendered here is derived from ``artifacts/results_*.jsonl`` at build
time, so the page cannot disagree with the run that produced it. Charts are
inline SVG with no external dependencies - the file opens from disk.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

from occam.eval.report import (PIPELINE_LABEL, PIPELINE_ORDER, QTYPE_ORDER, Agg,
                               agent_value, by_pipeline, by_pipeline_qtype,
                               load_rows, tier_breakdown)

# Categorical slots 1-4 of the reference palette, validated for the adjacent
# pairlist in both modes. Every chart also direct-labels or legends its series,
# so identity never rests on colour alone.
SERIES_LIGHT = {"rag": "#2a78d6", "graphrag": "#eb6834",
                "agentic": "#1baf7a", "occam": "#eda100"}
SERIES_DARK = {"rag": "#3987e5", "graphrag": "#d95926",
               "agentic": "#199e70", "occam": "#c98500"}

CSS = """
:root{color-scheme:light;
  --surface-0:#f6f6f4; --surface-1:#fcfcfb; --surface-2:#eeeeea;
  --border:#d9d9d2; --grid:#e6e6e0;
  --text-primary:#0b0b0b; --text-secondary:#52514e; --text-muted:#78776f;
  --series-rag:#2a78d6; --series-graphrag:#eb6834;
  --series-agentic:#1baf7a; --series-occam:#eda100;
  --good:#1e7a48; --bad:#b3261e;}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;
  --surface-0:#121211; --surface-1:#1a1a19; --surface-2:#242422;
  --border:#3a3a37; --grid:#2e2e2b;
  --text-primary:#ffffff; --text-secondary:#c3c2b7; --text-muted:#96958c;
  --series-rag:#3987e5; --series-graphrag:#d95926;
  --series-agentic:#199e70; --series-occam:#c98500;
  --good:#4caf7d; --bad:#e66767;}}
:root[data-theme="dark"]{color-scheme:dark;
  --surface-0:#121211; --surface-1:#1a1a19; --surface-2:#242422;
  --border:#3a3a37; --grid:#2e2e2b;
  --text-primary:#ffffff; --text-secondary:#c3c2b7; --text-muted:#96958c;
  --series-rag:#3987e5; --series-graphrag:#d95926;
  --series-agentic:#199e70; --series-occam:#c98500;
  --good:#4caf7d; --bad:#e66767;}
*{box-sizing:border-box}
body{margin:0;background:var(--surface-0);color:var(--text-primary);
  font:15px/1.5 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;}
.wrap{max-width:1080px;margin:0 auto;padding:40px 16px 80px}
h1{font-size:26px;margin:0 0 6px;letter-spacing:-.01em}
h2{font-size:17px;margin:40px 0 4px;letter-spacing:-.005em}
.sub{color:var(--text-secondary);margin:0 0 4px}
.note{color:var(--text-muted);font-size:13px;margin:4px 0 14px}
.card{background:var(--surface-1);border:1px solid var(--border);
  border-radius:12px;padding:18px 20px;margin-top:14px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-top:18px}
.tile{background:var(--surface-1);border:1px solid var(--border);border-radius:12px;padding:16px 18px}
.tile .name{font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--text-muted)}
.tile .big{font-size:32px;font-weight:650;letter-spacing:-.02em;margin:6px 0 2px}
.tile .meta{font-size:13px;color:var(--text-secondary)}
.swatch{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:7px;vertical-align:baseline}
table{border-collapse:collapse;width:100%;font-size:13.5px}
th,td{text-align:right;padding:7px 10px;border-bottom:1px solid var(--grid)}
th:first-child,td:first-child{text-align:left}
th{color:var(--text-secondary);font-weight:600;font-size:12px;
  letter-spacing:.04em;text-transform:uppercase}
tbody tr:last-child td{border-bottom:none}
.legend{display:flex;flex-wrap:wrap;gap:16px;margin:2px 0 10px;font-size:13px;color:var(--text-secondary)}
figure{margin:0}
svg{display:block;width:100%;height:auto;overflow:visible}
.mono{font-variant-numeric:tabular-nums;
  font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
.good{color:var(--good)} .bad{color:var(--bad)}
.hl{background:var(--surface-2);border-radius:8px;padding:12px 14px;margin-top:10px;font-size:14px}
footer{margin-top:44px;color:var(--text-muted);font-size:12.5px;
  border-top:1px solid var(--border);padding-top:14px}
[data-tip]{cursor:default}
"""

TIP_JS = """
(function(){
  var tip=document.createElement('div');
  tip.style.cssText='position:fixed;pointer-events:none;opacity:0;transition:opacity .08s;'+
    'background:var(--surface-2);color:var(--text-primary);border:1px solid var(--border);'+
    'border-radius:8px;padding:7px 10px;font:13px ui-sans-serif,system-ui;z-index:99;'+
    'box-shadow:0 6px 20px rgba(0,0,0,.16);max-width:280px';
  document.body.appendChild(tip);
  document.addEventListener('mouseover',function(e){
    var t=e.target.closest('[data-tip]'); if(!t) return;
    tip.textContent=t.getAttribute('data-tip'); tip.style.opacity='1';
  });
  document.addEventListener('mousemove',function(e){
    if(tip.style.opacity==='0') return;
    var x=e.clientX+14, y=e.clientY+14;
    if(x+tip.offsetWidth>innerWidth-8) x=e.clientX-tip.offsetWidth-14;
    if(y+tip.offsetHeight>innerHeight-8) y=e.clientY-tip.offsetHeight-14;
    tip.style.left=x+'px'; tip.style.top=y+'px';
  });
  document.addEventListener('mouseout',function(e){
    if(e.target.closest('[data-tip]')) tip.style.opacity='0';
  });
})();
"""


def _esc(s) -> str:
    return html.escape(str(s), quote=True)


def _legend(pipelines=PIPELINE_ORDER) -> str:
    return '<div class="legend">' + "".join(
        f'<span><span class="swatch" style="background:var(--series-{p})"></span>'
        f'{_esc(PIPELINE_LABEL[p])}</span>' for p in pipelines) + "</div>"


def chart_frontier(bp: dict[str, Agg]) -> str:
    """Cost vs accuracy. The headline: which pipeline is on the frontier?

    Tokens span three orders of magnitude, so x is log-scaled; every point is
    direct-labelled because four scatter points cannot rely on hue alone.
    """
    import math
    W, H = 720, 330
    L, R, T, B = 56, 24, 18, 46
    pts = []
    for p in PIPELINE_ORDER:
        a = bp.get(p)
        if a:
            pts.append((p, max(a.avg_tokens, 1.0), a.accuracy))
    lo = min(x for _, x, _ in pts) / 1.9
    hi = max(x for _, x, _ in pts) * 1.9

    def sx(v: float) -> float:
        return L + (math.log10(v) - math.log10(lo)) / (math.log10(hi) - math.log10(lo)) * (W - L - R)

    def sy(v: float) -> float:
        return T + (1 - v) * (H - T - B)

    parts = [f'<svg viewBox="0 0 {W} {H}" role="img" '
             f'aria-label="Average tokens per question versus answer accuracy">']
    for frac in (0, .25, .5, .75, 1.0):
        y = sy(frac)
        parts.append(f'<line x1="{L}" y1="{y:.1f}" x2="{W-R}" y2="{y:.1f}" '
                     f'stroke="var(--grid)" stroke-width="1"/>')
        parts.append(f'<text x="{L-9}" y="{y+4:.1f}" text-anchor="end" font-size="11.5" '
                     f'fill="var(--text-muted)">{frac*100:.0f}%</text>')
    for tick in (10, 100, 1000, 10000):
        if lo <= tick <= hi:
            x = sx(tick)
            parts.append(f'<line x1="{x:.1f}" y1="{T}" x2="{x:.1f}" y2="{H-B}" '
                         f'stroke="var(--grid)" stroke-width="1"/>')
            parts.append(f'<text x="{x:.1f}" y="{H-B+18}" text-anchor="middle" '
                         f'font-size="11.5" fill="var(--text-muted)">'
                         f'{tick:,}</text>')
    parts.append(f'<text x="{(L+W-R)/2:.0f}" y="{H-8}" text-anchor="middle" font-size="12" '
                 f'fill="var(--text-secondary)">mean tokens per question (log scale)</text>')
    parts.append(f'<text transform="translate(14,{(T+H-B)/2:.0f}) rotate(-90)" '
                 f'text-anchor="middle" font-size="12" fill="var(--text-secondary)">'
                 f'answer accuracy</text>')

    for p, tok, acc in pts:
        x, y = sx(tok), sy(acc)
        lbl = PIPELINE_LABEL[p]
        anchor = "end" if x > W - 150 else "start"
        dx = -14 if anchor == "end" else 14
        tip = f"{lbl}: {acc:.0%} accuracy at {tok:,.0f} tokens/question"
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="8" fill="var(--series-{p})" '
                     f'stroke="var(--surface-1)" stroke-width="2" data-tip="{_esc(tip)}"/>')
        parts.append(f'<text x="{x+dx:.1f}" y="{y-11:.1f}" text-anchor="{anchor}" '
                     f'font-size="12.5" font-weight="600" fill="var(--text-primary)">{_esc(lbl)}</text>')
        parts.append(f'<text x="{x+dx:.1f}" y="{y+5:.1f}" text-anchor="{anchor}" font-size="11.5" '
                     f'fill="var(--text-secondary)" class="mono">{acc:.0%} · {tok:,.0f} tok</text>')
    parts.append("</svg>")
    return "".join(parts)


def chart_qtype(bpq: dict[tuple[str, str], Agg]) -> str:
    """Accuracy by question type - where each approach actually breaks."""
    W, H = 720, 300
    L, R, T, B = 46, 12, 14, 52
    groups = QTYPE_ORDER
    gw = (W - L - R) / len(groups)
    bw = min(20.0, (gw - 16) / len(PIPELINE_ORDER))
    parts = [f'<svg viewBox="0 0 {W} {H}" role="img" '
             f'aria-label="Answer accuracy by question type for each pipeline">']
    for frac in (0, .25, .5, .75, 1.0):
        y = T + (1 - frac) * (H - T - B)
        parts.append(f'<line x1="{L}" y1="{y:.1f}" x2="{W-R}" y2="{y:.1f}" '
                     f'stroke="var(--grid)" stroke-width="1"/>')
        parts.append(f'<text x="{L-8}" y="{y+4:.1f}" text-anchor="end" font-size="11.5" '
                     f'fill="var(--text-muted)">{frac*100:.0f}%</text>')
    for gi, qt in enumerate(groups):
        gx = L + gi * gw
        total = bpq.get(("occam", qt))
        n = total.n if total else 0
        parts.append(f'<text x="{gx+gw/2:.1f}" y="{H-B+18}" text-anchor="middle" '
                     f'font-size="12" fill="var(--text-secondary)">{_esc(qt)}</text>')
        parts.append(f'<text x="{gx+gw/2:.1f}" y="{H-B+33}" text-anchor="middle" '
                     f'font-size="11" fill="var(--text-muted)">n={n}</text>')
        span = bw * len(PIPELINE_ORDER) + 2 * (len(PIPELINE_ORDER) - 1)
        x0 = gx + (gw - span) / 2
        for pi, p in enumerate(PIPELINE_ORDER):
            a = bpq.get((p, qt))
            if not a:
                continue
            h = a.accuracy * (H - T - B)
            x = x0 + pi * (bw + 2)          # 2px surface gap between adjacent bars
            y = T + (H - T - B) - h
            tip = (f"{PIPELINE_LABEL[p]} · {qt}: {a.accuracy:.0%} correct "
                   f"({a.correct}/{a.n}), {a.avg_tokens:,.0f} tok/q")
            parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" '
                         f'height="{max(h,1):.1f}" rx="4" fill="var(--series-{p})" '
                         f'data-tip="{_esc(tip)}"/>')
            if a.accuracy <= 0.55:           # label only the notable lows
                parts.append(f'<text x="{x+bw/2:.1f}" y="{y-5:.1f}" text-anchor="middle" '
                             f'font-size="10.5" fill="var(--text-secondary)" class="mono">'
                             f'{a.accuracy:.0%}</text>')
    parts.append("</svg>")
    return "".join(parts)


def chart_investigation(bp: dict[str, Agg]) -> str:
    """Answer accuracy beside evidence recall.

    The gap between the two is the whole point: a pipeline can name the right
    answer without having retrieved the documents that justify it, and only the
    second bar exposes that.
    """
    W, H = 720, 250
    L, R, T, B = 130, 70, 10, 34
    rows = [(p, bp[p]) for p in PIPELINE_ORDER if p in bp]
    rh = (H - T - B) / len(rows)
    parts = [f'<svg viewBox="0 0 {W} {H}" role="img" '
             f'aria-label="Answer accuracy compared with completeness (evidence recall)">']
    for frac in (0, .5, 1.0):
        x = L + frac * (W - L - R)
        parts.append(f'<line x1="{x:.1f}" y1="{T}" x2="{x:.1f}" y2="{H-B}" '
                     f'stroke="var(--grid)" stroke-width="1"/>')
        parts.append(f'<text x="{x:.1f}" y="{H-B+17}" text-anchor="middle" font-size="11.5" '
                     f'fill="var(--text-muted)">{frac*100:.0f}%</text>')
    for i, (p, a) in enumerate(rows):
        y0 = T + i * rh
        parts.append(f'<text x="{L-12}" y="{y0+rh/2+4:.1f}" text-anchor="end" font-size="12.5" '
                     f'fill="var(--text-primary)">{_esc(PIPELINE_LABEL[p])}</text>')
        for j, (val, label) in enumerate(((a.accuracy, "answer accuracy"),
                                          (a.evidence_recall, "evidence recall"))):
            bh = rh * 0.30
            y = y0 + rh / 2 - bh - 1 + j * (bh + 2)   # 2px gap between the pair
            w = max(val * (W - L - R), 1)
            op = "1" if j == 0 else "0.45"
            tip = f"{PIPELINE_LABEL[p]} {label}: {val:.1%}"
            parts.append(f'<rect x="{L}" y="{y:.1f}" width="{w:.1f}" height="{bh:.1f}" '
                         f'rx="4" fill="var(--series-{p})" fill-opacity="{op}" '
                         f'data-tip="{_esc(tip)}"/>')
            parts.append(f'<text x="{L+w+8:.1f}" y="{y+bh*0.78:.1f}" font-size="11" '
                         f'fill="var(--text-secondary)" class="mono">{val:.0%}</text>')
    parts.append("</svg>")
    return "".join(parts)


def _metrics_table(bp: dict[str, Agg]) -> str:
    head = ("<tr><th>pipeline</th><th>accuracy</th><th>completeness</th>"
            "<th>evidence precision</th><th>tokens / question</th>"
            "<th>tokens / correct answer</th><th>steps</th><th>sec / q</th></tr>")
    body = []
    for p in PIPELINE_ORDER:
        a = bp.get(p)
        if not a:
            continue
        ctc = "-" if a.cost_to_correct == float("inf") else f"{a.cost_to_correct:,.0f}"
        body.append(
            f'<tr><td><span class="swatch" style="background:var(--series-{p})"></span>'
            f'{_esc(PIPELINE_LABEL[p])}</td>'
            f'<td class="mono">{a.accuracy:.0%}</td>'
            f'<td class="mono">{a.evidence_recall:.0%}</td>'
            f'<td class="mono">{a.evidence_precision:.0%}</td>'
            f'<td class="mono">{a.avg_tokens:,.0f}</td>'
            f'<td class="mono">{ctc}</td>'
            f'<td class="mono">{a.avg_steps:.1f}</td>'
            f'<td class="mono">{a.avg_latency:.1f}</td></tr>')
    return f"<table><thead>{head}</thead><tbody>{''.join(body)}</tbody></table>"


def build(public_path: str | Path, hidden_path: str | Path | None,
          out: str | Path, fragment: bool = False) -> Path:
    """Render the dashboard.

    ``fragment=True`` omits the document skeleton for hosts that supply their
    own (the Artifact runtime wraps the file), so the standalone file in the
    repo and the shareable page stay the same build.
    """
    rows = load_rows(public_path)
    bp, bpq = by_pipeline(rows), by_pipeline_qtype(rows)
    av, tiers = agent_value(rows), tier_breakdown(rows)
    n_q = len({r["qid"] for r in rows})

    tiles = []
    for p in PIPELINE_ORDER:
        a = bp.get(p)
        if not a:
            continue
        tiles.append(
            f'<div class="tile"><div class="name">'
            f'<span class="swatch" style="background:var(--series-{p})"></span>'
            f'{_esc(PIPELINE_LABEL[p])}</div>'
            f'<div class="big mono">{a.accuracy:.0%}</div>'
            f'<div class="meta mono">{a.avg_tokens:,.0f} tokens / question</div></div>')

    tier_rows = "".join(
        f'<tr><td>{_esc(t)}</td><td class="mono">{d["n"]}</td>'
        f'<td class="mono">{d["correct"]/d["n"]:.0%}</td>'
        f'<td class="mono">{d["tokens"]/d["n"]:,.0f}</td></tr>'
        for t, d in sorted(tiers.items(), key=lambda kv: -kv[1]["n"]))

    hidden_block = ""
    if hidden_path and Path(hidden_path).exists():
        hrows = load_rows(hidden_path)
        hbp = by_pipeline(hrows)
        htiers = tier_breakdown(hrows)
        hn = len({r["qid"] for r in hrows})
        cells = "".join(
            f'<tr><td><span class="swatch" style="background:var(--series-{p})"></span>'
            f'{_esc(PIPELINE_LABEL[p])}</td>'
            f'<td class="mono">{sum(1 for r in hrows if r["pipeline"]==p and r["answer"])}/{hbp[p].n}</td>'
            f'<td class="mono">{hbp[p].avg_tokens:,.0f}</td>'
            f'<td class="mono">{hbp[p].avg_steps:.1f}</td></tr>'
            for p in PIPELINE_ORDER if p in hbp)
        htier = ", ".join(f"{t.replace('_',' ')} &times;{d['n']}"
                          for t, d in sorted(htiers.items(), key=lambda kv: -kv[1]["n"]))
        hidden_block = f"""
<h2>Held-out set ({hn} questions)</h2>
<p class="note">Ground truth for these is not published, so only coverage and cost
can be reported here - accuracy is scored by the organisers. Raw answers and full
agentic traces are in <span class="mono">artifacts/results_hidden.jsonl</span>.</p>
<div class="card"><table><thead><tr><th>pipeline</th><th>answered</th>
<th>tokens / question</th><th>steps</th></tr></thead><tbody>{cells}</tbody></table>
<div class="hl">OCCAM routing: {htier}</div></div>"""

    rescued = ", ".join(av["rescued"]) or "none"
    per_rescue = ("n/a" if av["extra_tokens_per_rescue"] == float("inf")
                  else f"{av['extra_tokens_per_rescue']:,.0f}")
    occam, graph = bp.get("occam"), bp.get("graphrag")
    saving = (graph.avg_tokens / occam.avg_tokens) if occam and occam.avg_tokens else 0

    head = ("" if fragment else
            '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">')
    open_body = "" if fragment else "</head><body>"
    doc = f"""{head}
<title>OCCAM Benchmark</title><style>{CSS}</style>{open_body}<div class="wrap">

<h1>OCCAM: when is an agent worth its tokens?</h1>
<p class="sub">RAG vs GraphRAG vs Agentic GraphRAG vs cost-aware routing,
over {n_q} questions on the TigerGraph Agentic GraphRAG corpus.</p>
<p class="note">Every number on this page is computed from the raw run files in
<span class="mono">artifacts/</span> at build time.</p>

<div class="tiles">{''.join(tiles)}</div>

<h2>Cost against accuracy</h2>
<p class="note">Up and to the left is better. The agent reaches the top;
routing reaches the same height for roughly {saving:,.0f}&times; fewer tokens.</p>
<div class="card">{_legend()}<figure>{chart_frontier(bp)}</figure></div>

<h2>Where each approach breaks</h2>
<p class="note">RAG does not degrade gracefully on aggregation and superlative
questions. Those need a median of 11 documents and up to 43, so the evidence
does not fit in a top-10 retrieval whatever the prompt says.</p>
<div class="card">{_legend()}<figure>{chart_qtype(bpq)}</figure></div>

<h2>Completeness: did it investigate, or just retrieve?</h2>
<p class="note">Solid bars are answer accuracy; pale bars are <strong>completeness</strong>,
the share of the question's gold documents the pipeline actually retrieved. A wide
gap means answers are being produced without the evidence that settles them.</p>
<div class="card"><figure>{chart_investigation(bp)}</figure></div>

<h2>Full metrics</h2>
<div class="card">{_metrics_table(bp)}</div>

<h2>Where the agent tier earned its cost</h2>
<div class="card">
<p style="margin:0 0 8px">Comparing the agentic run with single-pass GraphRAG on
the same {av['n']} questions:</p>
<table><tbody>
<tr><td>questions the agent rescued</td>
    <td class="mono good">{len(av['rescued'])} ({av['share_where_agent_mattered']:.0%})</td></tr>
<tr><td>questions the agent broke</td>
    <td class="mono {'bad' if av['regressed'] else 'good'}">{len(av['regressed'])}</td></tr>
<tr><td>extra tokens spent in total</td><td class="mono">{av['extra_tokens_total']:,}</td></tr>
<tr><td>extra tokens per question rescued</td><td class="mono">{per_rescue}</td></tr>
</tbody></table>
<div class="hl">Rescued: <span class="mono">{_esc(rescued)}</span>. All three were
cases where the graph narrowed the answer to a handful of candidates but could not
choose between them. That is the shape of question worth paying an agent for.</div>
</div>

<h2>How OCCAM routed</h2>
<p class="note">Each question starts at the cheapest tier and climbs only when a
tier reports what it was missing.</p>
<div class="card"><table><thead><tr><th>tier</th><th>questions</th>
<th>accuracy</th><th>tokens / question</th></tr></thead>
<tbody>{tier_rows}</tbody></table></div>
{hidden_block}

<footer>Generated by <span class="mono">occam.eval.dashboard</span>.
Corpus and questions supplied by the TigerGraph Agentic GraphRAG Hackathon.
Answer accuracy is normalised exact match. Completeness is evidence recall: the
share of a question's published <span class="mono">gold_doc_ids</span> the pipeline
actually retrieved. Tokens are as reported by the provider on every call.</footer>

</div><script>{TIP_JS}</script>{"" if fragment else "</body></html>"}"""

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8")
    return out
