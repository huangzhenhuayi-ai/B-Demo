const form = document.getElementById("runForm");
const modeButtons = document.querySelectorAll(".mode-button");
const topicPanel = document.getElementById("topicPanel");
const keywordPanel = document.getElementById("keywordPanel");
const topicOnlyFields = document.querySelectorAll(".topic-only");
const runButton = document.getElementById("runButton");
const runState = document.getElementById("runState");
const stateText = document.getElementById("stateText");
const keywordCount = document.getElementById("keywordCount");
const doneCount = document.getElementById("doneCount");
const currentKeyword = document.getElementById("currentKeyword");
const progressBar = document.getElementById("progressBar");
const summaryBody = document.getElementById("summaryBody");
const suggestionBody = document.getElementById("suggestionBody");
const detailBody = document.getElementById("detailBody");
const summaryCount = document.getElementById("summaryCount");
const suggestionCount = document.getElementById("suggestionCount");
const detailCount = document.getElementById("detailCount");
const downloadSummary = document.getElementById("downloadSummary");
const downloadSuggestions = document.getElementById("downloadSuggestions");
const downloadDetail = document.getElementById("downloadDetail");
const downloadTopic = document.getElementById("downloadTopic");
const downloadTopicKeywords = document.getElementById("downloadTopicKeywords");
const downloadOptimized = document.getElementById("downloadOptimized");
const topicDownloadLinks = document.querySelectorAll(".topic-download");
const topicResult = document.getElementById("topicResult");
const topicScore = document.getElementById("topicScore");
const topicRecommendation = document.getElementById("topicRecommendation");
const topicReason = document.getElementById("topicReason");
const topicKeywordBody = document.getElementById("topicKeywordBody");
const topicKeywordCount = document.getElementById("topicKeywordCount");
const optimizedBody = document.getElementById("optimizedBody");
const optimizedCount = document.getElementById("optimizedCount");

const numberFormat = new Intl.NumberFormat("zh-CN");
let pollTimer = null;
let currentMode = "topic";

modeButtons.forEach((button) => {
  button.addEventListener("click", () => setMode(button.dataset.mode));
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearPoll();
  setRunning(true);
  setState("running", "创建任务");
  setDownloads(null);

  const payload = {
    pages: Number(document.getElementById("pages").value),
    max_results: Number(document.getElementById("maxResults").value),
    sleep: Number(document.getElementById("sleep").value),
    timeout: Number(document.getElementById("timeout").value),
    suggestions_limit: Number(document.getElementById("suggestionsLimit").value),
    order: document.getElementById("order").value,
    enrich: document.getElementById("enrich").checked,
    force_ipv4: document.getElementById("forceIpv4").checked,
  };
  let endpoint = "/api/runs";
  if (currentMode === "topic") {
    endpoint = "/api/topic-runs";
    payload.topic = document.getElementById("topic").value;
    payload.keyword_limit = Number(document.getElementById("keywordLimit").value);
    payload.optimized_limit = Number(document.getElementById("optimizedLimit").value);
  } else {
    payload.keywords = document.getElementById("keywords").value;
  }

  try {
    const response = await fetch(endpoint, {
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

function setMode(mode) {
  currentMode = mode === "keyword" ? "keyword" : "topic";
  modeButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.mode === currentMode);
  });
  topicPanel.classList.toggle("hidden", currentMode !== "topic");
  keywordPanel.classList.toggle("hidden", currentMode !== "keyword");
  topicOnlyFields.forEach((field) => field.classList.toggle("hidden", currentMode !== "topic"));
  topicDownloadLinks.forEach((link) => link.classList.toggle("hidden", currentMode !== "topic"));
  runButton.querySelector("span:last-child").textContent = currentMode === "topic" ? "开始分析" : "开始排查";
}

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
  const isTopicJob = job.mode === "topic" || Boolean(job.topic_summary);
  topicResult.classList.toggle("hidden", !isTopicJob);
  renderTopicSummary(job.topic_summary);
  renderTopicKeywords(job.topic_keywords || []);
  renderOptimizedTopics(job.optimized_topics || []);
  renderSummary(job.summary || []);
  renderSuggestions(job.suggestions || []);
  renderDetails(job.details_preview || []);
  if (job.files) {
    setDownloads(job.files);
  }
}

function setRunning(isRunning) {
  runButton.disabled = isRunning;
  const idleText = currentMode === "topic" ? "开始分析" : "开始排查";
  const busyText = currentMode === "topic" ? "分析中" : "排查中";
  runButton.querySelector("span:last-child").textContent = isRunning ? busyText : idleText;
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
  const links = [
    [downloadSummary, "summary"],
    [downloadSuggestions, "suggestions"],
    [downloadDetail, "detail"],
    [downloadTopic, "topic"],
    [downloadTopicKeywords, "topic_keywords"],
    [downloadOptimized, "optimized"],
  ];
  if (!files) {
    links.forEach(([link]) => disableDownload(link));
    return;
  }
  links.forEach(([link, key]) => {
    if (files[key]) {
      link.href = files[key];
      link.classList.remove("disabled");
    } else {
      disableDownload(link);
    }
  });
}

function disableDownload(link) {
  link.classList.add("disabled");
  link.removeAttribute("href");
}

function renderTopicSummary(row) {
  if (!row) {
    topicScore.textContent = "-";
    topicRecommendation.textContent = "-";
    topicReason.textContent = "-";
    return;
  }
  topicScore.textContent = row.topic_score ?? "-";
  topicRecommendation.textContent = row.recommendation || "-";
  topicRecommendation.className = `topic-tag ${tagClass(row.recommendation)}`;
  topicReason.textContent = row.reason || "-";
}

function renderTopicKeywords(rows) {
  topicKeywordCount.textContent = `${rows.length} 条`;
  topicKeywordBody.replaceChildren();
  if (!rows.length) {
    topicKeywordBody.appendChild(emptyRow(7));
    return;
  }

  for (const row of rows) {
    const tr = document.createElement("tr");
    tr.append(
      cell(row.keyword),
      scoreCell(row.importance_score),
      scoreCell(row.opportunity_score),
      cell(row.demand_score),
      cell(row.competition_score),
      cell(row.source),
      tagCell(row.recommendation)
    );
    topicKeywordBody.appendChild(tr);
  }
}

function renderOptimizedTopics(rows) {
  optimizedCount.textContent = `${rows.length} 条`;
  optimizedBody.replaceChildren();
  if (!rows.length) {
    optimizedBody.appendChild(emptyRow(6));
    return;
  }

  for (const row of rows) {
    const tr = document.createElement("tr");
    tr.append(
      cell(row.rank),
      cell(row.optimized_topic),
      scoreCell(row.score),
      tagCell(row.recommendation),
      cell(row.based_keyword),
      cell(row.reason)
    );
    optimizedBody.appendChild(tr);
  }
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

function renderSuggestions(rows) {
  suggestionCount.textContent = `${rows.length} 条`;
  suggestionBody.replaceChildren();
  if (!rows.length) {
    suggestionBody.appendChild(emptyRow(3));
    return;
  }

  for (const row of rows) {
    const tr = document.createElement("tr");
    tr.append(
      cell(row.keyword),
      cell(row.suggestion_rank || "-"),
      suggestionCell(row.suggestion || row.highlighted || "-")
    );
    suggestionBody.appendChild(tr);
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

function suggestionCell(value) {
  const td = document.createElement("td");
  const chip = document.createElement("span");
  chip.className = "suggestion-chip";
  chip.textContent = value || "-";
  td.appendChild(chip);
  return td;
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
