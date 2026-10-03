/* Race: replays recorded pipeline traces side by side.
   render(t) is a pure function of time t (ms), so the live site drives it
   with requestAnimationFrame and the demo video drives it with its own clock. */
(function () {
  const PIPES = [
    { key: "rag", name: "RAG", color: "var(--c-rag)", blurb: "top-10 chunks → LLM" },
    { key: "graphrag", name: "GraphRAG", color: "var(--c-graphrag)", blurb: "one planning call → graph" },
    { key: "agentic", name: "Agentic GraphRAG", color: "var(--c-agentic)", blurb: "plan → observe → re-plan" },
    { key: "occam", name: "OCCAM", color: "var(--c-occam)", blurb: "cheapest tier that can answer" },
  ];
  const LABEL = {
    llm_plan: "LLM writes the query plan", llm_read: "LLM reads 10 retrieved chunks",
    llm_disambiguate: "LLM applies the question's constraint", rule_match: "rule matches the question shape (no LLM)",
    vector_similarity_search: "vector search over 18,762 chunks", graph_aggregation: "graph aggregation (in-database)",
    graph_traversal_prev_edition: "traverse PREV_EDITION edge", graph_vertex_lookup: "graph vertex lookup",
  };
  const fmt = (n) => Math.round(n).toLocaleString("en-US");
  const dur = (s) => (s.latency > 0 ? Math.min(3000, Math.max(700, s.latency * 1000)) : 420);

  function schedule(run) {
    let t = 0;
    const steps = run.steps.map((s) => { const d = dur(s); const o = { s, a: t, b: t + d }; t += d; return o; });
    return { steps, end: t, reveal: t + 250 };
  }

  const Race = {
    PIPES, fmt, data: null, q: null, plan: null, lanes: {}, total: 0,
    mount(root, data) { this.root = root; this.data = data; },
    setQuestion(i) {
      const q = (this.q = this.data.questions[i]);
      this.plan = {}; this.total = 0;
      this.root.innerHTML = "";
      PIPES.forEach((p) => {
        const run = q.runs[p.key]; const sc = (this.plan[p.key] = schedule(run));
        this.total = Math.max(this.total, sc.reveal);
        const el = document.createElement("div"); el.className = "lane"; el.style.setProperty("--lane", p.color);
        el.innerHTML = `<div class="lane-h"><span class="dot"></span><b>${p.name}</b><i>${p.blurb}</i></div>
          <div class="tok"><span class="n mono">0</span><small>tokens</small></div>
          <ol class="steps">${sc.steps.map((x) => `<li><span class="ic"></span><div><b>${LABEL[x.s.action] || x.s.action}</b>
            <small class="mono">${x.s.agent} · ${x.s.tokens ? fmt(x.s.tokens) + " tok" : "0 tok"}${x.s.outcome !== "ok" ? " · " + x.s.outcome : ""}</small></div></li>`).join("")}</ol>
          <div class="ans"><small>answer</small><div class="a"></div><div class="v"></div></div>`;
        this.root.appendChild(el);
        this.lanes[p.key] = {
          el, n: el.querySelector(".n"), lis: [...el.querySelectorAll("li")], a: el.querySelector(".a"), v: el.querySelector(".v"),
        };
      });
      this.total += 400;
      this.render(0);
    },
    render(t) {
      PIPES.forEach((p) => {
        const run = this.q.runs[p.key], sc = this.plan[p.key], L = this.lanes[p.key];
        let tok = 0;
        sc.steps.forEach((x, i) => {
          const li = L.lis[i];
          const state = t >= x.b ? "done" : t >= x.a ? "run" : "wait";
          if (li.dataset.s !== state) { li.dataset.s = state; li.className = state + (x.s.outcome !== "ok" ? " " + x.s.outcome : ""); }
          if (t >= x.b) tok += x.s.tokens; else if (t > x.a) tok += x.s.tokens * ((t - x.a) / (x.b - x.a));
        });
        L.n.textContent = fmt(tok);
        const shown = t >= sc.reveal;
        L.el.classList.toggle("final", shown);
        L.a.textContent = shown ? (run.answer == null ? "no answer — model said insufficient evidence" : run.answer) : "…";
        L.v.className = "v " + (shown ? (run.correct ? "ok" : "bad") : "");
        L.v.textContent = shown ? (run.correct ? "✓ correct" : "✗ wrong") : "";
      });
    },
  };
  window.Race = Race;
})();
