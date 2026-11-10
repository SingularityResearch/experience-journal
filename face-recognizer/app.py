"""
app.py - Face Recognizer: the live tracker and the labeling tool in one window, as two tabs.

The two stay separate programs inside: each keeps its own web server (tracker.py on 8766,
label_tool.py on 8765) and page, exactly as when started from recognize.bat / label.bat, and this
window shows both pages, one per tab. The tracker keeps running while the Labeling tab is shown.
If either is already running from its .bat, that copy is used instead of starting a second one.

Run:  python app.py            (or FaceRecognizer.exe, built with build_app.bat)
Needs pywebview (pip install pywebview); the window is Edge WebView2, part of Windows 11.
"""
import http.server
import json
import os
import re
import sys
import threading
import time
import traceback
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

import localguard

TITLE = "Face Recognizer"
VERSION = "1.7"                                    # this build; GitHub release tags are "v" + VERSION
REPO = "SingularityResearch/facial-recognition"
HOME = Path(os.environ.get("APPDATA", Path.home())) / "FaceLabels"   # private: outside the published project

SHELL = r"""<!doctype html><html><head><meta charset="utf-8"><title>Face Recognizer</title><style>
:root { color-scheme: dark; }
html, body { margin: 0; height: 100%; background: #0d1512; color: #dfe8e4; font: 14px "Segoe UI", system-ui, sans-serif; }
body { display: flex; flex-direction: column; }
nav { display: flex; gap: 4px; padding: 6px 10px 0; background: #111c18; border-bottom: 1px solid #24342e; }
nav button { font: inherit; color: #9fb2ab; background: none; border: 1px solid transparent; border-bottom: none;
  border-radius: 8px 8px 0 0; padding: 8px 18px; cursor: pointer; }
nav button:hover { color: #dfe8e4; }
nav button[aria-selected="true"] { color: #dfe8e4; background: #0d1512; border-color: #24342e; margin-bottom: -1px; }
nav small { margin-left: 8px; color: #6f827b; }
nav .ver { margin-left: auto; align-self: center; padding-bottom: 6px; color: #6f827b; font-size: 12px; }
nav .ver button { font: inherit; color: #9fb2ab; background: none; border: 0; padding: 0 0 0 8px; cursor: pointer; text-decoration: underline; }
main { flex: 1; position: relative; }
iframe { position: absolute; inset: 0; width: 100%; height: 100%; border: 0; visibility: hidden; }
iframe.on { visibility: visible; }
.wait { position: absolute; inset: 0; display: grid; place-content: center; color: #9fb2ab; }
.wait.err { color: #f0a08f; white-space: pre-wrap; padding: 24px; }
#settings { position: absolute; inset: 0; overflow: auto; padding: 18px 24px 40px; }
#settings[hidden] { display: none; }
.sets, #sec-programs { max-width: 860px; margin: 0 auto; display: grid; gap: 14px; }
#sec-programs { width: 100%; }
.sets h1 { font-size: 18px; font-weight: 600; margin: 0 0 2px; }
.sets > p { margin: 0; color: #9fb2ab; }
.sec { border: 1px solid #24342e; border-radius: 10px; background: #111c18; padding: 4px 16px 10px; }
.sec h2 { display: flex; align-items: center; gap: 10px; font-size: 14px; font-weight: 600; margin: 10px 0 4px; }
.sec h2 button { margin-left: auto; }
.sec .note { color: #9fb2ab; margin: 6px 0; }
.row { display: grid; grid-template-columns: minmax(180px, 1fr) minmax(220px, 1.3fr); gap: 4px 18px; align-items: center;
  padding: 9px 0; border-top: 1px solid #1b2924; }
.row:first-of-type { border-top: 0; }
.row[hidden] { display: none; }
.row > label, .row > .lab { color: #dfe8e4; }
.row .hint { grid-column: 1 / -1; color: #7f938c; font-size: 12.5px; line-height: 1.45; }
.row .ctl { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.row .info { white-space: pre-wrap; color: #b7c7c1; }
.row.off { opacity: .55; }
.sets input[type=text], .sets input[type=password], .sets select { font: inherit; color: #dfe8e4; background: #0d1512;
  border: 1px solid #2c3f38; border-radius: 7px; padding: 5px 8px; min-width: 0; flex: 1; }
.sets input[type=range] { flex: 1; accent-color: #4fc3a1; }
.sets input[type=checkbox] { width: 18px; height: 18px; accent-color: #4fc3a1; }
.sets output { min-width: 3.2em; text-align: right; color: #9fb2ab; font-variant-numeric: tabular-nums; }
.sets button.b { font: inherit; font-size: 13px; color: #dfe8e4; background: #18332a; border: 1px solid #2f5a4b; border-radius: 7px;
  padding: 5px 12px; cursor: pointer; }
.sets button.b:hover { background: #1f4236; }
.sets button.b:disabled { opacity: .5; cursor: default; }
.sets .msg { color: #9fb2ab; font-size: 12.5px; }
.sets .msg.err { color: #f0a08f; }
.sets code { color: #b7c7c1; }
.multi { display: grid; gap: 6px; flex: 1; min-width: 0; }
.multi .box { max-height: 240px; overflow: auto; border: 1px solid #2c3f38; border-radius: 7px; background: #0d1512; padding: 4px; }
.multi .box label { display: flex; gap: 8px; align-items: center; padding: 3px 6px; border-radius: 5px; cursor: pointer; }
.multi .box label:hover { background: #15241f; }
.multi .box label[hidden] { display: none; }
.multi .box .none { color: #7f938c; padding: 3px 6px; }
.multi .box label.sel { color: #fff; }
.multi .top { display: flex; gap: 8px; align-items: center; }
@media (max-width: 700px) { .row { grid-template-columns: 1fr; } }
</style></head><body>
<nav role="tablist">
  <button role="tab" id="tab-track" aria-selected="true" onclick="show('track')">Face tracking<small id="st-track">starting…</small></button>
  <button role="tab" id="tab-label" aria-selected="false" onclick="show('label')">Labeling<small id="st-label">starting…</small></button>
  <button role="tab" id="tab-set" aria-selected="false" onclick="show('set')">Settings</button>
  <span class="ver"><span id="ver">vVERSION</span><button id="upd" onclick="checkUpdate()" title="Asks GitHub for the latest release (only when you click)">Check for updates</button></span>
</nav>
<main>
  <div class="wait" id="wait">Loading the face models…</div>
  <!-- visibility, not display:none, so the hidden tab keeps tracking and collecting faces -->
  <iframe id="f-track" title="Face tracking" allow="camera; microphone; autoplay; fullscreen"></iframe>
  <iframe id="f-label" title="Labeling" allow="clipboard-read; clipboard-write; fullscreen"></iframe>
  <div id="settings" hidden><div class="sets" id="sets">
    <div><h1>Settings</h1><p>Everything you can set in the app, in one place. Changes apply at once and are remembered;
      the same options stay on the Face tracking and Labeling tabs too.</p></div>
    <section class="sec" id="sec-app"><h2>App</h2>
      <div class="row"><span class="lab">Version</span><div class="ctl"><span>vVERSION</span>
        <button class="b" id="upd2" onclick="checkUpdate()">Check for updates</button></div>
        <div class="hint">Asks GitHub for the latest release, only when you click.</div></div>
      <div class="row"><span class="lab">Faces, names and labels</span><div class="ctl"><code id="p-data">data</code>
        <button class="b" onclick="openDir('data')">Open folder</button></div>
        <div class="hint">The <code>data</code> folder beside the app. It stays on this computer; keep it out of any public repository.</div></div>
      <div class="row"><span class="lab">Keys, descriptions, snapshots, log</span><div class="ctl"><code id="p-private">%APPDATA%</code>
        <button class="b" onclick="openDir('private')">Open folder</button></div>
        <div class="hint">Web search keys, photo descriptions, webcam snapshots, the presence log and this app's messages (app.log).</div></div>
      <div class="row"><span class="lab">Switch tabs</span><div class="ctl"><span>Ctrl+1 Face tracking, Ctrl+2 Labeling, Ctrl+3 Settings</span></div></div>
    </section>
    <div id="sec-programs"></div>
  </div></div>
</main>
<script>
let current = "track";
function show(k) {
  current = k;
  for (const t of ["track", "label", "set"]) document.getElementById("tab-" + t).setAttribute("aria-selected", t === k);
  for (const t of ["track", "label"])
    document.getElementById("f-" + t).classList.toggle("on", t === k && !!document.getElementById("f-" + t).src);
  const f = document.getElementById("f-" + k);
  document.getElementById("settings").hidden = k !== "set";
  document.getElementById("wait").hidden = k === "set" || !!f.src;
  if (k === "set") askAll(); else if (f.src) f.focus();
  try { localStorage.setItem("tab", k); } catch {}
}
try { const t = localStorage.getItem("tab"); if (t === "label" || t === "set") current = t; } catch {}
const errors = {};
async function poll() {                          // each program's URL once it's serving, or why it failed
  let st = {};
  try { st = await (await fetch("/status", { cache: "no-store" })).json(); } catch {}
  for (const k of ["track", "label"]) {
    const f = document.getElementById("f-" + k), s = st[k] || {};
    if (s.url && !f.src) { f.src = s.url; document.getElementById("st-" + k).textContent = ""; }
    if (s.error) { errors[k] = s.error; document.getElementById("st-" + k).textContent = "failed"; }
  }
  show(current);
  const w = document.getElementById("wait");
  if (current !== "set" && errors[current]) { w.className = "wait err"; w.textContent = errors[current]; }
  else {
    w.className = "wait";
    w.textContent = st.fetch   // first start of a downloaded copy: the models come from the project's GitHub Release
      ? `Downloading the face models (first start only): ${Math.round(st.fetch.done / 1e6)} of ${Math.round(st.fetch.total / 1e6)} MB`
      : "Loading the face models…";
  }
  if (!["track", "label"].every(k => document.getElementById("f-" + k).src || errors[k])) setTimeout(poll, 400);
}
poll();
addEventListener("keydown", e => {               // Ctrl+1 / Ctrl+2 / Ctrl+3 switch tabs
  const t = { "1": "track", "2": "label", "3": "set" }[e.key];
  if (e.ctrlKey && t) { show(t); e.preventDefault(); }
});
async function checkUpdate() {
  const bs = ["upd", "upd2"].map(id => document.getElementById(id)), say = t => bs.forEach(b => b.textContent = t);
  say("Checking…");
  try {
    const r = await (await fetch("/update", { cache: "no-store", headers: { "X-Face-Tool": "1" } })).json();
    if (r.error) say("Couldn't check");
    else if (r.newer) { say(`${r.latest} is available: open the download page`); bs.forEach(b => b.onclick = () => fetch("/open-release", { headers: { "X-Face-Tool": "1" } })); }
    else say("Up to date");
  } catch { say("Couldn't check"); }
}

// ---------------------------------------------------------------- Settings tab
// The tracker's and the labeling tool's settings live in their own pages (their controls, their browser storage,
// their servers), so this tab asks each page for them (settings_bridge.js, over postMessage) and sends changes back.
const NAMES = { track: "Face tracking", label: "Labeling" }, STATE = { track: null, label: null }, waiting = {};
let rid = 0;
const frame = k => document.getElementById("f-" + k);
const originOf = k => { try { return new URL(frame(k).src).origin; } catch { return null; } };
function tell(k, msg) { const o = originOf(k); if (o && frame(k).contentWindow) frame(k).contentWindow.postMessage(msg, o); }
function askAll() { for (const k of ["track", "label"]) tell(k, { fs: "get" }); drawPrograms(); }
function act(k, id, args) {
  return new Promise(res => { const r = ++rid; waiting[r] = res; tell(k, { fs: "act", id, args, rid: r });
    setTimeout(() => { if (waiting[r]) { delete waiting[r]; res({ ok: false, error: "No answer" }); } }, 30000); });
}
addEventListener("message", e => {
  const k = ["track", "label"].find(k => frame(k).contentWindow === e.source && originOf(k) === e.origin);
  const m = e.data;
  if (!k || !m) return;
  if (m.fs === "state") { STATE[k] = m.items; drawPrograms(); }
  if (m.fs === "result" && waiting[m.rid]) { waiting[m.rid](m); delete waiting[m.rid]; }
});
const el = (tag, props = {}, ...kids) => { const n = Object.assign(document.createElement(tag), props); n.append(...kids.filter(x => x != null)); return n; };
// One row per setting; rows are made once and then only updated, so typing and dragging aren't interrupted
function makeRow(k, it) {
  const key = k + ":" + it.id, row = el("div", { className: "row" }), ctl = el("div", { className: "ctl" });
  row.dataset.key = key;
  const lab = el("label", { textContent: it.label, htmlFor: "s-" + key });
  if (it.type === "toggle") {
    const c = el("input", { type: "checkbox", id: "s-" + key });
    c.onchange = () => tell(k, { fs: "set", id: it.id, value: c.checked });
    ctl.append(c);
  } else if (it.type === "range") {
    const r = el("input", { type: "range", id: "s-" + key, min: it.min, max: it.max, step: it.step }), o = el("output");
    const dp = String(it.step).includes(".") ? String(it.step).split(".")[1].length : 0;
    r.oninput = () => { o.value = (+r.value).toFixed(dp); tell(k, { fs: "set", id: it.id, value: +r.value }); };
    r.dataset.dp = dp; ctl.append(r, o);
  } else if (it.type === "select") {
    const sel = el("select", { id: "s-" + key });
    sel.onchange = () => tell(k, { fs: "set", id: it.id, value: sel.value });
    ctl.append(sel);
  } else if (it.type === "text") {
    const t = el("input", { type: "text", id: "s-" + key, autocomplete: "off" });
    t.onchange = () => tell(k, { fs: "set", id: it.id, value: t.value });
    ctl.append(t);
  } else if (it.type === "multi") {                // several of a list: a box of checkboxes with a filter
    const find = el("input", { type: "text", placeholder: "Find…", autocomplete: "off", ariaLabel: "Find in " + it.label });
    const count = el("span", { className: "msg" }), none = el("button", { className: "b", type: "button", textContent: "Clear" });
    const box = el("div", { className: "box", id: "s-" + key, role: "group", ariaLabel: it.label });
    const send = () => { const v = [...box.querySelectorAll("input:checked")].map(c => c.value);
      count.textContent = `${v.length} selected`; box.querySelectorAll("label").forEach(l => l.classList.toggle("sel", l.firstChild.checked));
      tell(k, { fs: "set", id: it.id, value: v }); };
    box.onchange = send;
    none.onclick = () => { box.querySelectorAll("input").forEach(c => c.checked = false); send(); };
    box._filter = () => {                          // as you type: only the names containing it
      const q = find.value.trim().toLowerCase();
      let shown = 0;
      box.querySelectorAll("label").forEach(l => { l.hidden = !!q && !l.firstChild.value.toLowerCase().includes(q); shown += !l.hidden; });
      box.querySelector(".none")?.remove();
      if (!shown) box.append(el("div", { className: "none", textContent: "Nobody by that name" }));
      box.scrollTop = 0;
    };
    find.oninput = box._filter;
    find.onkeydown = e => { if (e.key === "Escape") { find.value = ""; box._filter(); } };
    ctl.append(el("div", { className: "multi" }, el("div", { className: "top" }, find, count, none), box));
    box._count = count;
  } else if (it.type === "info") {
    ctl.append(el("span", { className: "info", id: "s-" + key }));
  } else if (it.type === "button" || it.type === "form") {
    const inputs = (it.fields || []).map(f => el("input", { type: f.secret ? "password" : "text", placeholder: f.placeholder || "",
      autocomplete: "off", ariaLabel: f.placeholder || f.name, size: f.size || 20, style: f.size ? "flex:0 0 auto" : "" }));
    const b = el("button", { className: "b", id: "s-" + key, type: "button" }), msg = el("span", { className: "msg" });
    b.onclick = async () => {
      b.disabled = true; msg.className = "msg"; msg.textContent = "…";
      const args = {}; (it.fields || []).forEach((f, j) => args[f.name] = inputs[j].value);
      const r = await act(k, it.id, args);
      b.disabled = false;
      msg.textContent = r.ok ? r.value?.message || (it.type === "form" ? "Saved" : "Started") : r.error; msg.className = r.ok ? "msg" : "msg err";
      if (r.ok) inputs.forEach(i => i.value = "");
    };
    ctl.append(...inputs, b, msg);
  }
  if (["toggle", "range", "select", "text"].includes(it.type)) ctl.append(el("span", { className: "msg err rmsg" }));
  row.append(it.type === "info" || it.type === "button" ? el("span", { className: "lab", textContent: it.label }) : lab, ctl);
  if (it.hint) row.append(el("div", { className: "hint", textContent: it.hint }));
  return row;
}
function update(row, it) {
  const c = row.querySelector("#" + CSS.escape("s-" + row.dataset.key));
  row.hidden = !!it.hidden;
  const m = row.querySelector(".rmsg"), h = row.querySelector(".hint");
  if (m) m.textContent = it.error || "";
  if (h && it.hint && h.textContent !== it.hint) h.textContent = it.hint;
  row.classList.toggle("off", !!it.disabled);
  if (!c) return;
  c.disabled = !!it.disabled && it.type !== "info";
  if (document.activeElement === c && (it.type === "text" || it.type === "range")) return;    // don't fight the user
  if (it.type === "toggle") c.checked = !!it.value;
  else if (it.type === "range") { c.value = it.value; c.nextSibling.value = (+it.value).toFixed(+c.dataset.dp); }
  else if (it.type === "select") {
    const opts = JSON.stringify(it.options || []);
    if (c.dataset.opts !== opts) { c.dataset.opts = opts; c.replaceChildren(...(it.options || []).map(([v, t]) => el("option", { value: v, textContent: t }))); }
    c.value = it.value;
  } else if (it.type === "text") c.value = it.value ?? "";
  else if (it.type === "multi") {
    const opts = JSON.stringify(it.options || []), on = new Set(it.value || []);
    if (c.dataset.opts !== opts) {
      c.dataset.opts = opts;
      c.replaceChildren(...(it.options || []).map(([v, t]) => el("label", {}, el("input", { type: "checkbox", value: v }), t)));
      c._filter();                                 // keep what's typed in Find applied
    }
    c.querySelectorAll("label").forEach(l => { l.firstChild.checked = on.has(l.firstChild.value); l.classList.toggle("sel", l.firstChild.checked); });
    c._count.textContent = `${on.size} selected`;
  }
  else if (it.type === "info") c.textContent = it.error ? `Couldn't read this: ${it.error}` : it.value ?? "";
  else if (it.type === "button") c.textContent = it.button;
  else if (it.type === "form") c.textContent = it.button || "Save";
}
function drawPrograms() {
  const box = document.getElementById("sec-programs");
  for (const k of ["track", "label"]) {
    const items = STATE[k];
    if (!items) {                                  // not answered yet: loading, or the program failed
      const id = "sec-wait-" + k;
      const n = document.getElementById(id) || box.appendChild(el("section", { className: "sec", id }));
      n.replaceChildren(el("h2", { textContent: NAMES[k] }),
        el("p", { className: "note", textContent: errors[k] ? `${NAMES[k]} couldn't start, so its settings aren't available.` : "Loading…" }));
      continue;
    }
    document.getElementById("sec-wait-" + k)?.remove();
    for (const it of items) {
      const sid = "sec-" + k + "-" + it.section;
      let sec = document.getElementById(sid);
      if (!sec) {
        sec = box.appendChild(el("section", { className: "sec", id: sid }));
        const resetable = items.filter(x => x.section === it.section && x.def != null && !x.noReset && ["toggle", "range", "select"].includes(x.type));
        const h = el("h2", { textContent: it.section });
        if (resetable.length) h.append(el("button", { className: "b", textContent: "Reset to defaults", type: "button",
          onclick: () => { if (confirm(`Reset "${it.section}" to the default settings?`)) for (const x of STATE[k].filter(x => x.section === it.section && x.def != null && !x.noReset && ["toggle", "range", "select"].includes(x.type))) tell(k, { fs: "set", id: x.id, value: x.def }); } }));
        sec.append(h);
      }
      const key = k + ":" + it.id;
      const row = sec.querySelector(`[data-key="${CSS.escape(key)}"]`) || sec.appendChild(makeRow(k, it));
      update(row, it);
    }
  }
}
async function openDir(which) { try { await fetch("/open?what=" + which, { headers: { "X-Face-Tool": "1" } }); } catch {} }
(async () => {
  try { const p = await (await fetch("/paths", { cache: "no-store" })).json();
        document.getElementById("p-data").textContent = p.data; document.getElementById("p-private").textContent = p.private; } catch {}
})();
setInterval(() => { if (current === "set") askAll(); }, 5000);   // statuses (keys, downloads) and the other tabs' changes
</script></body></html>""".replace("VERSION", VERSION)


