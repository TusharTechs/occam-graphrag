// Render the demo video: drive video/index.html's seek(t) in headless Chrome over CDP.
//   node render.mjs still 12.5 40 ...      -> build/still_<t>.png
//   node render.mjs frames [workers] [fps] -> build/frames/*.jpg
import { spawn } from "node:child_process";
import fs from "node:fs";
const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const PORT = 9333, URL = "http://localhost:8766/video/index.html";
const [mode, ...rest] = process.argv.slice(2);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const chrome = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${PORT}`, "--hide-scrollbars", "--force-device-scale-factor=1",
  "--window-size=1920,1080", "--user-data-dir=/tmp/occam-chrome-prof", "--no-first-run", "--disable-gpu-vsync", "about:blank"], { stdio: "ignore" });
process.on("exit", () => chrome.kill());
async function newPage() {
  for (let i = 0; i < 50; i++) { try { const r = await fetch(`http://localhost:${PORT}/json/new?${URL}`, { method: "PUT" }); return await r.json(); } catch { await sleep(300); } }
  throw new Error("chrome not up");
}
async function connect() {
  const t = await newPage(); const ws = new WebSocket(t.webSocketDebuggerUrl); await new Promise((r) => (ws.onopen = r));
  let id = 0; const pend = new Map();
  ws.onmessage = (m) => { const d = JSON.parse(m.data); if (d.id && pend.has(d.id)) { pend.get(d.id)(d); pend.delete(d.id); } };
  const send = (method, params = {}) => new Promise((res, rej) => { const i = ++id; pend.set(i, (d) => (d.error ? rej(new Error(JSON.stringify(d.error))) : res(d.result))); ws.send(JSON.stringify({ id: i, method, params })); });
  await send("Emulation.setDeviceMetricsOverride", { width: 1920, height: 1080, deviceScaleFactor: 1, mobile: false });
  for (let i = 0; i < 100; i++) { const r = await send("Runtime.evaluate", { expression: "window.ready===true" }); if (r.result.value) break; await sleep(200); }
  return { send, ws };
}
const shot = async (p, t, fmt) => { await p.send("Runtime.evaluate", { expression: `seek(${t})` }); await sleep(30);
  const r = await p.send("Page.captureScreenshot", fmt === "png" ? { format: "png" } : { format: "jpeg", quality: 90 }); return Buffer.from(r.data, "base64"); };
if (mode === "still") {
  const p = await connect(); for (const t of rest) { fs.writeFileSync(`build/still_${t}.png`, await shot(p, +t, "png")); console.log("still", t); }
} else {
  const W = +rest[0] || 4, FPS = +rest[1] || 25; const TL = JSON.parse(fs.readFileSync("timeline.json")); const N = Math.ceil(TL.total * FPS);
  fs.mkdirSync("build/frames", { recursive: true }); let done = 0; const t0 = Date.now();
  const pages = await Promise.all(Array.from({ length: W }, connect));
  await Promise.all(pages.map(async (p, w) => { for (let f = w; f < N; f += W) {
    const fn = `build/frames/${String(f).padStart(6, "0")}.jpg`; if (fs.existsSync(fn)) { done++; continue; }
    fs.writeFileSync(fn, await shot(p, f / FPS, "jpg")); if (++done % 200 === 0) console.log(`${done}/${N} ${((Date.now() - t0) / 1000) | 0}s`); } }));
  console.log("frames done", N);
}
process.exit(0);
