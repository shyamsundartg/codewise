// CodeWise front-end. Plain JS, no build step: one file, easy to read.
"use strict";

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => [...document.querySelectorAll(sel)];
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const LANG_COLORS = { Python: "#7cd4a8", TypeScript: "#a99cff", JavaScript: "#f0b86e", Markdown: "#6b7787", JSON: "#ff8fa3" };
const HLJS_LANG = { py: "python", js: "javascript", jsx: "javascript", ts: "typescript", tsx: "typescript", json: "json", md: "markdown", yml: "yaml", yaml: "yaml", toml: "ini", html: "xml", css: "css", sh: "bash", sql: "sql", go: "go", java: "java", rs: "rust" };

const state = { repo: null, history: [], busy: false, openPath: null };

// ------------------------------------------------------------------- api
async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `${res.status} ${res.statusText}`);
  }
  return res.json();
}

// --------------------------------------------------------------- landing
async function loadRepoList() {
  const repos = await api("/api/repos");
  const list = $("#repo-list");
  if (!repos.length) return;
  list.innerHTML = repos.map((r) => `
    <li class="repo" data-id="${esc(r.repo_id)}">
      <span class="name">${esc(r.name)}</span>
      <span class="muted mono">${r.files} files · ${r.chunks} chunks</span>
    </li>`).join("");
  list.querySelectorAll("li.repo").forEach((li) => li.addEventListener("click", () => openRepo(li.dataset.id)));
}

function showProgress(status, message) {
  $("#progress").classList.remove("hidden");
  const order = ["fetching", "indexing", "embedding", "ready"];
  const idx = order.indexOf(status);
  $$(".steps li").forEach((li, i) => {
    li.className = "";
    if (status === "error") { if (i === 0) li.className = "error"; return; }
    if (i < idx || status === "ready") li.className = "done";
    else if (i === idx) li.className = "active";
  });
  $("#progress-msg").textContent = message || "";
  $("#progress-msg").classList.toggle("warn", status === "error");
}

async function trackJob(job) {
  showProgress(job.status, "Starting…");
  while (true) {
    job = await api(`/api/jobs/${job.job_id}`);
    showProgress(job.status, job.message);
    if (job.status === "ready") return openRepo(job.repo_id);
    if (job.status === "error") return;
    await new Promise((r) => setTimeout(r, 700));
  }
}

async function ingestGithub(e) {
  e.preventDefault();
  const url = $("#github-url").value.trim();
  try {
    const job = await api("/api/repos", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ github_url: url }) });
    trackJob(job);
  } catch (err) { showProgress("error", err.message); }
}

async function ingestZip(file) {
  if (!file) return;
  const form = new FormData();
  form.append("file", file);
  try {
    const job = await api("/api/repos/upload", { method: "POST", body: form });
    trackJob(job);
  } catch (err) { showProgress("error", err.message); }
}

// ------------------------------------------------------------- workspace
async function openRepo(repoId) {
  state.repo = await api(`/api/repos/${repoId}`);
  state.history = [];
  history.replaceState(null, "", `#${repoId}`);

  $("#landing").classList.add("hidden");
  $("#workspace").classList.remove("hidden");
  $("#new-repo-btn").classList.remove("hidden");
  const pill = $("#repo-pill");
  pill.textContent = `${state.repo.name} · ${state.repo.chunk_count} chunks`;
  pill.classList.remove("hidden");

  $$(".msg").forEach((m) => m.remove());
  $("#empty-chat").classList.remove("hidden");
  renderSidebar();
  $("#suggestions").innerHTML = state.repo.suggested_questions
    .map((q) => `<button type="button">${esc(q)}</button>`).join("");
  $$("#suggestions button").forEach((b) => b.addEventListener("click", () => ask(b.textContent)));
  closeViewer();
  $("#question").focus();
}

function renderSidebar() {
  const r = state.repo;
  renderFileTree("");

  $("#ep-count").textContent = r.endpoints.length || "";
  $("#endpoint-list").innerHTML = r.endpoints.length
    ? r.endpoints.map((e) => `<li data-path="${esc(e.file)}" data-line="${e.line}">
        <span class="verb ${esc(e.method)}">${esc(e.method)}</span><span class="mono">${esc(e.path)}</span>
        <span class="sub">${esc(e.handler)} · ${esc(e.file)}:${e.line}</span></li>`).join("")
    : `<li class="muted">No endpoints detected.</li>`;

  $("#dep-count").textContent = r.dependencies.length || "";
  $("#dep-list").innerHTML = r.dependencies.length
    ? r.dependencies.map((d) => `<li data-path="${esc(d.source)}">
        <span class="mono">${esc(d.name)}</span> <span class="muted mono">${esc(d.version)}</span>
        <span class="sub">${esc(d.ecosystem)} · ${esc(d.source)}</span></li>`).join("")
    : `<li class="muted">No manifests found.</li>`;

  $$(".facts li[data-path]").forEach((li) => li.addEventListener("click", () => {
    const line = Number(li.dataset.line) || 1;
    openFile(li.dataset.path, line, line);
  }));

  const total = Object.values(r.languages).reduce((a, b) => a + b, 0) || 1;
  $("#lang-bar").innerHTML = Object.entries(r.languages).map(([lang, n]) =>
    `<span title="${esc(lang)}: ${n} files" style="width:${(n / total) * 100}%;background:${LANG_COLORS[lang] || "#3a4452"}"></span>`).join("");
}

