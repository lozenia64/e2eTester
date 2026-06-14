const STATUS_BADGE_CLASSES = {
    pending: "bg-gray-100 text-gray-600",
    queued: "bg-gray-100 text-gray-600",
    running: "bg-blue-100 text-blue-700",
    waiting_input: "bg-amber-100 text-amber-700",
    passed: "bg-emerald-100 text-emerald-700",
    failed: "bg-red-100 text-red-700",
    blocked: "bg-orange-100 text-orange-700",
    skipped: "bg-slate-200 text-slate-700",
    cancelled: "bg-zinc-200 text-zinc-700",
};

const MODULE_GRAPH_COLUMN_WIDTH = 172;
const MODULE_GRAPH_ROW_HEIGHT = 76;
const MODULE_GRAPH_ROW_GAP = 16;
const MODULE_GRAPH_COLUMN_GAP = 14;

function parseSystemDefinition(form) {
    const script = form.querySelector('[data-role="system-definition"]');
    if (!script) {
        return null;
    }

    try {
        return JSON.parse(script.textContent);
    } catch (error) {
        console.error("시스템 정의 파싱 실패", error);
        return null;
    }
}

function sortModulesByOrder(modules) {
    return [...modules].sort((left, right) => Number(left.order ?? 0) - Number(right.order ?? 0));
}

function buildModuleRelations(modules) {
    const modulesById = new Map(modules.map((module) => [module.module_id, module]));
    const childrenById = new Map(modules.map((module) => [module.module_id, []]));

    for (const module of modules) {
        const dependencies = Array.isArray(module.depends_on) ? module.depends_on : [];
        for (const dependency of dependencies) {
            if (!childrenById.has(dependency)) {
                childrenById.set(dependency, []);
            }
            childrenById.get(dependency).push(module.module_id);
        }
    }

    for (const childIds of childrenById.values()) {
        childIds.sort((left, right) => {
            const leftOrder = Number(modulesById.get(left)?.order ?? 0);
            const rightOrder = Number(modulesById.get(right)?.order ?? 0);
            return leftOrder - rightOrder;
        });
    }

    return { modulesById, childrenById };
}

function computeModuleDepth(moduleId, modulesById, cache = new Map()) {
    if (cache.has(moduleId)) {
        return cache.get(moduleId);
    }

    const module = modulesById.get(moduleId);
    if (!module) {
        return 0;
    }

    const dependencies = Array.isArray(module.depends_on) ? module.depends_on : [];
    const depth = dependencies.length === 0
        ? 0
        : Math.max(...dependencies.map((dependency) => computeModuleDepth(dependency, modulesById, cache))) + 1;
    cache.set(moduleId, depth);
    return depth;
}

function computeModuleSubtreeHeight(moduleId, childrenById, cache = new Map()) {
    if (cache.has(moduleId)) {
        return cache.get(moduleId);
    }

    const childIds = childrenById.get(moduleId) ?? [];
    let height = 1;
    if (childIds.length === 1) {
        height = computeModuleSubtreeHeight(childIds[0], childrenById, cache);
    } else if (childIds.length > 1) {
        height = childIds.reduce(
            (totalHeight, childId) => totalHeight + computeModuleSubtreeHeight(childId, childrenById, cache),
            0,
        );
    }

    cache.set(moduleId, height);
    return height;
}

