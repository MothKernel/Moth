"use strict";
const $ = id => document.getElementById(id);
const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
let lang = localStorage.getItem("moth-language") || "en";
if (!MOTH_LANG[lang]) lang = "en";
let page = "scan", tools = [], current = null, selected = new Set(), busy = false;
const t = key => MOTH_LANG[lang][key] || MOTH_LANG.en[key] || key;
const token = document.querySelector('meta[name="moth-token"]').content;
const active = () => current && ["queued", "running", "stopping"].includes(current.status);

async function api(path, options = {}) {
  const response = await fetch("/api/" + path, {...options, headers: {"X-Moth-Token":token, "Content-Type":"application/json", ...options.headers}});
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw Error(typeof data.detail === "string" ? data.detail : "Request failed (" + response.status + ")");
  }
  return response;
}
let toastTimer;
function notify(message) { $("toast").textContent = message; $("toast").hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => $("toast").hidden = true, 6500); }
function localize() {
  document.documentElement.lang = lang;
  $("language").value = lang;
  document.querySelectorAll("[data-i18n]").forEach(el => el.textContent = t(el.dataset.i18n));
  $("page-label").textContent = t(page === "scan" ? "assessment" : page);
  $("progress").setAttribute("aria-label", t("progress_label"));
  renderTools(); renderScan();
  if (page === "history") loadHistory().catch(e => notify(e.message));
}
function switchPage(value) {
  page = value;
  ["scan","tools","history"].forEach(p => $(p + "-page").hidden = p !== page);
  document.querySelectorAll("[data-page]").forEach(el => el.classList.toggle("active", el.dataset.page === page));
  $("page-label").textContent = t(page === "scan" ? "assessment" : page);
  if (page === "history") loadHistory().catch(e => notify(e.message));
}
function renderTools() {
  $("tool-grid").innerHTML = tools.map(tool => {
    const ready = tool.status === "ready", installing = tool.status === "installing";
    const manual = tool.id === "nmap" && !ready;
    const requirement = tool.id === "zap" && tool.status === "prerequisite" ? t("zap_requirement") : manual ? t("nmap_requirement") : tool.message;
    const action = manual ? `<a class="secondary" href="${esc(tool.url)}" target="_blank" rel="noreferrer">${t("manual")} ↗</a><button class="secondary" data-refresh>${t("refresh")}</button>` : `<button class="${ready ? "secondary" : "primary"}" data-install="${esc(tool.id)}" ${ready || installing || tool.status === "prerequisite" || active() ? "disabled" : ""}>${t(ready ? "ready" : installing ? "installing" : tool.status === "error" ? "retry" : "install")}</button>`;
    return `<article class="tool-card"><div class="tool-head"><h2>${esc(tool.name)}</h2><span class="badge">${t(tool.status === "ready" ? "ready" : tool.status)}</span></div><p>${t("tool_" + tool.id)}</p>${requirement ? `<div class="tool-message">${esc(requirement)}</div>` : ""}<div class="tool-actions">${action}<a href="${esc(tool.url)}" target="_blank" rel="noreferrer">${t("upstream")}</a></div></article>`;
  }).join("");
  $("scan-tools").innerHTML = tools.map(tool => `<label class="tool-option"><input type="checkbox" value="${esc(tool.id)}" ${selected.has(tool.id) ? "checked" : ""} ${tool.status !== "ready" || active() ? "disabled" : ""}><span>${esc(tool.name)}</span><small>${t(tool.status === "ready" ? "ready" : "missing")}</small></label>`).join("");
  $("selected-count").textContent = selected.size;
}
function renderScan() {
  const running = active();
  $("start-button").disabled = Boolean(running);
  $("stop-button").hidden = !running;
  $("progress").hidden = !current;
  $("progress").value = current?.progress || 0;
  $("progress-icon").classList.toggle("running", Boolean(running));
  let state = !current ? "idle" : running ? "running" : current.status === "completed" ? "finished" : ["cancelled","interrupted"].includes(current.status) ? "cancelled" : "failed";
  $("progress-title").textContent = t(state + "_title");
  $("progress-description").textContent = t(state + "_description");
  $("step-list").innerHTML = current ? `<div class="step"><span>${esc(current.target)}</span></div>` + current.steps.map(step => `<div class="step"><span>${esc(step.tool)}</span><span>${t(step.status)}</span></div>`).join("") : "";
  $("result-area").hidden = !current;
  if (!current) return;
  $("summary").innerHTML = `<span class="stat">${current.findings.length} ${t("observations")}</span><span class="stat">${current.steps.filter(s => s.status === "completed").length} ${t("checks")}</span><span class="stat">${t(current.status)}</span>`;
  $("scan-errors").innerHTML = current.errors.map(e => `<div class="error"><strong>${esc(e.tool)}</strong> · ${esc(e.message)}</div>`).join("");
  $("findings").innerHTML = current.findings.map(f => {
    const text = f.text[lang] || f.text.en;
    return `<article class="finding"><span class="badge ${esc(f.severity)}">${t(f.severity)}</span><span class="source">${esc(f.tool)} · ${t(f.kind)}</span><h3>${esc(text[0])}</h3><p>${esc(text[1])}</p><p class="recommendation"><strong>${t("recommendation")}</strong><br>${esc(text[2])}</p>${f.source_language === "en" && lang !== "en" ? `<p>${t("english_source")}</p>` : ""}<details><summary>${t("technical")}</summary><p>${t(f.confidence)}</p><pre>${esc(f.evidence)}</pre>${f.technical ? `<pre>${esc(f.technical)}</pre>` : ""}</details></article>`;
  }).join("") || (running ? "" : `<div class="empty">${t("no_findings")}</div>`);
  if (current.coverage.coverage) $("findings").insertAdjacentHTML("beforeend", `<div class="notice"><strong>${t("coverage")}</strong><br>${esc(current.coverage.coverage)}${current.coverage.http_status ? ` · HTTP ${esc(current.coverage.http_status)}` : ""}<br>${t("report_note")}</div>`);
}
async function loadTools() { tools = await (await api("tools")).json(); renderTools(); }
async function loadHistory() {
  const scans = await (await api("scans")).json();
  $("history-list").innerHTML = scans.map(scan => `<button class="history-item" data-scan="${esc(scan.id)}"><span><strong>${esc(scan.target)}</strong><small>${esc(new Date(scan.created).toLocaleString(lang))}</small></span><span class="history-meta"><span class="badge">${t(scan.status)}</span><small>${scan.finding_count} ${t("observations")} ↗</small></span></button>`).join("") || `<div class="empty">${t("no_history")}</div>`;
}
async function loadScan(id) {
  if (active() && current.id !== id) throw Error(t("scan_in_progress"));
  current = await (await api("scans/" + encodeURIComponent(id))).json();
  localStorage.setItem("moth-last-scan", id);
  renderScan();
}
async function downloadReport(format) {
  if (!current) return;
  const response = await api(`scans/${current.id}/report?format=${format}&language=${lang}`);
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a"); link.href = url; link.download = `moth-${current.id}.${format}`; link.click(); setTimeout(() => URL.revokeObjectURL(url),1000); notify(t("export"));
}
$("language").addEventListener("change", e => {lang=e.target.value;localStorage.setItem("moth-language",lang);localize();});
document.querySelectorAll("[data-page]").forEach(el => el.addEventListener("click", () => switchPage(el.dataset.page)));
$("scan-tools").addEventListener("change", e => {if (e.target.type === "checkbox") {e.target.checked ? selected.add(e.target.value) : selected.delete(e.target.value);$("selected-count").textContent=selected.size;}});
$("scan-form").addEventListener("submit", async e => {
  e.preventDefault(); $("start-button").disabled = true;
  try {
    const result = await (await api("scans", {method:"POST",body:JSON.stringify({target:$("target").value,tools:[...selected],authorized:$("authorized").checked,allow_private:$("lab").checked})})).json();
    await loadScan(result.id); renderTools();
  } catch (error) {notify(error.message);renderScan();}
});
$("stop-button").addEventListener("click", async () => {if (current) {try {await api(`scans/${current.id}/stop`, {method:"POST"});$("stop-button").textContent=t("stopping");}catch(e){notify(e.message);}}});
$("tool-grid").addEventListener("click", async e => {
  const button = e.target.closest("[data-install],[data-refresh]"); if (!button) return;
  button.disabled = true;
  try {if (button.dataset.install) await api(`tools/${button.dataset.install}/install`,{method:"POST"});await loadTools();} catch(error) {notify(error.message);await loadTools();}
});
$("history-list").addEventListener("click", async e => {const row=e.target.closest("[data-scan]");if(row){try{await loadScan(row.dataset.scan);switchPage("scan");}catch(error){notify(error.message);}}});
$("export-html").addEventListener("click", () => downloadReport("html").catch(e=>notify(e.message)));
$("export-json").addEventListener("click", () => downloadReport("json").catch(e=>notify(e.message)));
async function tick() {
  if (busy) return;
  busy=true;
  try {if(active()) await loadScan(current.id); if(page==="tools" || tools.some(t=>t.status==="installing")) await loadTools();}
  catch(error){notify(error.message);}finally{busy=false;}
}
async function init() {
  localize();
  try {await loadTools();const id=localStorage.getItem("moth-last-scan");if(id) await loadScan(id);}catch(error){notify(error.message);}
  setInterval(tick,2000);
}
init();
