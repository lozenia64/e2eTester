const STATUS_BADGE_CLASSES = {
    pending: "bg-gray-100 text-gray-600",
    queued: "bg-gray-100 text-gray-600",
    running: "bg-blue-100 text-blue-700",
    waiting_input: "bg-amber-100 text-amber-700",
    passed: "bg-emerald-100 text-emerald-700",
    failed: "bg-red-100 text-red-700",
    blocked: "bg-orange-100 text-orange-700",
};

function statusBadgeClassName(status, sizeClasses = "px-2.5 py-1") {
    const tone = STATUS_BADGE_CLASSES[String(status).toLowerCase()] ?? "bg-gray-100 text-gray-600";
    return `inline-flex items-center rounded-full text-xs font-semibold ${sizeClasses} ${tone}`;
}

function collectFormInput(form) {
    const formData = new FormData(form);
    const inputData = {};
    for (const [key, value] of formData.entries()) {
        inputData[key] = String(value).trim();
    }
    return inputData;
}

function syncConditionalFields(form) {
    const conditionalFields = form.querySelectorAll(".conditional-field");
    for (const field of conditionalFields) {
        const controllingKey = field.dataset.showWhenKey;
        const expectedRaw = field.dataset.showWhenValue || "";
        const expectedValues = expectedRaw.split(",").map((s) => s.trim()).filter(Boolean);
        const controllingInput = form.querySelector(`[name="${controllingKey}"]`);
        const input = field.querySelector("input, select, textarea");
        const isVisible =
            controllingInput && input && expectedValues.includes(controllingInput.value);

        field.classList.toggle("is-hidden", !isVisible);
        if (!input) {
            continue;
        }

        input.disabled = !isVisible;
        input.required = isVisible && field.dataset.required === "true";
    }
}

function bindConditionalFields(form) {
    const controllingKeys = new Set(
        Array.from(form.querySelectorAll(".conditional-field"))
            .map((field) => field.dataset.showWhenKey)
            .filter(Boolean),
    );

    for (const key of controllingKeys) {
        const input = form.querySelector(`[name="${key}"]`);
        if (!input) {
            continue;
        }
        const sync = () => syncConditionalFields(form);
        input.addEventListener("change", sync);
        input.addEventListener("input", sync);
    }

    syncConditionalFields(form);
}

function updateOtpPanel(runOrMessage) {
    const panel = document.getElementById("otp-panel");
    if (!panel) {
        return;
    }

    const awaitingModuleId = runOrMessage.awaiting_input_module_id ?? runOrMessage.payload?.awaiting_input_module_id ?? "";
    const prompt = runOrMessage.awaiting_input_prompt ?? runOrMessage.payload?.awaiting_input_prompt ?? "인증문자 발송 후 OTP 입력이 필요하면 이 영역이 활성화됩니다.";
    panel.dataset.awaitingModuleId = awaitingModuleId;
    document.getElementById("otp-prompt").textContent = prompt;
    panel.classList.toggle("is-hidden", !awaitingModuleId);
}

async function startSystemRun(systemCode, button, form) {
    const authMethod = form.querySelector('[name="auth_method"]')?.value;
    if (authMethod && authMethod !== "phone" && authMethod !== "kakao") {
        window.alert(
            "HOM에서는 휴대폰인증·카카오인증만 실행할 수 있습니다. 선택한 인증수단은 아직 준비 중입니다.",
        );
        return;
    }

    button.disabled = true;
    button.textContent = "실행 중...";

    try {
        const response = await fetch(`/api/runs/systems/${systemCode}`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                input_data: collectFormInput(form),
            }),
        });

        if (!response.ok) {
            const errorBody = await response.text();
            throw new Error(`Run creation failed: ${response.status} ${errorBody}`);
        }

        const run = await response.json();
        window.location.href = `/runs/${run.run_id}`;
    } catch (error) {
        button.disabled = false;
        button.textContent = "실행";
        window.alert("Run 생성에 실패했습니다. 콘솔을 확인하세요.");
        console.error(error);
    }
}

const ACTIVE_RUN_STATUSES = new Set(["pending", "running", "waiting_input"]);
const RUN_LIST_LIMIT = 8;
const RUN_LIST_POLL_MS = 5000;

function formatRunTimestamp(isoString) {
    if (!isoString) {
        return "";
    }
    const date = new Date(isoString);
    if (Number.isNaN(date.getTime())) {
        return "";
    }
    const now = new Date();
    const sameDay =
        date.getFullYear() === now.getFullYear() &&
        date.getMonth() === now.getMonth() &&
        date.getDate() === now.getDate();
    const time = date.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
    if (sameDay) {
        return `오늘 ${time}`;
    }
    const day = date.toLocaleDateString("ko-KR", { month: "2-digit", day: "2-digit" });
    return `${day} ${time}`;
}

