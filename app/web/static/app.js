// 상태 라벨·색의 SSOT 는 app/core/status_labels.py 이며,
// 생성물(status.generated.ts)을 main.ts 가 window.__statusBadge 로 노출한다.
function normalizeOutcomeStatus(status) {
    return window.__statusBadge.normalizeTone(status);
}

function statusDisplayLabel(entity) {
    return window.__statusBadge.statusLabel(entity?.status ?? entity ?? "");
}

function isModuleIssueStatus(status) {
    const normalized = normalizeOutcomeStatus(status);
    return normalized === "anomaly" || normalized === "error";
}

async function readErrorMessage(response) {
    try {
        const payload = await response.json();
        return payload.detail ?? JSON.stringify(payload);
    } catch (_error) {
        return await response.text();
    }
}

function statusBadgeClassName(status, sizeClasses = "") {
    void sizeClasses; // 크기는 data-size 로 이관됨 — 호출부 호환을 위해 인자만 유지
    return "status-badge";
}

const FEEDBACK_TONE_CLASSES = {
    error: "text-red-600",
    success: "text-emerald-600",
    info: "text-gray-500",
};

// 폼/패널 안에 인라인 메시지를 표시한다. message 가 비어 있으면 숨긴다.
function setInlineFeedback(element, message, tone = "error") {
    if (!element) {
        return;
    }
    for (const toneClass of Object.values(FEEDBACK_TONE_CLASSES)) {
        element.classList.remove(toneClass);
    }
    if (!message) {
        element.classList.add("is-hidden");
        element.textContent = "";
        return;
    }
    element.classList.add(FEEDBACK_TONE_CLASSES[tone] ?? FEEDBACK_TONE_CLASSES.error);
    element.classList.remove("is-hidden");
    element.textContent = message;
}

const TOAST_TONE_CLASSES = {
    error: "border-red-200 bg-red-50 text-red-700",
    success: "border-emerald-200 bg-emerald-50 text-emerald-700",
    info: "border-gray-200 bg-white text-gray-700",
};

// 자연스러운 인라인 위치가 없는 동작(Run 취소·재실행 등)의 결과를 토스트로 알린다.
function showToast(message, tone = "error") {
    const container = document.getElementById("toast-container");
    if (!container) {
        window.alert(message);
        return;
    }
    const toast = document.createElement("div");
    toast.className = `pointer-events-auto max-w-md rounded-xl border px-4 py-3 text-sm font-medium shadow-lg transition-opacity duration-300 ${TOAST_TONE_CLASSES[tone] ?? TOAST_TONE_CLASSES.error}`;
    toast.setAttribute("role", "alert");
    toast.textContent = message;
    container.appendChild(toast);
    window.setTimeout(() => {
        toast.classList.add("opacity-0");
        window.setTimeout(() => toast.remove(), 300);
    }, 4000);
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
    if (run.triggered_by === "suite") {
        const suiteBadge = document.createElement("span");
        suiteBadge.className = "inline-flex items-center rounded-full bg-violet-100 px-2.5 py-0.5 text-xs font-semibold text-violet-700";
        suiteBadge.textContent = "전체 점검";
        titleRow.appendChild(suiteBadge);
    }
    info.appendChild(titleRow);

    const meta = document.createElement("p");
    meta.className = "mt-0.5 truncate text-xs text-gray-400";
    const metaParts = [run.run_id, formatRunTimestamp(run.requested_at)];
    if (isWaitingInput && run.awaiting_input_prompt) {
        metaParts.push(run.awaiting_input_prompt);
    } else if (isActive && run.current_module_name) {
        metaParts.push(`실행 중 · ${run.current_module_name}`);
    } else if (isModuleIssueStatus(status) && run.failed_module_name) {
        metaParts.push(`${statusDisplayLabel(status)} · ${run.failed_module_name}`);
    }
    meta.textContent = metaParts.filter(Boolean).join(" · ");
    info.appendChild(meta);
    left.appendChild(info);

    const right = document.createElement("div");
    right.className = "flex shrink-0 items-center gap-3";

    const progress = document.createElement("span");
    progress.className = "hidden text-xs font-medium text-gray-500 sm:inline";
    progress.textContent = run.module_skipped
        ? `통과 ${run.module_passed ?? 0}/${run.module_total ?? 0} · 제외 ${run.module_skipped}`
        : `통과 ${run.module_passed ?? 0}/${run.module_total ?? 0}`;
    right.appendChild(progress);

    const statusPill = window.__statusBadge.renderStatusBadge(run.status);
    right.appendChild(statusPill);

    card.appendChild(left);
    card.appendChild(right);
    return card;
}

