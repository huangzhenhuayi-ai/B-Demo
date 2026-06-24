const toolButtons = document.querySelectorAll(".mode-button");
const topicTool = document.getElementById("topicTool");
const keywordTool = document.getElementById("keywordTool");
const topicForm = document.getElementById("topicForm");
const keywordForm = document.getElementById("keywordForm");
const topicRunButton = document.getElementById("topicRunButton");
const keywordRunButton = document.getElementById("keywordRunButton");

const topicUi = {
  runState: document.getElementById("topicRunState"),
  stateText: document.getElementById("topicStateText"),
  totalCount: document.getElementById("topicTotalCount"),
  doneCount: document.getElementById("topicDoneCount"),
  currentKeyword: document.getElementById("topicCurrentKeyword"),
  progressBar: document.getElementById("topicProgressBar"),
  downloadTopic: document.getElementById("topicDownloadTopic"),
  downloadKeywords: document.getElementById("topicDownloadKeywords"),
  downloadOptimized: document.getElementById("topicDownloadOptimized"),
  downloadDetail: document.getElementById("topicDownloadDetail"),
  score: document.getElementById("topicScore"),
  recommendation: document.getElementById("topicRecommendation"),
  reason: document.getElementById("topicReason"),
  keywordBody: document.getElementById("topicKeywordBody"),
  keywordCount: document.getElementById("topicKeywordCount"),
  optimizedBody: document.getElementById("topicOptimizedBody"),
  optimizedCount: document.getElementById("topicOptimizedCount"),
  detailBody: document.getElementById("topicDetailBody"),
  detailCount: document.getElementById("topicDetailCount"),
};

const keywordUi = {
  runState: document.getElementById("keywordRunState"),
  stateText: document.getElementById("keywordStateText"),
  totalCount: document.getElementById("keywordTotalCount"),
  doneCount: document.getElementById("keywordDoneCount"),
  currentKeyword: document.getElementById("keywordCurrentKeyword"),
  progressBar: document.getElementById("keywordProgressBar"),
  downloadSummary: document.getElementById("keywordDownloadSummary"),
  downloadSuggestions: document.getElementById("keywordDownloadSuggestions"),
  downloadDetail: document.getElementById("keywordDownloadDetail"),
  summaryBody: document.getElementById("keywordSummaryBody"),
  summaryCount: document.getElementById("keywordSummaryCount"),
  suggestionBody: document.getElementById("keywordSuggestionBody"),
  suggestionCount: document.getElementById("keywordSuggestionCount"),
  detailBody: document.getElementById("keywordDetailBody"),
  detailCount: document.getElementById("keywordDetailCount"),
};

const numberFormat = new Intl.NumberFormat("zh-CN");
let topicPollTimer = null;
let keywordPollTimer = null;

toolButtons.forEach((button) => {
  button.addEventListener("click", () => setActiveTool(button.dataset.tool));
});

topicForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearPoll("topic");
  setTopicRunning(true);
  setState(topicUi, "running", "创建任务");
  setTopicDownloads(null);

  const payload = {
    topic: document.getElementById("topic").value,
    pages: numberValue("topicPages"),
    max_results: numberValue("topicMaxResults"),
    sleep: numberValue("topicSleep"),
    timeout: numberValue("topicTimeout"),
    suggestions_limit: 8,
    keyword_limit: numberValue("keywordLimit"),
    optimized_limit: numberValue("optimizedLimit"),
    order: document.getElementById("topicOrder").value,
    enrich: document.getElementById("topicEnrich").checked,
    force_ipv4: document.getElementById("topicForceIpv4").checked,
  };

  try {
    const job = await createJob("/api/topic-runs", payload);
    renderTopicJob(job);
    poll(job.id, "topic");
  } catch (error) {
    setTopicRunning(false);
    setState(topicUi, "error", error.message);
  }
});

keywordForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearPoll("keyword");
  setKeywordRunning(true);
  setState(keywordUi, "running", "创建任务");
  setKeywordDownloads(null);

  const payload = {
    keywords: document.getElementById("keywords").value,
    pages: numberValue("keywordPages"),
    max_results: numberValue("keywordMaxResults"),
    sleep: numberValue("keywordSleep"),
    timeout: numberValue("keywordTimeout"),
    suggestions_limit: numberValue("keywordSuggestionsLimit"),
    order: document.getElementById("keywordOrder").value,
    enrich: document.getElementById("keywordEnrich").checked,
    force_ipv4: document.getElementById("keywordForceIpv4").checked,
  };

  try {
    const job = await createJob("/api/runs", payload);
    renderKeywordJob(job);
    poll(job.id, "keyword");
  } catch (error) {
    setKeywordRunning(false);
    setState(keywordUi, "error", error.message);
  }
});

function setActiveTool(tool) {
  const active = tool === "keyword" ? "keyword" : "topic";
  toolButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.tool === active);
  });
  topicTool.classList.toggle("hidden", active !== "topic");
  keywordTool.classList.toggle("hidden", active !== "keyword");
}

async function createJob(endpoint, payload) {
  const response = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || "任务创建失败");
  }
  return data;
}

function poll(jobId, mode) {
  const timer = window.setInterval(async () => {
    try {
      const response = await fetch(`/api/runs/${jobId}`);
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || "任务状态读取失败");
      }

      if (mode === "topic") {
        renderTopicJob(data);
        if (data.status === "done" || data.status === "error") {
          clearPoll("topic");
          setTopicRunning(false);
        }
      } else {
        renderKeywordJob(data);
        if (data.status === "done" || data.status === "error") {
          clearPoll("keyword");
          setKeywordRunning(false);
        }
      }
    } catch (error) {
      clearPoll(mode);
      if (mode === "topic") {
        setTopicRunning(false);
        setState(topicUi, "error", error.message);
      } else {
        setKeywordRunning(false);
        setState(keywordUi, "error", error.message);
      }
    }
  }, 1200);

  if (mode === "topic") {
    topicPollTimer = timer;
  } else {
    keywordPollTimer = timer;
  }
}