function createRunListItem(run) {
    const status = String(run.status ?? "").toLowerCase();
    const isWaitingInput = status === "waiting_input";
    const isActive = ACTIVE_RUN_STATUSES.has(status);

    const card = document.createElement("a");
    card.href = `/runs/${run.run_id}`;
    card.className = isWaitingInput
        ? "flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-amber-300 bg-amber-50 px-6 py-4 shadow-sm transition hover:border-amber-400 hover:bg-amber-100"
        : "flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-gray-200 bg-white px-6 py-4 shadow-sm transition hover:border-indigo-200 hover:bg-gray-50";

    const left = document.createElement("div");
    left.className = "flex min-w-0 items-center gap-4";

    const codeChip = document.createElement("span");
    codeChip.className = "inline-flex shrink-0 items-center rounded-md bg-indigo-50 px-2.5 py-1.5 font-mono text-xs font-semibold text-indigo-700 ring-1 ring-inset ring-indigo-200";
    codeChip.textContent = String(run.system_code ?? "").toUpperCase();
    left.appendChild(codeChip);

    const info = document.createElement("div");
    info.className = "min-w-0";

    const titleRow = document.createElement("div");
    titleRow.className = "flex flex-wrap items-center gap-2";

    const title = document.createElement("h3");
    title.className = "text-sm font-bold text-gray-900";
    title.textContent = run.system_name ?? run.system_code ?? "";
    titleRow.appendChild(title);

    if (isWaitingInput) {
        const waitingBadge = document.createElement("span");
        waitingBadge.className = "inline-flex items-center gap-1 rounded-full bg-amber-500 px-2.5 py-0.5 text-xs font-semibold text-white";
        waitingBadge.textContent = "⚠ 입력 대기 중";
        titleRow.appendChild(waitingBadge);
    }
    info.appendChild(titleRow);

    const meta = document.createElement("p");
    meta.className = "mt-0.5 truncate text-xs text-gray-400";
    const metaParts = [run.run_id, formatRunTimestamp(run.requested_at)];
    if (isWaitingInput && run.awaiting_input_prompt) {
        metaParts.push(run.awaiting_input_prompt);
    } else if (isActive && run.current_module_name) {
        metaParts.push(`실행 중 · ${run.current_module_name}`);
    } else if (status === "failed" && run.failed_module_name) {
        metaParts.push(`실패 · ${run.failed_module_name}`);
    }
    meta.textContent = metaParts.filter(Boolean).join(" · ");
    info.appendChild(meta);
    left.appendChild(info);

    const right = document.createElement("div");
    right.className = "flex shrink-0 items-center gap-3";

    const progress = document.createElement("span");
    progress.className = "hidden text-xs font-medium text-gray-500 sm:inline";
    progress.textContent = `모듈 ${run.module_passed ?? 0}/${run.module_total ?? 0} 통과`;
    right.appendChild(progress);

    const statusPill = document.createElement("span");
    statusPill.className = statusBadgeClassName(run.status);
    statusPill.textContent = run.status ?? "";
    right.appendChild(statusPill);

    card.appendChild(left);
    card.appendChild(right);
    return card;
}

function renderRunList(runs) {
    const section = document.getElementById("runs-section");
    const list = document.getElementById("runs-list");
    if (!section || !list) {
        return;
    }

    const activeRuns = runs.filter((run) => ACTIVE_RUN_STATUSES.has(String(run.status ?? "").toLowerCase()));
    const finishedRuns = runs.filter((run) => !ACTIVE_RUN_STATUSES.has(String(run.status ?? "").toLowerCase()));
    const visibleRuns = [...activeRuns, ...finishedRuns].slice(0, RUN_LIST_LIMIT);

    section.classList.toggle("is-hidden", visibleRuns.length === 0);
    list.innerHTML = "";
    for (const run of visibleRuns) {
        list.appendChild(createRunListItem(run));
    }
}

async function refreshRunList() {
    try {
        const response = await fetch("/api/runs");
        if (!response.ok) {
            return;
        }
        renderRunList(await response.json());
    } catch (error) {
        console.error("Run 목록 갱신 실패", error);
    }
}

function bindRunsOverview() {
    if (!document.getElementById("runs-list")) {
        return;
    }
    refreshRunList();
    setInterval(() => {
        if (!document.hidden) {
            refreshRunList();
        }
    }, RUN_LIST_POLL_MS);
}