// ─────────────────────────────────────────────────────────────────────────────
// 진행 중 / 최근 Run: "사용자 실행 단위" 가로 스트립.
// 전체 점검(Suite) 1회 = 1행(Suite 리드 카드 → 시스템별 Run 칩 파이프라인),
// 개별 실행 = 기존 Run 카드 1행. GitLab pipeline mini-graph 패턴을 따라
// 행에서는 결과 요약만 보여 주고 상세는 클릭해 들어간다.
// ─────────────────────────────────────────────────────────────────────────────

// Run 을 실행 단위(suite 그룹 / 개별 run)로 묶는다. runs 는 최신순 입력이므로
// 그룹 순서는 "그 실행에서 가장 최근에 만들어진 Run" 위치를 따른다.
function buildExecutionGroups(runs, suites) {
    const suiteById = new Map((suites ?? []).map((suite) => [suite.suite_id, suite]));
    const groups = [];
    const suiteGroups = new Map();
    for (const run of runs) {
        if (run.suite_id) {
            let group = suiteGroups.get(run.suite_id);
            if (!group) {
                group = { type: "suite", suiteId: run.suite_id, suite: suiteById.get(run.suite_id) ?? null, runs: [] };
                suiteGroups.set(run.suite_id, group);
                groups.push(group);
            }
            group.runs.push(run);
        } else {
            groups.push({ type: "run", runs: [run] });
        }
    }
    for (const group of suiteGroups.values()) {
        // 스텝 실행 순서(왼쪽→오른쪽)로 정렬해 suite → run1 → run2 … 를 만든다.
        group.runs.sort((left, right) => new Date(left.requested_at) - new Date(right.requested_at));
    }
    return groups;
}

function isExecutionGroupActive(group) {
    if (group.type === "suite" && group.suite) {
        return ACTIVE_RUN_STATUSES.has(String(group.suite.status ?? "").toLowerCase());
    }
    return group.runs.some((run) => ACTIVE_RUN_STATUSES.has(String(run.status ?? "").toLowerCase()));
}

// run-chip--* 상태 톤 클래스 키(팔레트는 status-badge 컴포넌트의 톤과 동일).
function runChipToneKey(status) {
    const normalized = normalizeOutcomeStatus(status);
    if (normalized === "waiting_input") {
        return "waiting";
    }
    if (normalized === "queued") {
        return "pending";
    }
    const known = new Set(["pending", "running", "passed", "anomaly", "error", "blocked", "skipped", "cancelled"]);
    return known.has(normalized) ? normalized : "pending";
}

function createRunChip(run) {
    const status = String(run.status ?? "").toLowerCase();
    const chip = document.createElement("a");
    chip.href = `/runs/${run.run_id}`;
    chip.className = `run-chip run-chip--${runChipToneKey(status)}`;
    chip.title = `${run.system_name ?? run.system_code ?? ""} · ${statusDisplayLabel(run)}`;

    const dot = document.createElement("span");
    dot.className = "run-chip__dot";
    dot.setAttribute("aria-hidden", "true");
    chip.appendChild(dot);

    const code = document.createElement("span");
    code.className = "run-chip__code";
    code.textContent = String(run.system_code ?? "").toUpperCase();
    chip.appendChild(code);

    const detail = document.createElement("span");
    detail.className = "run-chip__detail";
    detail.textContent =
        status === "waiting_input" ? "입력 대기" : `${run.module_passed ?? 0}/${run.module_total ?? 0}`;
    chip.appendChild(detail);
    return chip;
}