function buildModuleGraphLayout(modules) {
    const { modulesById, childrenById } = buildModuleRelations(modules);
    const depthCache = new Map();
    const subtreeHeightCache = new Map();
    const layoutByModuleId = new Map();
    const visited = new Set();

    function assignModuleRows(moduleId, row, depth) {
        if (visited.has(moduleId)) {
            return;
        }

        visited.add(moduleId);
        layoutByModuleId.set(moduleId, { depth, row });

        const childIds = childrenById.get(moduleId) ?? [];
        if (childIds.length === 0) {
            return;
        }

        if (childIds.length === 1) {
            assignModuleRows(childIds[0], row, depth + 1);
            return;
        }

        let nextRow = row;
        for (const childId of childIds) {
            assignModuleRows(childId, nextRow, depth + 1);
            nextRow += computeModuleSubtreeHeight(childId, childrenById, subtreeHeightCache);
        }
    }

    const rootModules = modules.filter((module) => (Array.isArray(module.depends_on) ? module.depends_on : []).length === 0);
    let nextRootRow = 0;
    for (const module of rootModules) {
        assignModuleRows(module.module_id, nextRootRow, 0);
        nextRootRow += computeModuleSubtreeHeight(module.module_id, childrenById, subtreeHeightCache);
    }

    for (const [index, module] of modules.entries()) {
        if (layoutByModuleId.has(module.module_id)) {
            continue;
        }
        assignModuleRows(module.module_id, nextRootRow + index, computeModuleDepth(module.module_id, modulesById, depthCache));
    }

    let maxDepth = 0;
    let maxRow = 0;
    for (const [moduleId, position] of layoutByModuleId.entries()) {
        maxDepth = Math.max(maxDepth, position.depth, computeModuleDepth(moduleId, modulesById, depthCache));
        maxRow = Math.max(maxRow, position.row);
    }

    return {
        layoutByModuleId,
        maxDepth,
        maxRow,
    };
}

function createModuleGraphNode(module, position, index) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "module-graph-node is-selected";
    button.dataset.role = "module-graph-node";
    button.dataset.moduleId = module.module_id;
    button.dataset.moduleName = module.name;
    button.dataset.order = String(module.order ?? index + 1);
    button.dataset.dependsOn = JSON.stringify(module.depends_on ?? []);
    button.dataset.depth = String(position.depth);
    button.dataset.row = String(position.row);
    button.dataset.selected = "true";
    button.style.gridColumn = String(position.depth + 1);
    button.style.gridRow = String(position.row + 1);
    button.setAttribute("aria-pressed", "true");

    const header = document.createElement("div");
    header.className = "flex items-center gap-3";

    const order = document.createElement("span");
    order.className = "module-graph-order";
    order.textContent = String(index + 1);
    header.appendChild(order);

    const title = document.createElement("strong");
    title.className = "module-graph-title";
    title.textContent = module.name;
    header.appendChild(title);

    button.appendChild(header);
    button.title = `${index + 1}. ${module.name}`;
    return button;
}

function getModuleGraphNodes(form) {
    return Array.from(form.querySelectorAll('[data-role="module-graph-node"]'));
}

function buildModuleNodeMap(form) {
    return new Map(getModuleGraphNodes(form).map((node) => [node.dataset.moduleId, node]));
}

function buildModuleChildrenMap(nodes) {
    const childrenById = new Map(nodes.map((node) => [node.dataset.moduleId, []]));
    for (const node of nodes) {
        const dependencies = JSON.parse(node.dataset.dependsOn || "[]");
        for (const dependency of dependencies) {
            if (!childrenById.has(dependency)) {
                childrenById.set(dependency, []);
            }
            childrenById.get(dependency).push(node.dataset.moduleId);
        }
    }

    for (const childIds of childrenById.values()) {
        childIds.sort((left, right) => Number((nodes.find((node) => node.dataset.moduleId === left)?.dataset.order) ?? 0) - Number((nodes.find((node) => node.dataset.moduleId === right)?.dataset.order) ?? 0));
    }

    return childrenById;
}

function collectDescendantModuleIds(moduleId, childrenById, collectedIds = new Set()) {
    const childIds = childrenById.get(moduleId) ?? [];
    for (const childId of childIds) {
        if (collectedIds.has(childId)) {
            continue;
        }
        collectedIds.add(childId);
        collectDescendantModuleIds(childId, childrenById, collectedIds);
    }
    return collectedIds;
}

function readNodeDependencyIds(node) {
    return JSON.parse(node.dataset.dependsOn || "[]");
}

function findMissingDependencyIds(node, nodeMap) {
    return readNodeDependencyIds(node).filter((dependencyId) => nodeMap.get(dependencyId)?.dataset.selected !== "true");
}

