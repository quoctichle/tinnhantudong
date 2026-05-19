const DEFAULT_API_BASE = localStorage.getItem("apiBaseUrl") || "http://127.0.0.1:8000";

const jobLabels = {
  exchange: "Gửi thông báo đơn đổi",
  billing: "Gửi thông báo cước",
  refund: "Gửi thông báo hoàn tiền",
};

const apiInput = document.getElementById("apiBaseUrl");
const saveConfigButton = document.getElementById("saveConfigButton");
const checkHealthButton = document.getElementById("checkHealthButton");
const clearLogButton = document.getElementById("clearLogButton");
const logOutput = document.getElementById("logOutput");
const healthBadge = document.getElementById("healthBadge");

apiInput.value = DEFAULT_API_BASE;

function getApiBaseUrl() {
  return apiInput.value.trim().replace(/\/$/, "");
}

function setHealthState(type, message) {
  const dot = healthBadge.querySelector(".status-dot");
  const text = healthBadge.querySelector("span:last-child");
  dot.classList.remove("ok", "error");
  if (type === "ok") {
    dot.classList.add("ok");
  }
  if (type === "error") {
    dot.classList.add("error");
  }
  text.textContent = message;
}

function appendLog(message) {
  const timestamp = new Date().toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  logOutput.textContent = `[${timestamp}] ${message}\n` + logOutput.textContent;
}

function formatDate(value) {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString("vi-VN");
}

function renderJobCard(jobKey, job) {
  const card = document.querySelector(`[data-job="${jobKey}"]`);
  if (!card) {
    return;
  }
  card.querySelector(".job-state").textContent = job.status || "idle";
  card.querySelector(".job-finished").textContent = formatDate(job.last_finished_at || job.last_started_at);
  const runButton = card.querySelector(".run-job-button");
  runButton.disabled = job.status === "running";
  runButton.textContent = job.status === "running" ? "Đang chạy..." : "Chạy ngay";
}

async function requestJson(path, options = {}) {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });

  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json") ? await response.json() : await response.text();

  if (!response.ok) {
    const message = typeof payload === "string" ? payload : payload.detail || "Request failed";
    throw new Error(message);
  }

  return payload;
}

async function checkHealth() {
  setHealthState("loading", "Đang kiểm tra API...");
  try {
    const payload = await requestJson("/api/health");
    setHealthState("ok", `API hoạt động: ${payload.status}`);
    appendLog("Kết nối API thành công.");
  } catch (error) {
    setHealthState("error", "Không kết nối được API");
    appendLog(`Lỗi health check: ${error.message}`);
  }
}

async function refreshJobs() {
  try {
    const payload = await requestJson("/api/jobs");
    Object.entries(payload.jobs).forEach(([jobKey, job]) => renderJobCard(jobKey, job));
  } catch (error) {
    appendLog(`Không tải được trạng thái job: ${error.message}`);
  }
}

async function runJob(jobKey) {
  appendLog(`Đang gọi job: ${jobLabels[jobKey] || jobKey}`);
  try {
    const payload = await requestJson(`/api/jobs/${jobKey}/run`, { method: "POST" });
    appendLog(payload.message || `Đã bắt đầu job ${jobKey}`);
    await refreshJobs();
  } catch (error) {
    appendLog(`Lỗi chạy job ${jobKey}: ${error.message}`);
    await refreshJobs();
  }
}

saveConfigButton.addEventListener("click", () => {
  localStorage.setItem("apiBaseUrl", getApiBaseUrl());
  appendLog(`Đã lưu API base URL: ${getApiBaseUrl()}`);
});

checkHealthButton.addEventListener("click", checkHealth);
clearLogButton.addEventListener("click", () => {
  logOutput.textContent = "Sẵn sàng.";
});

document.querySelectorAll(".run-job-button").forEach((button) => {
  button.addEventListener("click", async (event) => {
    const card = event.currentTarget.closest("[data-job]");
    await runJob(card.dataset.job);
  });
});

document.querySelectorAll(".refresh-job-button").forEach((button) => {
  button.addEventListener("click", async (event) => {
    const card = event.currentTarget.closest("[data-job]");
    const jobKey = card.dataset.job;
    appendLog(`Làm mới trạng thái job: ${jobLabels[jobKey] || jobKey}`);
    await refreshJobs();
  });
});

(async function boot() {
  await checkHealth();
  await refreshJobs();
  window.setInterval(refreshJobs, 7000);
})();