function createRunChipConnector() {
    const connector = document.createElement("span");
    connector.className = "run-chip-connector";
    connector.setAttribute("aria-hidden", "true");
    return connector;
}

// /api/suites 응답을 못 받았을 때 Run 들만으로 최소 Suite 요약을 유도한다.
function summarizeSuiteFromRuns(runsAsc) {
    const statuses = runsAsc.map((run) => String(run.status ?? "").toLowerCase());
    let status = "passed";
    if (statuses.some((value) => value === "waiting_input")) {
        status = "waiting_input";
    } else if (statuses.some((value) => ACTIVE_RUN_STATUSES.has(value))) {
        status = "running";
    } else if (statuses.some((value) => normalizeOutcomeStatus(value) === "error")) {
        status = "error";
    } else if (statuses.some((value) => normalizeOutcomeStatus(value) === "anomaly")) {
        status = "anomaly";
    } else if (statuses.every((value) => value === "cancelled")) {
        status = "cancelled";
    }
    return {
        status,
        requested_at: runsAsc[0]?.requested_at ?? null,
        step_selected_total: runsAsc.length,
        step_passed: statuses.filter((value) => value === "passed").length,
        step_skipped: 0,
    };
}

function createSuiteStripRow(group) {
    const suite = group.suite ?? summarizeSuiteFromRuns(group.runs);
    const isWaiting = String(suite.status ?? "").toLowerCase() === "waiting_input";

    const strip = document.createElement("div");
    strip.className = `run-strip run-strip--suite${isWaiting ? " run-strip--waiting" : ""}`;

    const lead = document.createElement("a");
    lead.href = `/suites/${group.suiteId}`;
    lead.className = "run-strip__lead";

    const icon = document.createElement("span");
    icon.className = "run-strip__icon";
    icon.setAttribute("aria-hidden", "true");
    icon.innerHTML =
        '<svg class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M4 6h16M4 12h16M4 18h7"/><path stroke-linecap="round" stroke-linejoin="round" d="M16 15l3 3m0 0l3-3m-3 3V9"/></svg>';
    lead.appendChild(icon);

    const leadText = document.createElement("div");
    leadText.className = "run-strip__lead-text";

    const titleRow = document.createElement("div");
    titleRow.className = "run-strip__title-row";

    const codeChip = document.createElement("span");
    codeChip.className = "run-strip__code";
    codeChip.textContent = "SUITE";
    titleRow.appendChild(codeChip);

    const title = document.createElement("h3");
    title.className = "run-strip__title";
    title.textContent = "전체 점검";
    titleRow.appendChild(title);

    const statusPill = window.__statusBadge.renderStatusBadge(suite.status);
    titleRow.appendChild(statusPill);

    if (isWaiting) {
        const waitingBadge = document.createElement("span");
        waitingBadge.className = "inline-flex items-center gap-1 rounded-full bg-amber-500 px-2.5 py-0.5 text-xs font-semibold text-white";
        waitingBadge.textContent = "⚠ 입력 대기 중";
        titleRow.appendChild(waitingBadge);
    }
    leadText.appendChild(titleRow);

    const meta = document.createElement("p");
    meta.className = "run-strip__meta";
    const selectedTotal = suite.step_selected_total ?? group.runs.length;
    const metaParts = [
        group.suiteId,
        formatRunTimestamp(suite.requested_at),
        `통과 ${suite.step_passed ?? 0}/${selectedTotal}`,
    ];
    if (suite.step_skipped) {
        metaParts.push(`제외 ${suite.step_skipped}`);
    }
    meta.textContent = metaParts.filter(Boolean).join(" · ");
    leadText.appendChild(meta);

    lead.appendChild(leadText);
    strip.appendChild(lead);

    const track = document.createElement("div");
    track.className = "run-strip__track";
    group.runs.forEach((run, index) => {
        if (index > 0) {
            track.appendChild(createRunChipConnector());
        }
        track.appendChild(createRunChip(run));
    });

    // 아직 Run 이 만들어지지 않은 남은 스텝은 자리 표시 칩으로 알린다.
    const remaining = selectedTotal - group.runs.length;
    if (remaining > 0) {
        track.appendChild(createRunChipConnector());
        const ghost = document.createElement("span");
        ghost.className = "run-chip run-chip--ghost";
        ghost.textContent = `대기 ${remaining}`;
        track.appendChild(ghost);
    }
    strip.appendChild(track);
    return strip;
}