function getSelectedModuleIds(form) {
    return getModuleGraphNodes(form)
        .filter((node) => node.dataset.selected === "true")
        .sort((left, right) => Number(left.dataset.order) - Number(right.dataset.order))
        .map((node) => node.dataset.moduleId);
}

function readSelectedModuleIdSet(form) {
    return new Set(getSelectedModuleIds(form));
}

function buildModuleSelectionWarnings(form, selectedModuleIds) {
    const nodeMap = buildModuleNodeMap(form);
    const warnings = [];

    for (const moduleId of selectedModuleIds) {
        const node = nodeMap.get(moduleId);
        if (!node) {
            continue;
        }
        const missingDependencies = readNodeDependencyIds(node)
            .filter((dependency) => !selectedModuleIds.has(dependency))
            .map((dependency) => nodeMap.get(dependency)?.dataset.moduleName ?? dependency);
        if (missingDependencies.length === 0) {
            continue;
        }
        warnings.push(`${node.dataset.moduleName}: ${missingDependencies.join(", ")} 선택 필요`);
    }

    return warnings;
}

function drawModuleGraph(form) {
    const canvas = form.querySelector('[data-role="module-graph-canvas"]');
    const grid = form.querySelector('[data-role="module-graph-grid"]');
    const svg = form.querySelector('[data-role="module-graph-edges"]');
    const nodes = getModuleGraphNodes(form);
    if (!canvas || !grid || !svg || nodes.length === 0) {
        return;
    }

    const canvasRect = canvas.getBoundingClientRect();
    svg.innerHTML = "";
    svg.setAttribute("viewBox", `0 0 ${Math.ceil(canvasRect.width)} ${Math.ceil(canvasRect.height)}`);

    const nodeMap = new Map(nodes.map((node) => [node.dataset.moduleId, node]));
    for (const node of nodes) {
        const dependencies = JSON.parse(node.dataset.dependsOn || "[]");
        for (const dependency of dependencies) {
            const sourceNode = nodeMap.get(dependency);
            if (!sourceNode) {
                continue;
            }

            const sourceRect = sourceNode.getBoundingClientRect();
            const targetRect = node.getBoundingClientRect();
            const startX = sourceRect.right - canvasRect.left;
            const startY = sourceRect.top - canvasRect.top + (sourceRect.height / 2);
            const endX = targetRect.left - canvasRect.left;
            const endY = targetRect.top - canvasRect.top + (targetRect.height / 2);
            const controlX = startX + ((endX - startX) / 2);

            const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
            path.setAttribute("d", `M ${startX} ${startY} C ${controlX} ${startY}, ${controlX} ${endY}, ${endX} ${endY}`);
            path.setAttribute("class", "module-graph-edge");

            const isActive = sourceNode.dataset.selected === "true" && node.dataset.selected === "true";
            path.classList.add(isActive ? "is-active" : "is-muted");
            svg.appendChild(path);
        }
    }
}

function updateModuleSelectorState(form, feedbackMessage = "") {
    const summary = form.querySelector('[data-role="module-selection-summary"]');
    const warning = form.querySelector('[data-role="module-selection-warning"]');
    const nodes = getModuleGraphNodes(form);
    const nodeMap = buildModuleNodeMap(form);
    const selectedIds = readSelectedModuleIdSet(form);

    for (const node of nodes) {
        const selected = node.dataset.selected === "true";
        const locked = !selected && findMissingDependencyIds(node, nodeMap).length > 0;
        node.classList.toggle("is-selected", selected);
        node.classList.toggle("is-unselected", !selected);
        node.classList.toggle("is-locked", locked);
        node.setAttribute("aria-pressed", selected ? "true" : "false");
        node.setAttribute("aria-disabled", locked ? "true" : "false");
    }

    const selectedCount = selectedIds.size;
    const totalCount = nodes.length;
    if (summary) {
        summary.textContent = `${selectedCount} / ${totalCount} 선택 · ${totalCount - selectedCount}개 제외`;
    }

    if (warning) {
        const warnings = buildModuleSelectionWarnings(form, selectedIds);
        const message = feedbackMessage || (warnings.length === 0 ? "" : `선행 모듈 누락 가능: ${warnings.join(" / ")}`);
        warning.classList.toggle("is-hidden", message.length === 0);
        warning.textContent = message;
    }

    drawModuleGraph(form);
}