def answering(url, app):
    """True if one of our programs (app = 'face-labels' or 'tracker') is already serving at url."""
    try:
        path = "api/summary" if app == "face-labels" else "api/people"
        req = urllib.request.Request(url + path, headers={"X-Face-Tool": "1"})
        with urllib.request.urlopen(req, timeout=3) as r:
            body = json.loads(r.read())
        return body.get("app") == "face-labels" if app == "face-labels" else "people" in body
    except Exception:
        return False


def start(name, module, port, app):
    """Start one program's server in this process on the first free port from `port`, or use the copy
    already running there. Returns its URL once it answers (models loaded)."""
    for p in range(port, port + 10):
        url = f"http://127.0.0.1:{p}/"
        try:
            srv = module.bind(p) if hasattr(module, "bind") else bind(p)
        except OSError:
            if answering(url, app):
                print(f"{name}: using the copy already running at {url}")
                return url
            continue
        print(f"{name}: loading ...")
        module.attach(srv)
        threading.Thread(target=srv.serve_forever, daemon=True, name=name).start()
        print(f"{name}: serving at {url}")
        return url
    raise OSError(f"No free port between {port} and {port + 9}")


def bind(port):
    return localguard.bind(port)                     # no address reuse on Windows: a second copy gets OSError


STATUS = {"track": {}, "label": {}}         # {"url": ...} once serving, {"error": ...} if it failed