function renderExecutionGroups(listEl, runs, suites, options = {}) {
    const { activeFirst = false, limit } = options;
    let groups = buildExecutionGroups(runs, suites);
    if (activeFirst) {
        const activeGroups = groups.filter((group) => isExecutionGroupActive(group));
        const finishedGroups = groups.filter((group) => !isExecutionGroupActive(group));
        groups = [...activeGroups, ...finishedGroups];
    }
    if (limit != null) {
        groups = groups.slice(0, limit);
    }
    listEl.innerHTML = "";
    for (const group of groups) {
        listEl.appendChild(group.type === "suite" ? createSuiteStripRow(group) : createRunListItem(group.runs[0]));
    }
    return groups.length;
}

function renderRunList(runs, suites) {
    const section = document.getElementById("runs-section");
    const list = document.getElementById("runs-list");
    if (!section || !list) {
        return;
    }

    const count = renderExecutionGroups(list, runs, suites, { activeFirst: true, limit: RUN_LIST_LIMIT });
    section.classList.toggle("is-hidden", count === 0);
}

async function refreshRunList() {
    try {
        const [runsResult, suitesResult] = await Promise.allSettled([
            fetch("/api/runs?scope=today"),
            fetch("/api/suites"),
        ]);
        if (runsResult.status !== "fulfilled" || !runsResult.value.ok) {
            return;
        }
        const runs = await runsResult.value.json();
        // Suite 요약은 그룹 헤더 강화용 — 실패해도 Run 기반 요약으로 대체한다.
        let suites = [];
        if (suitesResult.status === "fulfilled" && suitesResult.value.ok) {
            suites = await suitesResult.value.json();
        }
        renderRunList(runs, suites);
    } catch (error) {
        console.error("Run 목록 갱신 실패", error);
    }
}

const RUN_HISTORY_LIMIT = 100;