function renderModuleSelector(form) {
    const selector = form.querySelector('[data-role="module-selector"]');
    const canvas = form.querySelector('[data-role="module-graph-canvas"]');
    const grid = form.querySelector('[data-role="module-graph-grid"]');
    const definition = parseSystemDefinition(form);
    if (!selector || !canvas || !grid || !definition?.modules?.length) {
        return;
    }

    const modules = sortModulesByOrder(definition.modules);
    const { layoutByModuleId, maxDepth, maxRow } = buildModuleGraphLayout(modules);

    grid.innerHTML = "";
    for (const [index, module] of modules.entries()) {
        const position = layoutByModuleId.get(module.module_id) ?? { depth: 0, row: index };
        grid.appendChild(createModuleGraphNode(module, position, index));
    }

    canvas.style.width = `${Math.max(modules.length > 0 ? maxDepth + 1 : 1, 1) * MODULE_GRAPH_COLUMN_WIDTH}px`;
    canvas.style.height = `${(Math.max(maxRow + 1, 1) * MODULE_GRAPH_ROW_HEIGHT) + (Math.max(maxRow, 0) * MODULE_GRAPH_ROW_GAP)}px`;
    grid.style.gridTemplateColumns = `repeat(${Math.max(maxDepth + 1, 1)}, minmax(220px, 1fr))`;
    grid.style.gridTemplateRows = `repeat(${Math.max(maxRow + 1, 1)}, ${MODULE_GRAPH_ROW_HEIGHT}px)`;
    grid.style.rowGap = `${MODULE_GRAPH_ROW_GAP}px`;
    grid.style.columnGap = `${MODULE_GRAPH_COLUMN_GAP}px`;

    grid.addEventListener("click", (event) => {
        const button = event.target.closest('[data-role="module-graph-node"]');
        if (!button) {
            return;
        }

        const nodes = getModuleGraphNodes(form);
        const nodeMap = buildModuleNodeMap(form);
        const childrenById = buildModuleChildrenMap(nodes);
        const isSelected = button.dataset.selected === "true";

        if (isSelected) {
            button.dataset.selected = "false";
            const descendantIds = collectDescendantModuleIds(button.dataset.moduleId, childrenById);
            for (const descendantId of descendantIds) {
                const descendantNode = nodeMap.get(descendantId);
                if (descendantNode) {
                    descendantNode.dataset.selected = "false";
                }
            }
            updateModuleSelectorState(form);
            return;
        }

        const missingDependencyIds = findMissingDependencyIds(button, nodeMap);
        if (missingDependencyIds.length > 0) {
            const missingDependencyNames = missingDependencyIds
                .map((dependencyId) => nodeMap.get(dependencyId)?.dataset.moduleName ?? dependencyId)
                .join(", ");
            updateModuleSelectorState(form, `${button.dataset.moduleName}: ${missingDependencyNames} 선택 필요`);
            return;
        }

        button.dataset.selected = "true";
        updateModuleSelectorState(form);
    });

    updateModuleSelectorState(form);
}

function bindModuleSelectors() {
    const forms = document.querySelectorAll(".system-form");
    for (const form of forms) {
        renderModuleSelector(form);
        const details = form.closest("details");
        if (details) {
            details.addEventListener("toggle", () => {
                if (details.open) {
                    window.requestAnimationFrame(() => drawModuleGraph(form));
                }
            });
        }
    }

    let resizeTimer = null;
    window.addEventListener("resize", () => {
        window.clearTimeout(resizeTimer);
        resizeTimer = window.setTimeout(() => {
            for (const form of document.querySelectorAll(".system-form")) {
                drawModuleGraph(form);
            }
        }, 80);
    });
}

