const state = { path: "", selectedFile: "", selectedWorkRun: "", selectedStage: "all", selectedJob: "", jobs: [], config: null, transcriptJob: "" };
const $ = (id) => document.getElementById(id);
const API_BASE = location.pathname.startsWith("/transcriber") ? "/transcriber/api" : "/api";
const apiPath = (path) => `${API_BASE}${path}`;
const stageMeta = {
  all: { name: "一键完整处理", action: "开始完整处理", flow: "视频 → 原始音频 → 文字 → 时间戳" },
  extract: { name: "提取分析音频", action: "开始提取音频", flow: "视频 → 16kHz 单声道 WAV" },
  asr: { name: "ASR 语音转录", action: "开始语音转录", flow: "原始混音 → ASR → 逐句时间戳" },
  align: { name: "精细时间对齐", action: "开始时间对齐", flow: "转录文字 → 句级时间戳" },
};
const statusNames = { queued: "等待中", running: "处理中", cancelling: "正在中止", cancelled: "已中止", completed: "已完成", failed: "失败", interrupted: "已中断" };

function escapeHtml(value) { const node = document.createElement("div"); node.textContent = value ?? ""; return node.innerHTML; }
function escapeAttr(value) { return String(value ?? "").replaceAll("&", "&amp;").replaceAll('"', "&quot;").replaceAll("<", "&lt;").replaceAll(">", "&gt;"); }
function prettySize(bytes) { if (bytes == null) return ""; const units = ["B", "KB", "MB", "GB"]; let value = bytes, index = 0; while (value >= 1024 && index < units.length - 1) { value /= 1024; index++; } return `${value.toFixed(index > 1 ? 1 : 0)} ${units[index]}`; }
function suggestedId(path) { const stem = path.split("/").pop().replace(/\.[^.]+$/, "").replace(/[^a-zA-Z0-9_-]+/g, "-").replace(/^-|-$/g, "").slice(0, 32) || "recording"; let hash = 0; for (const char of path) hash = ((hash << 5) - hash + char.charCodeAt(0)) | 0; return `${stem}-${Math.abs(hash).toString(16)}`; }

async function browse(path = "") {
  const response = await fetch(apiPath(`/files?path=${encodeURIComponent(path)}`));
  if (!response.ok) throw new Error("无法读取录播目录");
  const data = await response.json();
  state.path = data.path;
  const parts = data.path ? data.path.split("/") : [];
  $("breadcrumbs").innerHTML = `<button class="crumb" data-path="">/录播目录</button>` + parts.map((part, i) => ` / <button class="crumb" data-path="${escapeAttr(parts.slice(0, i + 1).join("/"))}">${escapeHtml(part)}</button>`).join("");
  $("breadcrumbs").querySelectorAll(".crumb").forEach((button) => button.onclick = () => browse(button.dataset.path));
  const rows = [];
  if (data.parent !== null) rows.push(`<button class="file-row" data-type="directory" data-path="${escapeAttr(data.parent)}"><span>↰</span><span>返回上级</span><small></small></button>`);
  for (const entry of data.entries) {
    const selected = entry.path === state.selectedFile ? " selected" : "";
    rows.push(`<button class="file-row${selected}" data-type="${entry.type}" data-path="${escapeAttr(entry.path)}"><span>${entry.type === "directory" ? "▰" : "▶"}</span><span>${escapeHtml(entry.name)}</span><small>${prettySize(entry.size)}</small></button>`);
  }
  $("file-list").innerHTML = rows.join("") || `<p class="muted">这个目录中没有支持的视频文件。</p>`;
  $("file-list").querySelectorAll(".file-row").forEach((row) => row.onclick = () => row.dataset.type === "directory" ? browse(row.dataset.path) : selectFile(row.dataset.path));
}

function selectFile(path) {
  state.selectedFile = path;
  state.selectedWorkRun = "";
  $("source-name").textContent = path.split("/").pop();
  $("selected-file").textContent = `/input/${path}`;
  $("choose-file").classList.remove("empty");
  $("source-icon").textContent = "▶";
  $("run-id").value = suggestedId(path);
  updatePaths();
  $("file-dialog").close();
  $("action-message").textContent = "";
}

async function browseWorkRuns() {
  const response = await fetch(apiPath(`/work-runs?stage=${encodeURIComponent(state.selectedStage)}`));
  if (!response.ok) throw new Error("无法读取过程文件目录");
  const entries = await response.json();
  $("work-list").innerHTML = entries.map((entry) => `<button class="file-row${entry.run_id === state.selectedWorkRun ? " selected" : ""}" data-run-id="${escapeAttr(entry.run_id)}" data-source="${escapeAttr(entry.source_name || "")}"><span>▣</span><span><b>${escapeHtml(entry.run_id)}</b><br><small>${escapeHtml(entry.source_name || "原视频记录不可用")}</small></span><small>${escapeHtml(entry.required_file)} · ${prettySize(entry.size)}</small></button>`).join("") || `<p class="muted">没有找到当前模块可以复用的过程文件。</p>`;
  $("work-list").querySelectorAll(".file-row").forEach((row) => row.onclick = () => selectWorkRun(row.dataset.runId, row.dataset.source));
}