function updateModuleCard(module) {
    const card = document.querySelector(`[data-module-id="${module.module_id}"]`);
    if (!card) {
        return;
    }

    const statuses = ["pending", "queued", "running", "waiting_input", "passed", "failed", "blocked"];
    for (const status of statuses) {
        card.classList.remove(`status-${status}`);
    }
    card.classList.add(`status-${module.status.toLowerCase()}`);

    const statusNode = card.querySelector('[data-role="module-status"]');
    statusNode.className = statusBadgeClassName(module.status);
    statusNode.textContent = module.status;

    card.querySelector('[data-role="module-message"]').textContent = module.message;
    card.querySelector('[data-role="module-duration"]').textContent = `${module.duration_ms ?? 0} ms`;
    card.querySelector('[data-role="module-artifacts"]').textContent = `${module.artifact_count}`;

    const analysisPanel = card.querySelector('[data-role="failure-analysis"]');
    const analysis = module.failure_analysis;
    if (analysisPanel) {
        analysisPanel.classList.toggle("is-hidden", !analysis);
        card.querySelector('[data-role="analysis-category"]').textContent = analysis?.category ?? "";
        card.querySelector('[data-role="analysis-summary"]').textContent = analysis?.user_summary ?? "";
        card.querySelector('[data-role="analysis-action"]').textContent = analysis?.recommended_action ?? "";
        card.querySelector('[data-role="analysis-details"]').textContent = analysis?.developer_details ?? "";
    }

    const artifactList = card.querySelector('[data-role="module-artifacts-list"]');
    artifactList.innerHTML = "";
    for (const artifact of module.artifacts ?? []) {
        const link = document.createElement("a");
        link.href = artifact;
        link.target = "_blank";
        link.rel = "noreferrer";
        link.className = "truncate font-medium text-indigo-600 hover:underline";
        link.textContent = artifact.split("/").pop();
        artifactList.appendChild(link);
    }
}

function appendLogLine(text) {
    const consoleNode = document.getElementById("log-console");
    if (!consoleNode) {
        return;
    }
    const line = document.createElement("div");
    line.className = "log-line";
    line.textContent = text;
    consoleNode.appendChild(line);
    consoleNode.scrollTop = consoleNode.scrollHeight;
}

function bindSystemButtons() {
    const forms = document.querySelectorAll(".system-form");
    for (const form of forms) {
        bindConditionalFields(form);
        form.addEventListener("submit", (event) => {
            event.preventDefault();
            const button = form.querySelector("button[type='submit']");
            startSystemRun(form.dataset.systemCode, button, form);
        });
    }
}

async function submitOtp(runId, otpCode, form) {
    const button = form.querySelector("button[type='submit']");
    button.disabled = true;
    button.textContent = "제출 중...";

    try {
        const response = await fetch(`/api/runs/${runId}/otp`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({ otp_code: otpCode }),
        });

        if (!response.ok) {
            const errorBody = await response.text();
            throw new Error(`OTP submit failed: ${response.status} ${errorBody}`);
        }

        form.reset();
    } catch (error) {
        window.alert("OTP 제출에 실패했습니다. 콘솔을 확인하세요.");
        console.error(error);
    } finally {
        button.disabled = false;
        button.textContent = "OTP 제출";
    }
}

function bindOtpForm() {
    const form = document.getElementById("otp-form");
    const panel = document.getElementById("otp-panel");
    if (!form || !panel) {
        return;
    }

    form.addEventListener("submit", (event) => {
        event.preventDefault();
        const runId = panel.dataset.runId;
        const otpCode = String(new FormData(form).get("otp_code") || "").trim();
        if (!otpCode) {
            window.alert("OTP 코드를 입력하세요.");
            return;
        }
        submitOtp(runId, otpCode, form);
    });
}

function bindRunSocket() {
    const grid = document.getElementById("node-grid");
    if (!grid) {
        return;
    }

    const runId = grid.dataset.runId;
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const socket = new WebSocket(`${protocol}://${window.location.host}/ws/runs/${runId}`);

    socket.addEventListener("message", (event) => {
        const message = JSON.parse(event.data);

        if (message.event_type === "snapshot") {
            document.getElementById("run-status").textContent = message.payload.status;
            document.getElementById("run-status").className = statusBadgeClassName(message.payload.status, "px-3 py-1.5");
            updateOtpPanel(message.payload);
            for (const module of message.payload.modules) {
                updateModuleCard(module);
            }
            return;
        }

        if (message.payload.module) {
            updateModuleCard(message.payload.module);
        }

        if (message.event_type === "module_log") {
            appendLogLine(`[${message.payload.module_id}] ${message.payload.message}`);
        }

        if (message.run_status) {
            const runStatus = document.getElementById("run-status");
            runStatus.textContent = message.run_status;
            runStatus.className = statusBadgeClassName(message.run_status, "px-3 py-1.5");
        }

        if (message.event_type === "run_waiting_input" || message.event_type === "run_resumed" || message.event_type === "run_finished") {
            updateOtpPanel(message.payload);
        }
    });
}

document.addEventListener("DOMContentLoaded", () => {
    bindSystemButtons();
    bindRunsOverview();
    bindOtpForm();
    bindRunSocket();
});