async function readErrorMessage(response) {
    try {
        const payload = await response.json();
        return payload.detail ?? JSON.stringify(payload);
    } catch (_error) {
        return await response.text();
    }
}

function statusBadgeClassName(status, sizeClasses = "px-2.5 py-1") {
    const tone = STATUS_BADGE_CLASSES[String(status).toLowerCase()] ?? "bg-gray-100 text-gray-600";
    return `inline-flex items-center rounded-full text-xs font-semibold ${sizeClasses} ${tone}`;
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

    if (awaitingModuleId) {
        const startedAt =
            moduleStartedAtFromRun(runOrMessage, awaitingModuleId) ??
            moduleStartedAtFromRun(runOrMessage.payload, awaitingModuleId);
        startOtpCountdown(startedAt);
    } else {
        stopOtpCountdown();
    }
}

async function startSystemRun(systemCode, button, form) {
    const feedback = form.querySelector('[data-role="form-feedback"]');
    setInlineFeedback(feedback, "");

    const authMethod = form.querySelector('[name="auth_method"]')?.value;
    if (
        (systemCode === "hom" || systemCode === "mhm")
        && authMethod
        && authMethod !== "phone"
        && authMethod !== "kakao"
    ) {
        const systemLabel = systemCode.toUpperCase();
        setInlineFeedback(
            feedback,
            `${systemLabel}에서는 휴대폰인증·카카오인증만 실행할 수 있습니다. 선택한 인증수단은 아직 준비 중입니다.`,
        );
        return;
    }

    const selectedModuleIds = getSelectedModuleIds(form);
    if (selectedModuleIds.length === 0) {
        setInlineFeedback(feedback, "최소 1개 이상의 모듈을 선택해야 합니다.");
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
                selected_module_ids: selectedModuleIds,
            }),
        });

        if (!response.ok) {
            const errorBody = await readErrorMessage(response);
            throw new Error(errorBody || `Run 생성에 실패했습니다. (${response.status})`);
        }

        const run = await response.json();
        window.location.href = `/runs/${run.run_id}`;
    } catch (error) {
        button.disabled = false;
        button.textContent = "실행";
        setInlineFeedback(feedback, error.message.replace(/^Error:\s*/, "") || "Run 생성에 실패했습니다.");
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
    progress.textContent = run.module_skipped
        ? `통과 ${run.module_passed ?? 0}/${run.module_total ?? 0} · 제외 ${run.module_skipped}`
        : `통과 ${run.module_passed ?? 0}/${run.module_total ?? 0}`;
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
    rememberModuleState(module);
    updateRunProgress();

    const card = document.querySelector(`[data-module-id="${module.module_id}"]`);
    if (!card) {
        return;
    }

    const statuses = ["pending", "queued", "running", "waiting_input", "passed", "failed", "blocked", "skipped", "cancelled"];
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

    tickRunningElapsed();
}

const logEntries = [];
let logFilterModuleId = "";
let logSearchText = "";

function logEntryMatchesFilters(entry) {
    if (logFilterModuleId && entry.moduleId !== logFilterModuleId) {
        return false;
    }
    if (logSearchText && !entry.message.toLowerCase().includes(logSearchText)) {
        return false;
    }
    return true;
}

function formatLogLine(entry) {
    return entry.moduleId ? `[${entry.moduleId}] ${entry.message}` : entry.message;
}

function createLogLineNode(entry) {
    const line = document.createElement("div");
    line.className = "log-line";
    line.dataset.moduleId = entry.moduleId;
    line.textContent = formatLogLine(entry);
    return line;
}

function renderLogConsole() {
    const consoleNode = document.getElementById("log-console");
    if (!consoleNode) {
        return;
    }
    const visibleEntries = logEntries.filter(logEntryMatchesFilters);
    consoleNode.innerHTML = "";
    for (const entry of visibleEntries) {
        consoleNode.appendChild(createLogLineNode(entry));
    }
    if (visibleEntries.length === 0) {
        const empty = document.createElement("div");
        empty.className = "log-empty";
        empty.textContent = logEntries.length === 0 ? "아직 출력된 로그가 없습니다." : "조건에 맞는 로그가 없습니다.";
        consoleNode.appendChild(empty);
    }
    consoleNode.scrollTop = consoleNode.scrollHeight;
}