function selectWorkRun(runId, sourceName) {
  state.selectedWorkRun = runId;
  state.selectedFile = "";
  $("run-id").value = runId;
  $("source-name").textContent = runId;
  $("selected-file").textContent = `过程文件：/work/jobs/${runId}${sourceName ? ` · ${sourceName}` : ""}`;
  $("choose-file").classList.remove("empty");
  $("source-icon").textContent = "▣";
  updatePaths();
  $("work-dialog").close();
  $("action-message").textContent = "已选择过程文件，可直接运行当前模块。";
}

function updatePaths() {
  if (!state.config || !$("run-id").value) return;
  $("output-path").textContent = `${state.config.output_root}/${$("run-id").value}`;
}

function selectStage(stage) {
  state.selectedStage = stage;
  document.querySelectorAll(".workflow-tab").forEach((button) => button.classList.toggle("active", button.dataset.stage === stage));
  const meta = stageMeta[stage];
  $("stage-title").textContent = meta.name;
  $("stage-pill").textContent = meta.flow;
  $("start-button").innerHTML = `<span>▶</span> ${meta.action}`;
  $("common-options").hidden = !["all", "asr"].includes(stage);
  $("choose-work").hidden = !["asr", "align"].includes(stage);
}

function testMinutes() {
  const value = document.querySelector('input[name="duration"]:checked').value;
  return value === "custom" ? $("custom-minutes").value : value;
}

function options(stage) {
  return { input: state.selectedFile, run_id: $("run-id").value, stage, test_minutes: testMinutes(), chunk_seconds: Number($("chunk-seconds").value), separation_model: "htdemucs", asr_engine: $("asr-engine").value, asr_source: "mix", skip_separation: true, skip_alignment: !$("use-alignment").checked };
}

async function runSelectedStage() {
  const stage = state.selectedStage;
  const canReuse = ["asr", "align"].includes(stage) && $("run-id").value.trim();
  if (!state.selectedFile && !canReuse) { $("action-message").textContent = "请选择录播文件，或为独立模块选择已有过程任务。"; $("file-dialog").showModal(); return; }
  $("start-button").disabled = true;
  $("action-message").textContent = `正在提交：${stageMeta[stage].name}……`;
  try {
    const response = await fetch(apiPath("/jobs"), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(options(stage)) });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "任务提交失败");
    state.selectedJob = data.id;
    state.transcriptJob = "";
    $("action-message").textContent = "任务已开始。下面会持续显示处理进度。";
    await refreshJobs();
    $("result-card").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) { $("action-message").textContent = error.message; }
  finally { $("start-button").disabled = false; }
}

async function refreshJobs() {
  const response = await fetch(apiPath("/jobs"));
  state.jobs = await response.json();
  $("job-list").innerHTML = state.jobs.map((job) => `<div class="job${job.id === state.selectedJob ? " selected" : ""}" data-id="${escapeAttr(job.id)}"><div class="job-head"><strong>${escapeHtml(job.run_id)}</strong><span class="status ${job.status}">${statusNames[job.status] || job.status}</span></div><p>${escapeHtml(stageMeta[job.stage]?.name || job.stage)} · ${escapeHtml(job.progress_label || "等待")}</p><div class="job-progress"><i style="width:${job.progress || 0}%"></i></div></div>`).join("") || `<p class="muted">暂无任务</p>`;
  $("job-list").querySelectorAll(".job").forEach((row) => row.onclick = () => { state.selectedJob = row.dataset.id; state.transcriptJob = ""; refreshJobs(); });
  if (state.selectedJob) await refreshCurrentJob();
}