function clearPoll(mode) {
  if (mode === "topic" && topicPollTimer) {
    window.clearInterval(topicPollTimer);
    topicPollTimer = null;
  }
  if (mode === "keyword" && keywordPollTimer) {
    window.clearInterval(keywordPollTimer);
    keywordPollTimer = null;
  }
}

function renderTopicJob(job) {
  renderProgress(topicUi, job);
  setState(topicUi, job.status, job.message || statusLabel(job.status));
  renderTopicSummary(job.topic_summary);
  renderTopicKeywords(job.topic_keywords || []);
  renderOptimizedTopics(job.optimized_topics || []);
  renderDetails(topicUi.detailBody, topicUi.detailCount, job.details_preview || []);
  if (job.files) {
    setTopicDownloads(job.files);
  }
}

function renderKeywordJob(job) {
  renderProgress(keywordUi, job);
  setState(keywordUi, job.status, job.message || statusLabel(job.status));
  renderSummary(job.summary || []);
  renderSuggestions(job.suggestions || []);
  renderDetails(keywordUi.detailBody, keywordUi.detailCount, job.details_preview || []);
  if (job.files) {
    setKeywordDownloads(job.files);
  }
}

function renderProgress(ui, job) {
  const total = Number(job.total_keywords || job.keywords?.length || 0);
  const done = Number(job.completed_keywords || 0);
  const percent = total ? Math.round((done / total) * 100) : 0;

  ui.totalCount.textContent = numberFormat.format(total);
  ui.doneCount.textContent = `${numberFormat.format(done)} / ${numberFormat.format(total)}`;
  ui.currentKeyword.textContent = job.current_keyword || "-";
  ui.progressBar.style.width = `${percent}%`;
}

function setTopicRunning(isRunning) {
  topicRunButton.disabled = isRunning;
  topicRunButton.querySelector("span:last-child").textContent = isRunning ? "分析中" : "开始分析";
}

function setKeywordRunning(isRunning) {
  keywordRunButton.disabled = isRunning;
  keywordRunButton.querySelector("span:last-child").textContent = isRunning ? "排查中" : "开始排查";
}

function setState(ui, status, label) {
  const dot = ui.runState.querySelector(".state-dot");
  dot.className = `state-dot ${status || "idle"}`;
  ui.stateText.textContent = label || "待运行";
}

function statusLabel(status) {
  if (status === "queued") return "排队中";
  if (status === "running") return "采集中";
  if (status === "done") return "已完成";
  if (status === "error") return "失败";
  return "待运行";
}

function setTopicDownloads(files) {
  setDownloads(
    [
      [topicUi.downloadTopic, "topic"],
      [topicUi.downloadKeywords, "topic_keywords"],
      [topicUi.downloadOptimized, "optimized"],
      [topicUi.downloadDetail, "detail"],
    ],
    files
  );
}

function setKeywordDownloads(files) {
  setDownloads(
    [
      [keywordUi.downloadSummary, "summary"],
      [keywordUi.downloadSuggestions, "suggestions"],
      [keywordUi.downloadDetail, "detail"],
    ],
    files
  );
}

function setDownloads(links, files) {
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
    topicUi.score.textContent = "-";
    topicUi.recommendation.textContent = "-";
    topicUi.recommendation.className = "";
    topicUi.reason.textContent = "-";
    return;
  }
  topicUi.score.textContent = row.topic_score ?? "-";
  topicUi.recommendation.textContent = row.recommendation || "-";
  topicUi.recommendation.className = `topic-tag ${tagClass(row.recommendation)}`;
  topicUi.reason.textContent = row.reason || "-";
}

function renderTopicKeywords(rows) {
  topicUi.keywordCount.textContent = `${rows.length} 条`;
  topicUi.keywordBody.replaceChildren();
  if (!rows.length) {
    topicUi.keywordBody.appendChild(emptyRow(7));
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
    topicUi.keywordBody.appendChild(tr);
  }
}

function renderOptimizedTopics(rows) {
  topicUi.optimizedCount.textContent = `${rows.length} 条`;
  topicUi.optimizedBody.replaceChildren();
  if (!rows.length) {
    topicUi.optimizedBody.appendChild(emptyRow(6));
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
    topicUi.optimizedBody.appendChild(tr);
  }
}

function renderSummary(rows) {
  keywordUi.summaryCount.textContent = `${rows.length} 条`;
  keywordUi.summaryBody.replaceChildren();
  if (!rows.length) {
    keywordUi.summaryBody.appendChild(emptyRow(7));
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
    keywordUi.summaryBody.appendChild(tr);
  }
}

function renderSuggestions(rows) {
  keywordUi.suggestionCount.textContent = `${rows.length} 条`;
  keywordUi.suggestionBody.replaceChildren();
  if (!rows.length) {
    keywordUi.suggestionBody.appendChild(emptyRow(3));
    return;
  }

  for (const row of rows) {
    const tr = document.createElement("tr");
    tr.append(
      cell(row.keyword),
      cell(row.suggestion_rank || "-"),
      suggestionCell(row.suggestion || row.highlighted || "-")
    );
    keywordUi.suggestionBody.appendChild(tr);
  }
}

function renderDetails(body, countLabel, rows) {
  countLabel.textContent = `${rows.length} 条`;
  body.replaceChildren();
  if (!rows.length) {
    body.appendChild(emptyRow(7));
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
    body.appendChild(tr);
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

function numberValue(id) {
  return Number(document.getElementById(id).value);
}