function appendLogEntry(moduleId, message) {
    const entry = { moduleId: moduleId || "", message };
    logEntries.push(entry);
    if (!logEntryMatchesFilters(entry)) {
        return;
    }
    const consoleNode = document.getElementById("log-console");
    if (!consoleNode) {
        return;
    }
    const emptyNode = consoleNode.querySelector(".log-empty");
    if (emptyNode) {
        emptyNode.remove();
    }
    const nearBottom = consoleNode.scrollHeight - consoleNode.scrollTop - consoleNode.clientHeight < 48;
    consoleNode.appendChild(createLogLineNode(entry));
    if (nearBottom) {
        consoleNode.scrollTop = consoleNode.scrollHeight;
    }
}

function loadLogEntriesFromRun(runPayload) {
    logEntries.length = 0;
    const modules = [...(runPayload.modules ?? [])].sort(
        (left, right) => Number(left.order ?? 0) - Number(right.order ?? 0),
    );
    for (const module of modules) {
        for (const line of module.logs ?? []) {
            logEntries.push({ moduleId: module.module_id, message: line });
        }
    }
    renderLogConsole();
}

function logExportText() {
    return logEntries.filter(logEntryMatchesFilters).map(formatLogLine).join("\n");
}

function currentRunId() {
    return document.getElementById("node-grid")?.dataset.runId ?? "run";
}

async function copyLogsToClipboard(button) {
    const text = logExportText();
    if (!text) {
        return;
    }
    const original = button.textContent;
    try {
        await navigator.clipboard.writeText(text);
        button.textContent = "복사됨";
    } catch (error) {
        console.error("로그 복사 실패", error);
        button.textContent = "복사 실패";
    }
    window.setTimeout(() => {
        button.textContent = original;
    }, 1500);
}

function downloadLogs() {
    const text = logExportText();
    if (!text) {
        return;
    }
    const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    const suffix = logFilterModuleId ? `_${logFilterModuleId}` : "";
    anchor.download = `${currentRunId()}${suffix}.log`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
}

function bindLogControls() {
    const filter = document.getElementById("log-filter");
    const search = document.getElementById("log-search");
    const copyButton = document.getElementById("log-copy");
    const downloadButton = document.getElementById("log-download");
    if (filter) {
        filter.addEventListener("change", () => {
            logFilterModuleId = filter.value;
            renderLogConsole();
        });
    }
    if (search) {
        search.addEventListener("input", () => {
            logSearchText = search.value.trim().toLowerCase();
            renderLogConsole();
        });
    }
    if (copyButton) {
        copyButton.addEventListener("click", () => copyLogsToClipboard(copyButton));
    }
    if (downloadButton) {
        downloadButton.addEventListener("click", downloadLogs);
    }
}

const moduleRuntimeState = new Map();

function formatClock(milliseconds) {
    const totalSeconds = Math.max(0, Math.floor(milliseconds / 1000));
    const minutes = String(Math.floor(totalSeconds / 60)).padStart(2, "0");
    const seconds = String(totalSeconds % 60).padStart(2, "0");
    return `${minutes}:${seconds}`;
}

function rememberModuleState(module) {
    moduleRuntimeState.set(module.module_id, {
        status: String(module.status ?? "").toLowerCase(),
        startedAt: module.started_at ?? null,
    });
}