async function refreshCurrentJob() {
  const job = state.jobs.find((item) => item.id === state.selectedJob);
  if (!job) return;
  $("current-job-title").textContent = `${job.run_id} · ${stageMeta[job.stage]?.name || job.stage}`;
  $("log-status").textContent = statusNames[job.status] || job.status;
  $("log-status").className = `status ${job.status}`;
  $("cancel-button").hidden = !["queued", "running", "cancelling"].includes(job.status);
  $("cancel-button").disabled = job.status === "cancelling";
  $("progress-label").textContent = job.progress_label || "等待任务";
  $("progress-value").textContent = `${job.progress || 0}%`;
  $("progress-bar").style.width = `${job.progress || 0}%`;
  $("job-output-path").textContent = job.output_path || "—";
  $("work-path").textContent = job.work_path || "—";
  const results = job.downloads.map((name) => `<a target="_blank" href="${API_BASE}/jobs/${encodeURIComponent(job.id)}/download/${name}?inline=1">${escapeHtml(name)}</a>`).join("");
  const work = (job.work_downloads || []).map((name) => `<a target="_blank" href="${API_BASE}/jobs/${encodeURIComponent(job.id)}/download-work/${name}?inline=1">${escapeHtml(name)}</a>`).join("");
  $("downloads").innerHTML = `${results ? "<strong>结果文件 · 点击打开</strong>" + results : ""}${work ? "<strong>中间文件 · 点击打开</strong>" + work : ""}` || `<p class="muted">任务产生的文件会显示在这里。</p>`;
  const logResponse = await fetch(apiPath(`/jobs/${encodeURIComponent(job.id)}/log`));
  const logData = await logResponse.json();
  const log = $("job-log"), nearBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 70;
  log.textContent = logData.log || "暂无日志。";
  if (nearBottom) log.scrollTop = log.scrollHeight;
  if (job.downloads.includes("transcript.jsonl") && state.transcriptJob !== job.id) await loadTranscript(job);
  else if (!job.downloads.includes("transcript.jsonl")) $("transcript-list").innerHTML = `<div class="empty-result">${job.status === "completed" ? "这个独立模块不生成转录文字，可在“文件”中查看输出。" : "处理中，识别结果生成后会自动显示在这里。"}</div>`;
}

async function loadTranscript(job) {
  state.transcriptJob = job.id;
  try {
    const response = await fetch(apiPath(`/jobs/${encodeURIComponent(job.id)}/download/transcript.jsonl?inline=1`));
    if (!response.ok) throw new Error();
    const text = await response.text();
    const items = text.split(/\r?\n/).filter(Boolean).map((line) => JSON.parse(line));
    $("transcript-list").innerHTML = `<div class="transcript-table">${items.map((item) => `<div class="transcript-row"><time>${escapeHtml(item.start_text)}<br>${escapeHtml(item.end_text)}</time><p>${escapeHtml(item.text)}</p></div>`).join("")}</div>`;
  } catch { $("transcript-list").innerHTML = `<div class="empty-result">转录文件暂时无法预览，请到“文件”页打开。</div>`; }
}

document.querySelectorAll(".workflow-tab").forEach((button) => button.onclick = () => selectStage(button.dataset.stage));
document.querySelectorAll('input[name="duration"]').forEach((radio) => radio.onchange = () => { $("custom-minutes").disabled = radio.value !== "custom" || !radio.checked; });
document.querySelectorAll(".result-tab").forEach((button) => button.onclick = () => {
  document.querySelectorAll(".result-tab").forEach((tab) => tab.classList.toggle("active", tab === button));
  document.querySelectorAll(".result-view").forEach((view) => view.classList.toggle("active", view.id === `${button.dataset.view}-view`));
});
$("choose-file").onclick = () => { $("file-dialog").showModal(); browse(state.path); };
$("close-files").onclick = () => $("file-dialog").close();
$("file-dialog").onclick = (event) => { if (event.target === $("file-dialog")) $("file-dialog").close(); };
$("refresh-files").onclick = () => browse(state.path);
$("choose-work").onclick = () => { $("work-dialog").showModal(); browseWorkRuns().catch((error) => $("work-list").innerHTML = `<p class="muted">${escapeHtml(error.message)}</p>`); };
$("close-work").onclick = () => $("work-dialog").close();
$("work-dialog").onclick = (event) => { if (event.target === $("work-dialog")) $("work-dialog").close(); };
$("refresh-work").onclick = () => browseWorkRuns();
$("refresh-jobs").onclick = refreshJobs;
$("cancel-button").onclick = async () => {
  if (!state.selectedJob || !confirm("确定中止这个任务吗？已经生成的中间文件会保留。")) return;
  $("cancel-button").disabled = true;
  const response = await fetch(apiPath(`/jobs/${encodeURIComponent(state.selectedJob)}/cancel`), { method: "POST" });
  const data = await response.json();
  if (!response.ok) $("action-message").textContent = data.error || "中止任务失败";
  await refreshJobs();
};
$("run-id").addEventListener("input", updatePaths);
$("start-button").onclick = runSelectedStage;
fetch(apiPath("/config")).then((response) => response.json()).then((config) => {
  state.config = config;
  updatePaths();
  const option = $("asr-engine").querySelector('option[value="aliyun"]');
  option.textContent = config.aliyun_asr_configured ? "阿里云 qwen3-asr-flash（已配置）" : "阿里云 qwen3-asr-flash（未配置）";
  $("aliyun-hint").textContent = config.aliyun_asr_configured ? "API Key 已由 Docker 环境变量安全加载" : "需要先在 .env 配置 DASHSCOPE_API_KEY";
  $("aliyun-hint").className = `field-hint ${config.aliyun_asr_configured ? "ready" : "missing"}`;
});
browse().catch((error) => $("file-list").innerHTML = `<p class="muted">${escapeHtml(error.message)}</p>`);
refreshJobs();
setInterval(refreshJobs, 2500);