function renderFileTree(filter) {
  const f = filter.toLowerCase();
  const files = state.repo.files.filter((p) => p.toLowerCase().includes(f));
  let lastDir = null;
  const rows = [];
  for (const p of files) {
    const dir = p.includes("/") ? p.slice(0, p.lastIndexOf("/")) : "";
    if (dir !== lastDir) { if (dir) rows.push(`<li class="dir">${esc(dir)}/</li>`); lastDir = dir; }
    const name = p.slice(p.lastIndexOf("/") + 1);
    rows.push(`<li data-path="${esc(p)}" style="padding-left:${dir ? 24 : 12}px" class="${p === state.openPath ? "active" : ""}">${esc(name)}</li>`);
  }
  $("#file-tree").innerHTML = rows.join("") || `<li class="muted">No matches</li>`;
  $$("#file-tree li[data-path]").forEach((li) => li.addEventListener("click", () => openFile(li.dataset.path)));
}

// ---------------------------------------------------------------- viewer
async function openFile(path, start = null, end = null) {
  const { content } = await api(`/api/repos/${state.repo.repo_id}/file?path=${encodeURIComponent(path)}`);
  state.openPath = path;
  const ext = path.split(".").pop().toLowerCase();
  const lang = HLJS_LANG[ext];
  const rows = content.split("\n").map((line, i) => {
    const n = i + 1;
    const html = lang && hljs.getLanguage(lang) ? hljs.highlight(line, { language: lang, ignoreIllegals: true }).value : esc(line);
    const hl = start && n >= start && n <= end ? " class=\"hl\"" : "";
    return `<tr id="L${n}"${hl}><td class="ln">${n}</td><td>${html || " "}</td></tr>`;
  });
  $("#viewer-body").innerHTML = `<table class="code"><tbody>${rows.join("")}</tbody></table>`;
  $("#viewer-path").textContent = start ? `${path}:${start}-${end}` : path;
  $("#workspace").classList.add("viewer-open");
  $("#viewer").classList.remove("collapsed");
  renderFileTree($("#file-filter").value);
  if (start) requestAnimationFrame(() => document.getElementById(`L${start}`)?.scrollIntoView({ block: "center", behavior: "smooth" }));
}

function closeViewer() {
  state.openPath = null;
  $("#workspace").classList.remove("viewer-open");
}

// ------------------------------------------------------------------ chat
function addMessage(role) {
  const node = $("#msg-template").content.firstElementChild.cloneNode(true);
  node.classList.add(role);
  node.querySelector(".msg-role").textContent = role === "user" ? "You" : "CodeWise";
  $("#empty-chat").classList.add("hidden");
  $("#messages").appendChild(node);
  return node;
}

function renderAnswer(bodyEl, text, sources) {
  // Turn [n] into clickable citation buttons (not array indexes like a[1]).
  const withCites = text.replace(/(^|[^\w\]])\[(\d+)\]/g, (_, pre, n) => {
    const ok = sources[Number(n) - 1];
    return `${pre}<button class="cite${ok ? "" : " invalid"}" data-n="${n}" title="${ok ? esc(ok.path) : "Unknown source"}">${n}</button>`;
  });
  bodyEl.innerHTML = DOMPurify.sanitize(marked.parse(withCites));
  bodyEl.querySelectorAll("pre code").forEach((el) => hljs.highlightElement(el));
  bodyEl.querySelectorAll("button.cite:not(.invalid)").forEach((b) => b.addEventListener("click", () => {
    const s = sources[Number(b.dataset.n) - 1];
    openFile(s.path, s.start_line, s.end_line);
  }));
}

function renderSources(node, sources, citedNums) {
  const shown = sources.filter((s) => citedNums.has(s.n));
  const list = shown.length ? shown : sources.slice(0, 3);
  node.querySelector(".msg-sources").innerHTML = list.map((s) =>
    `<button class="source-chip" data-n="${s.n}"><b>${s.n}</b>${esc(s.path)}:${s.start_line}${s.symbol ? ` · ${esc(s.symbol)}` : ""}</button>`).join("");
  node.querySelectorAll(".source-chip").forEach((b) => b.addEventListener("click", () => {
    const s = sources[Number(b.dataset.n) - 1];
    openFile(s.path, s.start_line, s.end_line);
  }));
}