function updateRunProgress() {
    const bar = document.getElementById("run-progress-bar");
    const label = document.getElementById("run-progress-label");
    const detail = document.getElementById("run-progress-detail");
    if (!bar || !label) {
        return;
    }
    const states = [...moduleRuntimeState.values()].map((state) => state.status);
    const total = states.filter((status) => status !== "skipped").length;
    const passed = states.filter((status) => status === "passed").length;
    const failed = states.filter((status) => status === "failed").length;
    const blocked = states.filter((status) => status === "blocked").length;
    const finished = passed + failed + blocked;
    const ratio = total === 0 ? 0 : Math.round((finished / total) * 100);
    bar.style.width = `${ratio}%`;
    bar.classList.toggle("bg-red-500", failed > 0);
    bar.classList.toggle("bg-emerald-500", failed === 0);
    label.textContent = `통과 ${passed}/${total}`;
    if (detail) {
        const parts = [`완료 ${finished}/${total}`];
        if (failed > 0) {
            parts.push(`실패 ${failed}`);
        }
        if (blocked > 0) {
            parts.push(`차단 ${blocked}`);
        }
        detail.textContent = parts.join(" · ");
    }
}

function tickRunningElapsed() {
    const now = Date.now();
    for (const [moduleId, state] of moduleRuntimeState.entries()) {
        const card = document.querySelector(`[data-module-id="${moduleId}"]`);
        if (!card) {
            continue;
        }
        const elapsedNode = card.querySelector('[data-role="module-elapsed"]');
        if (!elapsedNode) {
            continue;
        }
        const isLive = state.status === "running" || state.status === "waiting_input";
        const startedMs = state.startedAt ? new Date(state.startedAt).getTime() : NaN;
        if (isLive && !Number.isNaN(startedMs)) {
            elapsedNode.textContent = `⏱ ${formatClock(now - startedMs)}`;
            elapsedNode.classList.remove("hidden");
        } else {
            elapsedNode.classList.add("hidden");
            elapsedNode.textContent = "";
        }
    }
}

function startRuntimeTicker() {
    if (!document.getElementById("node-grid")) {
        return;
    }
    window.setInterval(tickRunningElapsed, 1000);
}

const OTP_VALIDITY_SECONDS = 180;
let otpCountdownTimer = null;

function clearOtpCountdownTimer() {
    if (otpCountdownTimer) {
        window.clearInterval(otpCountdownTimer);
        otpCountdownTimer = null;
    }
}

function stopOtpCountdown() {
    clearOtpCountdownTimer();
    const node = document.getElementById("otp-countdown");
    if (node) {
        node.classList.add("is-hidden");
        node.textContent = "";
    }
}

function startOtpCountdown(startedAtIso) {
    const node = document.getElementById("otp-countdown");
    if (!node) {
        return;
    }
    clearOtpCountdownTimer();
    const startedMs = startedAtIso ? new Date(startedAtIso).getTime() : Date.now();
    const baselineMs = Number.isNaN(startedMs) ? Date.now() : startedMs;
    node.classList.remove("is-hidden");

    const tick = () => {
        const remaining = OTP_VALIDITY_SECONDS - Math.floor((Date.now() - baselineMs) / 1000);
        if (remaining > 0) {
            node.textContent = `⏳ 인증 유효시간 ${formatClock(remaining * 1000)} 남음`;
            node.classList.remove("bg-red-100", "text-red-700");
            node.classList.add("bg-amber-100", "text-amber-700");
        } else {
            node.textContent = "⚠ 인증 유효시간이 지났을 수 있습니다. 인증을 다시 시도하세요.";
            node.classList.remove("bg-amber-100", "text-amber-700");
            node.classList.add("bg-red-100", "text-red-700");
            clearOtpCountdownTimer();
        }
    };
    tick();
    otpCountdownTimer = window.setInterval(tick, 1000);
}