def latest_release():
    """{latest, newer} from GitHub's latest release of this project, or {error}. Only when asked
    (the window's "Check for updates"): the app contacts nothing on its own except the first-start
    model download."""
    try:
        req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/releases/latest",
                                     headers={"Accept": "application/vnd.github+json", "User-Agent": "FaceRecognizer"})
        with urllib.request.urlopen(req, timeout=10) as r:
            tag = json.loads(r.read()).get("tag_name", "")
        num = lambda v: tuple(int(x) for x in re.findall(r"\d+", v)[:3])
        return {"latest": tag, "newer": num(tag) > num(VERSION)}
    except Exception as e:
        return {"error": str(e)}


def data_dir():
    """The programs' data folder (face_id.DATA): data\\ beside the .exe, or beside the source files."""
    root = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
    return root / "data"


def shell_server():
    """The tab page itself, on 127.0.0.1 (an http://127.0.0.1 page counts as secure, which the camera
    needs; so must the page around the tracker's frame). The same request checks as the two programs
    (localguard): the right Host; and for anything that does something (contacts GitHub, opens a
    browser or a folder) the X-Face-Tool header, which only this page sends."""
    acts = ("/update", "/open-release", "/open")

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            why = localguard.refuse_reason(self.headers, self.server.server_address[1], write=path in acts)
            if why or path not in ("/", "/status", "/paths") + acts:
                self.send_response(403 if why else 404)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if path == "/open-release":                 # in the normal browser, not inside this window
                import webbrowser
                webbrowser.open(f"https://github.com/{REPO}/releases/latest")
                body = b"{}"
            elif path in ("/paths", "/open"):             # the Settings tab's data folders
                where = {"data": data_dir(), "private": HOME}
                if path == "/open":
                    d = where.get(self.path.split("what=", 1)[-1])
                    if d:
                        d.mkdir(parents=True, exist_ok=True)
                        os.startfile(d)
                body = json.dumps({k: str(v) for k, v in where.items()}).encode()
            elif path == "/update":
                body = json.dumps(latest_release()).encode()
            else:
                body = (SHELL if path == "/" else json.dumps(STATUS)).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8" if path == "/" else "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy", "frame-ancestors 'none'")   # never inside another page
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

    try:
        srv = bind(8764)                            # fixed, so the page's remembered tab survives restarts
    except OSError:
        srv = bind(0)                               # taken (a second copy?): any free port
    srv.RequestHandlerClass = Handler
    port = srv.server_address[1]
    localguard.FRAME_PARENTS.update({f"http://127.0.0.1:{port}", f"http://localhost:{port}"})   # may frame the programs
    threading.Thread(target=srv.serve_forever, daemon=True, name="shell").start()
    return f"http://127.0.0.1:{srv.server_address[1]}/"