function renderDebug(node, route, sources, trace) {
  const sig = (s) => Object.entries(s.signals).map(([k, r]) => `<span class="sig ${k}">${k} #${r}</span>`).join("");
  const rows = sources.map((s) => `
    <div class="debug-row"><span class="muted">${s.n}</span>
      <span class="loc" title="${esc(s.id)}">${esc(s.path)}:${s.start_line}-${s.end_line}${s.symbol ? " · " + esc(s.symbol) : ""}</span>
      <span>${sig(s)}</span></div>`).join("");
  const t = trace.timings_ms || {};
  const warnings = [];
  if (trace.invalid_citations?.length) warnings.push(`Invalid citations: ${trace.invalid_citations.join(", ")}`);
  if (trace.uncited_answer) warnings.push("Answer has no citations");
  node.querySelector(".debug-body").innerHTML = `
    <div class="muted" style="margin-bottom:6px">Route: <b>${esc(route)}</b> · fused with Reciprocal Rank Fusion</div>
    ${rows || '<div class="muted">No chunks retrieved.</div>'}
    <div class="timings">retrieve ${t.retrieve ?? "-"} ms · generate ${t.generate ?? "-"} ms · total ${trace.total_ms} ms · ~${trace.prompt_tokens_est} prompt tokens</div>
    ${warnings.map((w) => `<div class="warn">⚠ ${esc(w)}</div>`).join("")}`;
  node.querySelector(".msg-debug").classList.remove("hidden");
}

async function ask(question) {
  question = question.trim();
  if (!question || state.busy) return;
  state.busy = true;
  $("#send-btn").disabled = true;
  $("#question").value = "";
  autoGrow();

  addMessage("user").querySelector(".msg-body").textContent = question;
  const node = addMessage("assistant");
  const body = node.querySelector(".msg-body");
  body.classList.add("streaming");

  let text = "", sources = [], route = "", pending = false;
  const scroll = () => { const m = $("#messages"); m.scrollTop = m.scrollHeight; };
  const repaint = () => { if (pending) return; pending = true; requestAnimationFrame(() => { renderAnswer(body, text, sources); scroll(); pending = false; }); };

  try {
    const res = await fetch(`/api/repos/${state.repo.repo_id}/chat`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, history: state.history.slice(-6) }),
    });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let nl;
      while ((nl = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, nl); buf = buf.slice(nl + 1);
        if (!line.trim()) continue;
        const ev = JSON.parse(line);
        if (ev.type === "meta") {
          sources = ev.sources; route = ev.route;
          node.querySelector(".msg-role").insertAdjacentHTML("beforeend", `<span class="route-badge">${esc(route)}</span>`);
        } else if (ev.type === "token") {
          text += ev.text; repaint();
        } else if (ev.type === "done") {
          body.classList.remove("streaming");
          renderAnswer(body, text, sources);
          renderSources(node, sources, new Set(ev.trace.citations));
          renderDebug(node, route, sources, ev.trace);
        }
      }
    }
    state.history.push({ role: "user", content: question }, { role: "assistant", content: text });
  } catch (err) {
    body.classList.remove("streaming");
    body.innerHTML = `<p class="warn">Something went wrong: ${esc(err.message)}</p>`;
  } finally {
    state.busy = false;
    $("#send-btn").disabled = false;
    scroll();
  }
}

function autoGrow() {
  const t = $("#question");
  t.style.height = "auto";
  t.style.height = Math.min(t.scrollHeight, 180) + "px";
}

// ------------------------------------------------------------------ wire
function goHome() {
  $("#workspace").classList.add("hidden");
  $("#landing").classList.remove("hidden");
  $("#repo-pill").classList.add("hidden");
  $("#new-repo-btn").classList.add("hidden");
  $("#progress").classList.add("hidden");
  history.replaceState(null, "", "/");
  loadRepoList();
}

function init() {
  marked.setOptions({ gfm: true, breaks: false });
  $("#github-form").addEventListener("submit", ingestGithub);
  $("#zip-input").addEventListener("change", (e) => ingestZip(e.target.files[0]));
  const dz = $("#dropzone");
  ["dragenter", "dragover"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add("drag"); }));
  ["dragleave", "drop"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.remove("drag"); }));
  dz.addEventListener("drop", (e) => ingestZip(e.dataTransfer.files[0]));

  $("#home-link").addEventListener("click", goHome);
  $("#new-repo-btn").addEventListener("click", goHome);
  $("#viewer-close").addEventListener("click", closeViewer);
  $("#file-filter").addEventListener("input", (e) => renderFileTree(e.target.value));
  $$(".tab").forEach((t) => t.addEventListener("click", () => {
    $$(".tab").forEach((x) => x.classList.toggle("active", x === t));
    $$(".tab-panel").forEach((p) => p.classList.toggle("hidden", p.dataset.panel !== t.dataset.tab));
  }));

  $("#chat-form").addEventListener("submit", (e) => { e.preventDefault(); ask($("#question").value); });
  $("#question").addEventListener("input", autoGrow);
  $("#question").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask($("#question").value); }
  });

  const fromHash = location.hash.slice(1);
  if (fromHash) openRepo(fromHash).catch(goHome); else loadRepoList();
}

init();