function moduleStartedAtFromRun(runPayload, moduleId) {
    const module = (runPayload?.modules ?? []).find((item) => item.module_id === moduleId);
    return module?.started_at ?? null;
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

function otpFeedbackNode() {
    return document.querySelector('[data-role="otp-feedback"]');
}

async function submitOtp(runId, otpCode, form) {
    const button = form.querySelector("button[type='submit']");
    const feedback = otpFeedbackNode();
    setInlineFeedback(feedback, "");
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
            const errorBody = await readErrorMessage(response);
            throw new Error(errorBody || `OTP 제출에 실패했습니다. (${response.status})`);
        }

        form.reset();
        setInlineFeedback(feedback, "OTP가 제출되었습니다. 인증 완료까지 잠시 기다려 주세요.", "success");
    } catch (error) {
        setInlineFeedback(feedback, `OTP 제출에 실패했습니다: ${error.message.replace(/^Error:\s*/, "")}`);
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
            setInlineFeedback(otpFeedbackNode(), "OTP 코드를 입력하세요.");
            return;
        }
        submitOtp(runId, otpCode, form);
    });
}

const RUN_ACTIVE_STATUSES = new Set(["pending", "running", "waiting_input"]);

function updateRunActions(status) {
    const normalized = String(status ?? "").toLowerCase();
    const isActive = RUN_ACTIVE_STATUSES.has(normalized);
    const cancelButton = document.getElementById("run-cancel");
    const rerunButton = document.getElementById("run-rerun");
    if (cancelButton) {
        cancelButton.classList.toggle("hidden", !isActive);
        if (!isActive) {
            cancelButton.disabled = false;
            cancelButton.textContent = "실행 취소";
        }
    }
    if (rerunButton) {
        rerunButton.classList.toggle("hidden", isActive);
    }
}

async function cancelRun(button) {
    if (!window.confirm("진행 중인 Run을 취소하시겠습니까? 실행 중인 단계가 끝난 뒤 중단됩니다.")) {
        return;
    }
    button.disabled = true;
    button.textContent = "취소 요청됨...";
    try {
        const response = await fetch(`/api/runs/${currentRunId()}/cancel`, { method: "POST" });
        if (!response.ok) {
            throw new Error(await readErrorMessage(response));
        }
    } catch (error) {
        button.disabled = false;
        button.textContent = "실행 취소";
        showToast(`취소에 실패했습니다: ${error.message}`);
        console.error(error);
    }
}

async function rerunRun(button) {
    button.disabled = true;
    button.textContent = "재실행 중...";
    try {
        const response = await fetch(`/api/runs/${currentRunId()}/rerun`, { method: "POST" });
        if (!response.ok) {
            throw new Error(await readErrorMessage(response));
        }
        const run = await response.json();
        window.location.href = `/runs/${run.run_id}`;
    } catch (error) {
        button.disabled = false;
        button.textContent = "동일 조건으로 재실행";
        showToast(`재실행에 실패했습니다: ${error.message}`);
        console.error(error);
    }
}

function bindRunActions() {
    const cancelButton = document.getElementById("run-cancel");
    const rerunButton = document.getElementById("run-rerun");
    if (cancelButton) {
        cancelButton.addEventListener("click", () => cancelRun(cancelButton));
    }
    if (rerunButton) {
        rerunButton.addEventListener("click", () => rerunRun(rerunButton));
    }
    updateRunActions(document.getElementById("run-status")?.textContent);
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
            updateRunActions(message.payload.status);
            updateOtpPanel(message.payload);
            loadLogEntriesFromRun(message.payload);
            for (const module of message.payload.modules) {
                updateModuleCard(module);
            }
            return;
        }

        if (message.payload.module) {
            updateModuleCard(message.payload.module);
        }

        if (message.event_type === "module_log") {
            appendLogEntry(message.payload.module_id, message.payload.message);
        }

        if (message.run_status) {
            const runStatus = document.getElementById("run-status");
            runStatus.textContent = message.run_status;
            runStatus.className = statusBadgeClassName(message.run_status, "px-3 py-1.5");
            updateRunActions(message.run_status);
        }

        if (message.event_type === "run_waiting_input" || message.event_type === "run_resumed" || message.event_type === "run_finished") {
            updateOtpPanel(message.payload);
        }
    });
}

document.addEventListener("DOMContentLoaded", () => {
    bindModuleSelectors();
    bindSystemButtons();
    bindRunsOverview();
    bindLogControls();
    startRuntimeTicker();
    bindRunActions();
    bindOtpForm();
    bindRunSocket();
});
