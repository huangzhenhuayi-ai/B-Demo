const form = document.getElementById("runForm");
const runButton = document.getElementById("runButton");
const runState = document.getElementById("runState");
const stateText = document.getElementById("stateText");
const keywordCount = document.getElementById("keywordCount");
const doneCount = document.getElementById("doneCount");
const currentKeyword = document.getElementById("currentKeyword");
const progressBar = document.getElementById("progressBar");
const summaryBody = document.getElementById("summaryBody");
const detailBody = document.getElementById("detailBody");
const summaryCount = document.getElementById("summaryCount");
const detailCount = document.getElementById("detailCount");
const downloadSummary = document.getElementById("downloadSummary");
const downloadDetail = document.getElementById("downloadDetail");

const numberFormat = new Intl.NumberFormat("zh-CN");
let pollTimer = null;

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearPoll();
  setRunning(true);
  setState("running", "创建任务");
  setDownloads(null);

  const payload = {
    keywords: document.getElementById("keywords").value,
    pages: Number(document.getElementById("pages").value),
    max_results: Number(document.getElementById("maxResults").value),
    sleep: Number(document.getElementById("sleep").value),
    timeout: Number(document.getElementById("timeout").value),
    order: document.getElementById("order").value,
    enrich: document.getElementById("enrich").checked,
    force_ipv4: document.getElementById("forceIpv4").checked,
  };

  try {
    const response = await fetch("/api/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "任务创建失败");
    }
    renderJob(data);
    poll(data.id);
  } catch (error) {
    setRunning(false);
    setState("error", error.message);
  }
});

function poll(jobId) {
  pollTimer = window.setInterval(async () => {
    try {
      const response = await fetch(`/api/runs/${jobId}`);
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || "任务状态读取失败");
      }
      renderJob(data);
      if (data.status === "done" || data.status === "error") {
        clearPoll();
        setRunning(false);
      }
    } catch (error) {
      clearPoll();
      setRunning(false);
      setState("error", error.message);
    }
  }, 1200);
}

function clearPoll() {
  if (pollTimer) {
    window.clearInterval(pollTimer);
    pollTimer = null;
  }
}

function renderJob(job) {
  const total = Number(job.total_keywords || job.keywords?.length || 0);
  const done = Number(job.completed_keywords || 0);
  const percent = total ? Math.round((done / total) * 100) : 0;

  keywordCount.textContent = numberFormat.format(total);
  doneCount.textContent = `${numberFormat.format(done)} / ${numberFormat.format(total)}`;
  currentKeyword.textContent = job.current_keyword || "-";
  progressBar.style.width = `${percent}%`;

  const label = job.message || statusLabel(job.status);
  setState(job.status, label);
  renderSummary(job.summary || []);
  renderDetails(job.details_preview || []);
  if (job.files) {
    setDownloads(job.files);
  }
}

function setRunning(isRunning) {
  runButton.disabled = isRunning;
  runButton.querySelector("span:last-child").textContent = isRunning ? "排查中" : "开始排查";
}

function setState(status, label) {
  const dot = runState.querySelector(".state-dot");
  dot.className = `state-dot ${status || "idle"}`;
  stateText.textContent = label || "待运行";
}

function statusLabel(status) {
  if (status === "queued") return "排队中";
  if (status === "running") return "采集中";
  if (status === "done") return "已完成";
  if (status === "error") return "失败";
  return "待运行";
}

function setDownloads(files) {
  if (!files) {
    downloadSummary.classList.add("disabled");
    downloadDetail.classList.add("disabled");
    downloadSummary.removeAttribute("href");
    downloadDetail.removeAttribute("href");
    return;
  }
  downloadSummary.href = files.summary;
  downloadDetail.href = files.detail;
  downloadSummary.classList.remove("disabled");
  downloadDetail.classList.remove("disabled");
}

function renderSummary(rows) {
  summaryCount.textContent = `${rows.length} 条`;
  summaryBody.replaceChildren();
  if (!rows.length) {
    summaryBody.appendChild(emptyRow(7));
    return;
  }

  for (const row of rows) {
    const tr = document.createElement("tr");
    tr.append(
      cell(row.keyword),
      scoreCell(row.opportunity_score),
      cell(row.demand_score),
      cell(row.growth_score),
      cell(row.competition_score),
      tagCell(row.recommendation),
      cell(row.reason)
    );
    summaryBody.appendChild(tr);
  }
}

function renderDetails(rows) {
  detailCount.textContent = `${rows.length} 条`;
  detailBody.replaceChildren();
  if (!rows.length) {
    detailBody.appendChild(emptyRow(7));
    return;
  }

  for (const row of rows) {
    const tr = document.createElement("tr");
    tr.append(
      cell(row.rank),
      titleCell(row.title, row.url),
      cell(row.author),
      cell(formatNumber(row.views)),
      cell(formatNumber(row.likes)),
      cell(formatNumber(row.favorites)),
      cell(row.publish_date || "-")
    );
    detailBody.appendChild(tr);
  }
}

function cell(value) {
  const td = document.createElement("td");
  td.textContent = value === undefined || value === null || value === "" ? "-" : value;
  return td;
}

function scoreCell(value) {
  const td = cell(value);
  td.className = "score";
  return td;
}

function titleCell(title, url) {
  const td = document.createElement("td");
  if (url) {
    const link = document.createElement("a");
    link.className = "video-title";
    link.href = url;
    link.target = "_blank";
    link.rel = "noreferrer";
    link.textContent = title || url;
    td.appendChild(link);
  } else {
    td.textContent = title || "-";
  }
  return td;
}

function tagCell(value) {
  const td = document.createElement("td");
  const tag = document.createElement("span");
  tag.className = `tag ${tagClass(value)}`;
  tag.textContent = value || "-";
  td.appendChild(tag);
  return td;
}

function tagClass(value) {
  if (value === "可执行") return "go";
  if (value === "小样本测试") return "test";
  return "no";
}

function emptyRow(colspan) {
  const tr = document.createElement("tr");
  const td = document.createElement("td");
  td.className = "empty";
  td.colSpan = colspan;
  td.textContent = "暂无结果";
  tr.appendChild(td);
  return tr;
}

function formatNumber(value) {
  const number = Number(value || 0);
  return numberFormat.format(number);
}