def allow_camera(window):
    """Let this window's own local pages use the camera and microphone without asking each time
    (WebView2 asks by default). Pages from anywhere else still get WebView2's prompt."""
    if getattr(window, "_camera_ok", False):
        return
    window._camera_ok = True
    try:
        from System import Action
        from Microsoft.Web.WebView2.Core import CoreWebView2PermissionKind as Kind, CoreWebView2PermissionState as State

        def on_request(_, e):
            if urlparse(e.Uri).hostname == "127.0.0.1" and e.PermissionKind in (Kind.Camera, Kind.Microphone):
                e.State = State.Allow

        def hook():
            window.native.webview.CoreWebView2.PermissionRequested += on_request
        window.native.Invoke(Action(hook))
    except Exception:
        print("Camera permission: WebView2 will ask (couldn't pre-allow):")
        traceback.print_exc()


def run_programs():
    def fail(key, name, e):
        traceback.print_exc()
        why = str(e) if isinstance(e, SystemExit) else f"{type(e).__name__}: {e}"   # SystemExit: our own message
        STATUS[key] = {"error": f"{name} couldn't start.\n\n{why}\n\nDetails are in {HOME / 'app.log'}"}

    def get_models():
        """First start of a downloaded FaceRecognizer.exe: fetch the models (fetch_models.py)."""
        import fetch_models
        if not fetch_models.needed():
            return True
        print(f"Downloading models into {fetch_models.MODELS}: {', '.join(fetch_models.needed())}")

        def show(done, total, _):
            STATUS["fetch"] = {"done": done, "total": total}
        try:
            fetch_models.fetch(show)
            STATUS.pop("fetch", None)
            return True
        except OSError as e:
            for key, name in (("track", "Face tracker"), ("label", "Face Labels")):
                fail(key, name, OSError(f"The face models couldn't be downloaded: {e}\n"
                                        f"Check the internet connection and start the app again."))
            return False

    def one(key, name, module, port, app):
        try:
            STATUS[key] = {"url": start(name, module, port, app)}
        except BaseException as e:               # incl. SystemExit (e.g. face_id.NotDownloaded) from loading
            fail(key, name, e)

    def go():
        if not get_models():
            return
        try:
            import label_tool
            import tracker                          # imports face_id, which checks the model and data files
        except BaseException as e:
            for key, name in (("track", "Face tracker"), ("label", "Face Labels")):
                fail(key, name, e)
            return
        jobs = [("track", "Face tracker", tracker, 8766, "tracker"),
                ("label", "Face Labels", label_tool, 8765, "face-labels")]
        for job in jobs:                            # both load at once: tracker models and the label database
            threading.Thread(target=one, args=job, daemon=True).start()

    threading.Thread(target=go, daemon=True).start()


def main():
    HOME.mkdir(parents=True, exist_ok=True)
    if getattr(sys, "frozen", False) or sys.stdout is None:      # no console: keep the messages in a log
        log = open(HOME / "app.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = log
        print(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} {TITLE} starting")
    import webview
    run_programs()
    window = webview.create_window(TITLE, shell_server(), width=1440, height=920, min_size=(900, 600),
                                   background_color="#0d1512")
    window.events.loaded += lambda: allow_camera(window)
    # private_mode=False keeps each page's remembered options and per-person baselines between runs
    webview.start(private_mode=False, storage_path=str(HOME / "webview"))
    os._exit(0)                                     # window closed: stop both servers and background readers


if __name__ == "__main__":
    main()