async function bindRunsHistory() {
    const list = document.getElementById("runs-history-list");
    if (!list) {
        return;
    }
    const statusEl = document.getElementById("runs-history-status");
    try {
        const [runsResult, suitesResult] = await Promise.allSettled([
            fetch(`/api/runs?scope=before_today&limit=${RUN_HISTORY_LIMIT}`),
            fetch(`/api/suites?scope=before_today&limit=${RUN_HISTORY_LIMIT}`),
        ]);
        if (runsResult.status !== "fulfilled" || !runsResult.value.ok) {
            if (statusEl) {
                statusEl.textContent = "Run 목록을 불러오지 못했습니다.";
            }
            return;
        }
        const runs = await runsResult.value.json();
        let suites = [];
        if (suitesResult.status === "fulfilled" && suitesResult.value.ok) {
            suites = await suitesResult.value.json();
        }
        const count = renderExecutionGroups(list, runs, suites);
        if (count === 0) {
            if (statusEl) {
                statusEl.textContent = "이전 Run 이력이 없습니다.";
            }
            return;
        }
        if (statusEl) {
            statusEl.classList.add("is-hidden");
        }
    } catch (error) {
        console.error("Run 이력 로드 실패", error);
        if (statusEl) {
            statusEl.textContent = "Run 목록을 불러오지 못했습니다.";
        }
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

const SCHEDULE_LIST_POLL_MS = 15000;

const WEEKDAY_LABELS = { 0: "일", 1: "월", 2: "화", 3: "수", 4: "목", 5: "금", 6: "토" };

// "HH:MM" 24시간 표기를 "오전/오후 h:MM" 한국어 표기로 변환한다.
function formatScheduleTime(value) {
    const [hourRaw, minuteRaw] = String(value ?? "").split(":");
    const hour = Number(hourRaw);
    const minute = Number(minuteRaw);
    if (Number.isNaN(hour) || Number.isNaN(minute)) {
        return null;
    }
    const period = hour < 12 ? "오전" : "오후";
    const hour12 = hour % 12 === 0 ? 12 : hour % 12;
    return `${period} ${hour12}:${String(minute).padStart(2, "0")}`;
}

function getSelectedWeekdays(form) {
    return Array.from(form.querySelectorAll('[data-role="schedule-dow"].is-active'))
        .map((chip) => Number(chip.dataset.dow))
        .sort((left, right) => left - right);
}

// 예약 폼의 친화적 입력값에서 cron 식과 사람이 읽을 요약을 만든다.
// 입력이 불완전하면 { error } 를 반환한다.
function buildScheduleCron(form) {
    const container = form.querySelector('[data-role="schedule-form"]');
    const mode = container?.dataset.mode ?? "daily";

    if (mode === "interval") {
        const unit = container.dataset.intervalUnit ?? "hour";
        const everyRaw = form.querySelector('[data-role="schedule-interval-n"]')?.value;
        const every = Number(everyRaw);
        const max = unit === "minute" ? 59 : 23;
        if (!Number.isInteger(every) || every < 1 || every > max) {
            return { error: `반복 간격은 1~${max} 사이의 값이어야 합니다.` };
        }
        if (unit === "minute") {
            return { cron: `*/${every} * * * *`, summary: `${every}분마다 실행` };
        }
        return { cron: `0 */${every} * * *`, summary: `${every}시간마다 실행` };
    }

    const timeValue = form.querySelector('[data-role="schedule-time"]')?.value;
    const timeText = formatScheduleTime(timeValue);
    if (!timeText) {
        return { error: "실행 시각을 선택하세요." };
    }
    const [hour, minute] = timeValue.split(":").map(Number);

    if (mode === "daily") {
        return { cron: `${minute} ${hour} * * *`, summary: `매일 ${timeText}에 실행` };
    }
    if (mode === "weekdays") {
        return { cron: `${minute} ${hour} * * 1-5`, summary: `평일(월–금) ${timeText}에 실행` };
    }
    if (mode === "weekly") {
        const weekdays = getSelectedWeekdays(form);
        if (weekdays.length === 0) {
            return { error: "실행할 요일을 1개 이상 선택하세요." };
        }
        const labels = weekdays.map((dow) => WEEKDAY_LABELS[dow]).join("·");
        return { cron: `${minute} ${hour} * * ${weekdays.join(",")}`, summary: `매주 ${labels}요일 ${timeText}에 실행` };
    }
    if (mode === "monthly") {
        const dom = Number(container.dataset.dom ?? "1");
        return { cron: `${minute} ${hour} ${dom} * *`, summary: `매월 ${dom}일 ${timeText}에 실행` };
    }

    return { error: "반복 주기를 선택하세요." };
}

// 모드에 따라 관련 컨트롤만 노출한다.
function applyScheduleModeVisibility(form) {
    const container = form.querySelector('[data-role="schedule-form"]');
    const mode = container?.dataset.mode ?? "daily";
    const usesTime = mode === "daily" || mode === "weekdays" || mode === "weekly" || mode === "monthly";

    form.querySelector('[data-role="schedule-weekly"]')?.classList.toggle("is-hidden", mode !== "weekly");
    form.querySelector('[data-role="schedule-monthly"]')?.classList.toggle("is-hidden", mode !== "monthly");
    form.querySelector('[data-role="schedule-interval"]')?.classList.toggle("is-hidden", mode !== "interval");
    form.querySelector('[data-role="schedule-time-wrap"]')?.classList.toggle("is-hidden", !usesTime);
}

function updateSchedulePreview(form) {
    const summaryNode = form.querySelector('[data-role="schedule-summary"]');
    const cronNode = form.querySelector('[data-role="schedule-cron-preview"]');
    const result = buildScheduleCron(form);
    if (summaryNode) {
        summaryNode.textContent = result.error ?? result.summary;
        summaryNode.classList.toggle("text-red-600", Boolean(result.error));
        summaryNode.classList.toggle("text-gray-800", !result.error);
    }
    if (cronNode) {
        cronNode.textContent = result.cron ?? "—";
    }
}

function bindScheduleBuilder(form) {
    const container = form.querySelector('[data-role="schedule-form"]');
    if (!container) {
        return;
    }

    // 매월 날짜 선택지(1~31일) 채우기
    const domSelect = form.querySelector('[data-role="schedule-dom"]');
    if (domSelect && domSelect.options.length === 0) {
        for (let day = 1; day <= 31; day += 1) {
            const option = document.createElement("option");
            option.value = String(day);
            option.textContent = `${day}일`;
            domSelect.appendChild(option);
        }
        domSelect.value = container.dataset.dom ?? "1";
    }

    // 반복 주기 세그먼트
    for (const button of container.querySelectorAll('[data-role="schedule-mode"]')) {
        button.addEventListener("click", () => {
            for (const sibling of container.querySelectorAll('[data-role="schedule-mode"]')) {
                sibling.classList.toggle("is-active", sibling === button);
            }
            container.dataset.mode = button.dataset.mode;
            applyScheduleModeVisibility(form);
            updateSchedulePreview(form);
        });
    }

    // 요일 칩 토글
    for (const chip of container.querySelectorAll('[data-role="schedule-dow"]')) {
        chip.addEventListener("click", () => {
            chip.classList.toggle("is-active");
            chip.setAttribute("aria-pressed", chip.classList.contains("is-active") ? "true" : "false");
            updateSchedulePreview(form);
        });
    }

    // 반복 단위(분/시간) 세그먼트
    const intervalInput = form.querySelector('[data-role="schedule-interval-n"]');
    for (const button of container.querySelectorAll('[data-role="schedule-interval-unit"]')) {
        button.addEventListener("click", () => {
            for (const sibling of container.querySelectorAll('[data-role="schedule-interval-unit"]')) {
                sibling.classList.toggle("is-active", sibling === button);
            }
            container.dataset.intervalUnit = button.dataset.unit;
            if (intervalInput) {
                const max = button.dataset.unit === "minute" ? 59 : 23;
                intervalInput.max = String(max);
                if (Number(intervalInput.value) > max) {
                    intervalInput.value = String(max);
                }
            }
            updateSchedulePreview(form);
        });
    }

    if (domSelect) {
        domSelect.addEventListener("change", () => {
            container.dataset.dom = domSelect.value;
            updateSchedulePreview(form);
        });
    }
    for (const input of container.querySelectorAll('[data-role="schedule-time"], [data-role="schedule-interval-n"]')) {
        input.addEventListener("input", () => updateSchedulePreview(form));
        input.addEventListener("change", () => updateSchedulePreview(form));
    }

    applyScheduleModeVisibility(form);
    updateSchedulePreview(form);
}

function createScheduleActionButton(label, action, scheduleId, extraClasses) {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.scheduleAction = action;
    button.dataset.scheduleId = scheduleId;
    button.className = `inline-flex items-center rounded-lg border px-3 py-1.5 text-xs font-semibold transition disabled:cursor-not-allowed disabled:opacity-60 ${extraClasses}`;
    button.textContent = label;
    return button;
}

function createScheduleListItem(schedule) {
    const card = document.createElement("div");
    card.className = "flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-gray-200 bg-white px-6 py-4 shadow-sm";
    const isSuite = String(schedule.schedule_kind ?? "system").toLowerCase() === "suite";

    const left = document.createElement("div");
    left.className = "flex min-w-0 items-center gap-4";

    const codeChip = document.createElement("span");
    codeChip.className = isSuite
        ? "inline-flex shrink-0 items-center rounded-md bg-violet-50 px-2.5 py-1.5 font-mono text-xs font-semibold text-violet-700 ring-1 ring-inset ring-violet-200"
        : "inline-flex shrink-0 items-center rounded-md bg-indigo-50 px-2.5 py-1.5 font-mono text-xs font-semibold text-indigo-700 ring-1 ring-inset ring-indigo-200";
    codeChip.textContent = isSuite ? "SUITE" : String(schedule.system_code ?? "").toUpperCase();
    left.appendChild(codeChip);

    const info = document.createElement("div");
    info.className = "min-w-0";

    const titleRow = document.createElement("div");
    titleRow.className = "flex flex-wrap items-center gap-2";
    const title = document.createElement("h3");
    title.className = "text-sm font-bold text-gray-900";
    title.textContent = schedule.name || schedule.system_name || schedule.system_code || "";
    titleRow.appendChild(title);
    const cronChip = document.createElement("code");
    cronChip.className = "rounded bg-gray-100 px-1.5 py-0.5 font-mono text-xs text-gray-700";
    cronChip.textContent = schedule.cron ?? "";
    titleRow.appendChild(cronChip);
    if (!schedule.enabled) {
        const offBadge = document.createElement("span");
        offBadge.className = "inline-flex items-center rounded-full bg-gray-200 px-2 py-0.5 text-xs font-semibold text-gray-600";
        offBadge.textContent = "비활성";
        titleRow.appendChild(offBadge);
    }
    info.appendChild(titleRow);

    const meta = document.createElement("p");
    meta.className = "mt-0.5 truncate text-xs text-gray-400";
    const metaParts = [];
    if (schedule.enabled && schedule.next_run_at) {
        metaParts.push(`다음 ${formatRunTimestamp(schedule.next_run_at)}`);
    }
    if (isSuite && schedule.selected_system_count != null) {
        metaParts.push(`시스템 ${schedule.selected_system_count}개 선택`);
    } else if (isSuite && schedule.step_total != null) {
        metaParts.push(`시스템 ${schedule.step_total}개`);
    } else if (schedule.module_count != null) {
        metaParts.push(`모듈 ${schedule.module_count}개`);
    }
    if (!isSuite && schedule.auth_method) {
        metaParts.push(schedule.auth_method);
    }
    if (isSuite && schedule.browser_mode) {
        metaParts.push(schedule.browser_mode);
    }
    if (schedule.timezone) {
        metaParts.push(schedule.timezone);
    }
    meta.textContent = metaParts.filter(Boolean).join(" · ");
    info.appendChild(meta);

    if (isSuite && schedule.last_suite_id) {
        const last = document.createElement("p");
        last.className = "mt-0.5 truncate text-xs text-gray-400";
        last.append("최근 실행: ");
        const link = document.createElement("a");
        link.href = `/suites/${schedule.last_suite_id}`;
        link.className = "font-medium text-violet-600 hover:underline";
        link.textContent = schedule.last_suite_status || schedule.last_suite_id;
        last.appendChild(link);
        if (schedule.last_run_at) {
            last.append(` · ${formatRunTimestamp(schedule.last_run_at)}`);
        }
        info.appendChild(last);
    } else if (schedule.last_run_id) {
        const last = document.createElement("p");
        last.className = "mt-0.5 truncate text-xs text-gray-400";
        last.append("최근 실행: ");
        const link = document.createElement("a");
        link.href = `/runs/${schedule.last_run_id}`;
        link.className = "font-medium text-indigo-600 hover:underline";
        link.textContent = schedule.last_run_status || schedule.last_run_id;
        last.appendChild(link);
        if (schedule.last_run_at) {
            last.append(` · ${formatRunTimestamp(schedule.last_run_at)}`);
        }
        info.appendChild(last);
    }
    left.appendChild(info);

    const right = document.createElement("div");
    right.className = "flex shrink-0 items-center gap-2";
    right.appendChild(createScheduleActionButton("지금 실행", "run-now", schedule.schedule_id, "border-indigo-300 bg-white text-indigo-700 hover:bg-indigo-50"));
    if (schedule.trigger_token) {
        const copyButton = createScheduleActionButton("모바일 URL", "copy-mobile-url", schedule.schedule_id, "border-emerald-300 bg-white text-emerald-700 hover:bg-emerald-50");
        copyButton.dataset.triggerToken = schedule.trigger_token;
        right.appendChild(copyButton);
    }
    right.appendChild(createScheduleActionButton(schedule.enabled ? "비활성화" : "활성화", "toggle", schedule.schedule_id, "border-gray-300 bg-white text-gray-700 hover:bg-gray-50"));
    right.appendChild(createScheduleActionButton("삭제", "delete", schedule.schedule_id, "border-red-300 bg-white text-red-600 hover:bg-red-50"));

    card.appendChild(left);
    card.appendChild(right);
    return card;
}

function renderScheduleList(schedules) {
    const section = document.getElementById("schedules-section");
    const list = document.getElementById("schedules-list");
    if (!section || !list) {
        return;
    }
    section.classList.toggle("is-hidden", schedules.length === 0);
    list.innerHTML = "";
    for (const schedule of schedules) {
        list.appendChild(createScheduleListItem(schedule));
    }
}

async function refreshScheduleList() {
    try {
        const response = await fetch("/api/schedules");
        if (!response.ok) {
            return;
        }
        renderScheduleList(await response.json());
    } catch (error) {
        console.error("예약 목록 갱신 실패", error);
    }
}

async function handleScheduleAction(event) {
    const button = event.target.closest("[data-schedule-action]");
    if (!button) {
        return;
    }
    const action = button.dataset.scheduleAction;
    const scheduleId = button.dataset.scheduleId;
    if (action === "delete" && !window.confirm("이 예약을 삭제하시겠습니까?")) {
        return;
    }
    if (action === "copy-mobile-url") {
        const mobileUrl = `${window.location.origin}/m/${button.dataset.triggerToken}`;
        try {
            await navigator.clipboard.writeText(mobileUrl);
            showToast("모바일 즉시 점검 URL을 복사했습니다. 접속만 하면 이 예약의 점검이 실행됩니다.");
        } catch (error) {
            window.prompt("아래 모바일 즉시 점검 URL을 직접 복사하세요.", mobileUrl);
        }
        return;
    }

    button.disabled = true;
    try {
        let response;
        if (action === "toggle") {
            response = await fetch(`/api/schedules/${scheduleId}/toggle`, { method: "POST" });
        } else if (action === "run-now") {
            response = await fetch(`/api/schedules/${scheduleId}/run-now`, { method: "POST" });
        } else if (action === "delete") {
            response = await fetch(`/api/schedules/${scheduleId}`, { method: "DELETE" });
        }
        if (!response || !response.ok) {
            throw new Error(response ? await readErrorMessage(response) : "알 수 없는 동작입니다.");
        }
        if (action === "run-now") {
            const result = await response.json();
            if (String(result.schedule_kind ?? "").toLowerCase() === "suite" && result.suite_id) {
                window.location.href = `/suites/${result.suite_id}`;
            } else if (result.run_id) {
                window.location.href = `/runs/${result.run_id}`;
            }
            return;
        }
        refreshScheduleList();
    } catch (error) {
        button.disabled = false;
        showToast(`예약 처리에 실패했습니다: ${error.message.replace(/^Error:\s*/, "")}`);
        console.error(error);
    }
}

function bindSchedulesOverview() {
    const list = document.getElementById("schedules-list");
    if (!list) {
        return;
    }
    list.addEventListener("click", handleScheduleAction);
    refreshScheduleList();
    setInterval(() => {
        if (!document.hidden) {
            refreshScheduleList();
        }
    }, SCHEDULE_LIST_POLL_MS);
}

// Cycle 4까지 남는 공용 일정·피드백 보조 함수의 TypeScript 실행 화면 경계.
window.__executeLegacy = {
    setInlineFeedback,
    readErrorMessage,
    bindScheduleBuilder,
    buildScheduleCron,
    refreshScheduleList,
};

document.addEventListener("DOMContentLoaded", () => {
    bindRunsOverview();
    bindRunsHistory();
    bindSchedulesOverview();
});
