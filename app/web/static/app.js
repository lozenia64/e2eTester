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

const MODULE_GRAPH_MIN_ROW_HEIGHT = 26;
const MODULE_GRAPH_MAX_ROW_HEIGHT = 40;
const MODULE_GRAPH_MIN_GAP = 4;
const MODULE_GRAPH_MAX_GAP = 6;
const MODULE_GRAPH_MAX_VIEWPORT_HEIGHT = 200;
const moduleGraphResizeObservers = new WeakMap();

function computeModuleGraphMetrics(columnCount, rowCount, availableWidth, availableHeight) {
    let rowGap = MODULE_GRAPH_MAX_GAP;
    let columnGap = MODULE_GRAPH_MAX_GAP;
    let rowHeight = MODULE_GRAPH_MAX_ROW_HEIGHT;

    const totalHeight = (height, gap) => (rowCount * height) + (Math.max(rowCount - 1, 0) * gap);

    if (totalHeight(rowHeight, rowGap) > availableHeight) {
        const gapSpace = Math.max(rowCount - 1, 0) * rowGap;
        rowHeight = Math.floor((availableHeight - gapSpace) / rowCount);
        rowHeight = Math.max(MODULE_GRAPH_MIN_ROW_HEIGHT, Math.min(MODULE_GRAPH_MAX_ROW_HEIGHT, rowHeight));
    }

    if (totalHeight(rowHeight, rowGap) > availableHeight && rowCount > 1) {
        rowGap = Math.floor((availableHeight - (rowCount * rowHeight)) / (rowCount - 1));
        rowGap = Math.max(MODULE_GRAPH_MIN_GAP, Math.min(MODULE_GRAPH_MAX_GAP, rowGap));
    }

    if (columnCount >= 8) {
        rowHeight = Math.min(rowHeight, 28);
        columnGap = MODULE_GRAPH_MIN_GAP;
    } else if (columnCount >= 5) {
        rowHeight = Math.min(rowHeight, 32);
        columnGap = Math.min(columnGap, 5);
    }

    if (availableWidth > 0 && columnCount > 1) {
        const minColumnWidth = 44;
        const widthLimitedGap = Math.floor(
            (availableWidth - (columnCount * minColumnWidth)) / (columnCount - 1),
        );
        if (widthLimitedGap < columnGap) {
            columnGap = Math.max(MODULE_GRAPH_MIN_GAP, widthLimitedGap);
        }
    }

    return { rowHeight, rowGap, columnGap };
}

function ensureModuleGraphResizeObserver(form) {
    const viewport = form.querySelector(".module-graph-viewport");
    if (!viewport || moduleGraphResizeObservers.has(viewport)) {
        return;
    }

    const observer = new ResizeObserver(() => {
        window.requestAnimationFrame(() => {
            fitModuleGraphToViewport(form);
            drawModuleGraph(form);
        });
    });
    observer.observe(viewport);
    moduleGraphResizeObservers.set(viewport, observer);
}

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
    header.className = "module-graph-node__header";

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

function fitModuleGraphToViewport(form) {
    const viewport = form.querySelector(".module-graph-viewport");
    const canvas = form.querySelector('[data-role="module-graph-canvas"]');
    const grid = form.querySelector('[data-role="module-graph-grid"]');
    if (!viewport || !canvas || !grid) {
        return;
    }

    const columnCount = Math.max(Number(canvas.dataset.columnCount) || 1, 1);
    const rowCount = Math.max(Number(canvas.dataset.rowCount) || 1, 1);
    const availableWidth = viewport.clientWidth || viewport.getBoundingClientRect().width;
    const availableHeight = MODULE_GRAPH_MAX_VIEWPORT_HEIGHT;
    const { rowHeight, rowGap, columnGap } = computeModuleGraphMetrics(
        columnCount,
        rowCount,
        availableWidth,
        availableHeight,
    );
    const canvasHeight = (rowCount * rowHeight) + (Math.max(rowCount - 1, 0) * rowGap);

    canvas.style.width = "100%";
    canvas.style.height = `${canvasHeight}px`;
    grid.style.gridTemplateColumns = `repeat(${columnCount}, minmax(0, 1fr))`;
    grid.style.gridTemplateRows = `repeat(${rowCount}, ${rowHeight}px)`;
    grid.style.rowGap = `${rowGap}px`;
    grid.style.columnGap = `${columnGap}px`;

    viewport.dataset.graphCompact = columnCount >= 8 ? "dense" : columnCount >= 5 ? "compact" : "";
    ensureModuleGraphResizeObserver(form);
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

    const columnCount = Math.max(maxDepth + 1, 1);
    const rowCount = Math.max(maxRow + 1, 1);
    canvas.dataset.columnCount = String(columnCount);
    canvas.dataset.rowCount = String(rowCount);
    fitModuleGraphToViewport(form);

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
                    window.requestAnimationFrame(() => {
                        fitModuleGraphToViewport(form);
                        drawModuleGraph(form);
                    });
                }
            });
        }
    }

    let resizeTimer = null;
    window.addEventListener("resize", () => {
        window.clearTimeout(resizeTimer);
        resizeTimer = window.setTimeout(() => {
            for (const form of document.querySelectorAll(".system-form")) {
                fitModuleGraphToViewport(form);
                drawModuleGraph(form);
            }
        }, 80);
    });
}

function bindSystemCardExpand() {
    const section = document.getElementById("suite-section");
    if (!section) {
        return;
    }
    const systemCards = section.querySelectorAll("details.system-card:not(.system-card--suite)");
    for (const card of systemCards) {
        card.addEventListener("toggle", () => {
            if (!card.open) {
                return;
            }
            for (const sibling of systemCards) {
                if (sibling !== card) {
                    sibling.open = false;
                }
            }
        });
    }
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

function collectFormInput(form) {
    const formData = new FormData(form);
    const inputData = {};
    for (const [key, value] of formData.entries()) {
        inputData[key] = String(value).trim();
    }
    return inputData;
}

// ===== 인증 프리셋 (내 점검 세트) =====================================
// 사용자별·시스템별 인증 수단/정보 저장 세트. 개별 점검에서는 폼을 원클릭으로 채우고,
// 전체 점검에서는 시스템별로 프리셋을 골라 인증 정보를 공급한다.

let presetsBySystem = {};
// 전체 점검에서 시스템별로 고른 프리셋 id: systemCode -> preset_id
const suitePresetSelection = new Map();

const AUTH_METHOD_LABELS = {
    phone: "휴대폰인증",
    kakao: "카카오인증",
    finance_certificate: "금융인증서",
    public_certificate: "공동인증서",
};

function authMethodLabel(method) {
    return AUTH_METHOD_LABELS[method] ?? (method || "인증");
}

function presetSummaryText(preset) {
    const parts = [authMethodLabel(preset.auth_method)];
    const data = preset.input_data ?? {};
    if (data.name) {
        parts.push(data.name);
    }
    if (data.phone_number) {
        parts.push(data.phone_number);
    }
    return parts.join(" · ");
}

async function loadPresets() {
    // 프리셋 UI 가 없는 화면(대시보드 등)에서는 조용히 종료.
    if (!document.querySelector('[data-role="preset-panel"], [data-role="suite-preset-list"]')) {
        return;
    }
    try {
        const response = await fetch("/api/presets");
        if (!response.ok) {
            throw new Error(`프리셋 조회 실패 (${response.status})`);
        }
        const presets = await response.json();
        presetsBySystem = {};
        for (const preset of presets) {
            (presetsBySystem[preset.system_code] ??= []).push(preset);
        }
    } catch (error) {
        console.error(error);
        presetsBySystem = {};
    }
    renderAllPresetUI();
}

function renderAllPresetUI() {
    renderIndividualPresetPanels();
    renderSuitePresetLists();
    const suiteForm = document.getElementById("suite-form");
    if (suiteForm) {
        updateSuiteSystemSelectorState(suiteForm);
    }
}

// ----- 개별 점검 카드의 프리셋 칩 --------------------------------------
function renderIndividualPresetPanels() {
    for (const panel of document.querySelectorAll('[data-role="preset-panel"]')) {
        const systemCode = panel.dataset.systemCode;
        const list = panel.querySelector('[data-role="preset-list"]');
        const form = panel.closest("form");
        if (!list || !form) {
            continue;
        }
        list.dataset.loading = "false";
        list.innerHTML = "";
        const presets = presetsBySystem[systemCode] ?? [];
        if (presets.length === 0) {
            const empty = document.createElement("span");
            empty.className = "preset-empty";
            empty.textContent = "저장된 프리셋이 없습니다. 아래에 정보를 입력한 뒤 저장하면 다음부터 원클릭으로 불러옵니다.";
            list.appendChild(empty);
            continue;
        }
        for (const preset of presets) {
            list.appendChild(buildPresetChip(preset, form));
        }
    }
}

function buildPresetChip(preset, form) {
    const chip = document.createElement("div");
    chip.className = "preset-chip";
    chip.dataset.presetId = preset.preset_id;

    const apply = document.createElement("button");
    apply.type = "button";
    apply.className = "preset-chip__apply";
    apply.title = "이 프리셋으로 폼을 채웁니다";
    apply.innerHTML = `<span class="preset-chip__name"></span><span class="preset-chip__meta"></span>`;
    apply.querySelector(".preset-chip__name").textContent = preset.name;
    apply.querySelector(".preset-chip__meta").textContent = presetSummaryText(preset);
    apply.addEventListener("click", () => {
        applyPresetToForm(form, preset);
        chip.classList.add("preset-chip--just-applied");
        window.setTimeout(() => chip.classList.remove("preset-chip--just-applied"), 900);
        const feedback = form.querySelector('[data-role="preset-feedback"]');
        setInlineFeedback(feedback, `‘${preset.name}’ 프리셋을 적용했습니다.`, "success");
    });

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "preset-chip__delete";
    remove.title = "프리셋 삭제";
    remove.setAttribute("aria-label", `${preset.name} 프리셋 삭제`);
    remove.innerHTML = `<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"/></svg>`;
    remove.addEventListener("click", async (event) => {
        event.stopPropagation();
        if (!window.confirm(`‘${preset.name}’ 프리셋을 삭제할까요?`)) {
            return;
        }
        await deletePresetById(preset.preset_id, form);
    });

    chip.append(apply, remove);
    return chip;
}

function applyPresetToForm(form, preset) {
    const data = preset.input_data ?? {};
    // auth_method 를 먼저 반영해야 조건부 필드(show_when)의 표시/숨김이 올바르게 계산된다.
    const keys = Object.keys(data).sort((left, right) => {
        if (left === "auth_method") return -1;
        if (right === "auth_method") return 1;
        return 0;
    });
    for (const key of keys) {
        // browser_mode 는 프리셋에 저장하지 않으며, 적용 시에도 현재 폼 선택을 유지한다.
        if (key === "browser_mode") {
            continue;
        }
        const field = form.querySelector(`[name="${key}"]`);
        if (field) {
            field.value = data[key];
        }
    }
    syncConditionalFields(form);
    applyModuleSelection(form, preset.selected_module_ids ?? null);
}

function applyModuleSelection(form, moduleIds) {
    const nodes = getModuleGraphNodes(form);
    if (nodes.length === 0) {
        return;
    }
    if (moduleIds == null) {
        for (const node of nodes) {
            node.dataset.selected = "true";
        }
    } else {
        const selected = new Set(moduleIds);
        for (const node of nodes) {
            node.dataset.selected = selected.has(node.dataset.moduleId) ? "true" : "false";
        }
    }
    updateModuleSelectorState(form);
}

async function submitPresetSave(systemCode, form, nameInput, saveForm, feedback, confirmButton) {
    const name = String(nameInput.value ?? "").trim();
    if (!name) {
        setInlineFeedback(feedback, "프리셋 이름을 입력하세요.");
        nameInput.focus();
        return;
    }
    const selectedModuleIds = getSelectedModuleIds(form);
    confirmButton.disabled = true;
    try {
        const response = await fetch("/api/presets", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                system_code: systemCode,
                name,
                input_data: collectFormInput(form),
                selected_module_ids: selectedModuleIds,
            }),
        });
        if (!response.ok) {
            const errorBody = await readErrorMessage(response);
            throw new Error(errorBody || `프리셋 저장에 실패했습니다. (${response.status})`);
        }
        const preset = await response.json();
        (presetsBySystem[systemCode] ??= []).push(preset);
        renderAllPresetUI();
        saveForm.classList.add("is-hidden");
        nameInput.value = "";
        setInlineFeedback(feedback, `‘${preset.name}’ 프리셋을 저장했습니다.`, "success");
    } catch (error) {
        setInlineFeedback(feedback, error.message.replace(/^Error:\s*/, "") || "프리셋 저장에 실패했습니다.");
        console.error(error);
    } finally {
        confirmButton.disabled = false;
    }
}

async function deletePresetById(presetId, form) {
    try {
        const response = await fetch(`/api/presets/${presetId}`, { method: "DELETE" });
        if (!response.ok) {
            const errorBody = await readErrorMessage(response);
            throw new Error(errorBody || `프리셋 삭제에 실패했습니다. (${response.status})`);
        }
        for (const code of Object.keys(presetsBySystem)) {
            presetsBySystem[code] = presetsBySystem[code].filter((item) => item.preset_id !== presetId);
        }
        for (const [code, chosen] of suitePresetSelection.entries()) {
            if (chosen === presetId) {
                suitePresetSelection.delete(code);
            }
        }
        renderAllPresetUI();
        if (form) {
            setInlineFeedback(form.querySelector('[data-role="preset-feedback"]'), "프리셋을 삭제했습니다.", "success");
        }
    } catch (error) {
        showToast(error.message.replace(/^Error:\s*/, "") || "프리셋 삭제에 실패했습니다.");
        console.error(error);
    }
}

function bindPresetPanels() {
    for (const panel of document.querySelectorAll('[data-role="preset-panel"]')) {
        const systemCode = panel.dataset.systemCode;
        const form = panel.closest("form");
        const saveOpen = panel.querySelector('[data-role="preset-save-open"]');
        const saveForm = panel.querySelector('[data-role="preset-save-form"]');
        const nameInput = panel.querySelector('[data-role="preset-name-input"]');
        const saveConfirm = panel.querySelector('[data-role="preset-save-confirm"]');
        const saveCancel = panel.querySelector('[data-role="preset-save-cancel"]');
        const feedback = panel.querySelector('[data-role="preset-feedback"]');
        if (!form || !saveOpen || !saveForm || !nameInput || !saveConfirm || !saveCancel) {
            continue;
        }
        saveOpen.addEventListener("click", () => {
            saveForm.classList.toggle("is-hidden");
            setInlineFeedback(feedback, "");
            if (!saveForm.classList.contains("is-hidden")) {
                nameInput.value = "";
                nameInput.focus();
            }
        });
        saveCancel.addEventListener("click", () => {
            saveForm.classList.add("is-hidden");
            setInlineFeedback(feedback, "");
        });
        saveConfirm.addEventListener("click", () => {
            submitPresetSave(systemCode, form, nameInput, saveForm, feedback, saveConfirm);
        });
        nameInput.addEventListener("keydown", (event) => {
            if (event.key === "Enter") {
                event.preventDefault();
                submitPresetSave(systemCode, form, nameInput, saveForm, feedback, saveConfirm);
            }
        });
    }
}

// ----- 전체 점검의 시스템별 프리셋 선택 --------------------------------
function renderSuitePresetLists() {
    const suiteForm = document.getElementById("suite-form");
    if (!suiteForm) {
        return;
    }
    for (const list of suiteForm.querySelectorAll('[data-role="suite-preset-list"]')) {
        const systemCode = list.dataset.systemCode;
        const presets = presetsBySystem[systemCode] ?? [];
        list.dataset.loading = "false";
        list.innerHTML = "";

        const chosen = suitePresetSelection.get(systemCode);
        const chosenStillExists = presets.some((preset) => preset.preset_id === chosen);
        if (!chosenStillExists) {
            suitePresetSelection.delete(systemCode);
        }
        // 프리셋이 정확히 1개면 편의상 자동 선택(모호하지 않음). 2개 이상이면 명시적 선택을 요구.
        if (!suitePresetSelection.has(systemCode) && presets.length === 1) {
            suitePresetSelection.set(systemCode, presets[0].preset_id);
        }

        if (presets.length === 0) {
            const empty = document.createElement("span");
            empty.className = "preset-empty preset-empty--warn";
            empty.textContent = "저장된 프리셋이 없습니다. 개별 점검 화면에서 먼저 저장하세요.";
            list.appendChild(empty);
            continue;
        }
        for (const preset of presets) {
            list.appendChild(buildSuitePresetChip(suiteForm, systemCode, preset));
        }
    }
}

function buildSuitePresetChip(suiteForm, systemCode, preset) {
    const isActive = suitePresetSelection.get(systemCode) === preset.preset_id;
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = `preset-chip preset-chip--radio${isActive ? " is-active" : ""}`;
    chip.dataset.presetId = preset.preset_id;
    chip.setAttribute("aria-pressed", isActive ? "true" : "false");
    chip.innerHTML = `<span class="preset-chip__check" aria-hidden="true"><svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" stroke-width="3" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7"/></svg></span><span class="preset-chip__body"><span class="preset-chip__name"></span><span class="preset-chip__meta"></span></span>`;
    chip.querySelector(".preset-chip__name").textContent = preset.name;
    chip.querySelector(".preset-chip__meta").textContent = presetSummaryText(preset);
    chip.addEventListener("click", () => {
        if (suitePresetSelection.get(systemCode) === preset.preset_id) {
            suitePresetSelection.delete(systemCode);
        } else {
            suitePresetSelection.set(systemCode, preset.preset_id);
        }
        renderSuitePresetLists();
        updateSuiteSystemSelectorState(suiteForm);
        setInlineFeedback(suiteForm.querySelector('[data-role="suite-feedback"]'), "");
    });
    return chip;
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
    button.textContent = "시작 중...";

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
        button.textContent = "점검 시작";
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

async function registerSchedule(systemCode, form, button) {
    const feedback = form.querySelector('[data-role="schedule-feedback"]');
    setInlineFeedback(feedback, "");

    const nameInput = form.querySelector('[data-role="schedule-name"]');
    const name = (nameInput?.value ?? "").trim();
    const built = buildScheduleCron(form);
    if (built.error) {
        setInlineFeedback(feedback, built.error);
        return;
    }
    const cron = built.cron;

    const authMethod = form.querySelector('[name="auth_method"]')?.value;
    if (
        (systemCode === "hom" || systemCode === "mhm")
        && authMethod
        && authMethod !== "phone"
        && authMethod !== "kakao"
    ) {
        setInlineFeedback(feedback, `${systemCode.toUpperCase()}에서는 휴대폰인증·카카오인증만 예약할 수 있습니다.`);
        return;
    }

    const selectedModuleIds = getSelectedModuleIds(form);
    if (selectedModuleIds.length === 0) {
        setInlineFeedback(feedback, "최소 1개 이상의 모듈을 선택해야 합니다.");
        return;
    }

    button.disabled = true;
    button.textContent = "등록 중...";
    try {
        const response = await fetch(`/api/schedules/systems/${systemCode}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                cron,
                name,
                input_data: collectFormInput(form),
                selected_module_ids: selectedModuleIds,
            }),
        });
        if (!response.ok) {
            const errorBody = await readErrorMessage(response);
            throw new Error(errorBody || `예약 등록에 실패했습니다. (${response.status})`);
        }
        setInlineFeedback(feedback, "예약이 등록되었습니다.", "success");
        if (nameInput) {
            nameInput.value = "";
        }
        refreshScheduleList();
    } catch (error) {
        setInlineFeedback(feedback, error.message.replace(/^Error:\s*/, "") || "예약 등록에 실패했습니다.");
        console.error(error);
    } finally {
        button.disabled = false;
        button.textContent = "예약 등록";
    }
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

function updateModuleCard(module) {
    rememberModuleState(module);
    updateRunProgress();

    const card = document.querySelector(`[data-module-id="${module.module_id}"]`);
    if (!card) {
        return;
    }

    const statuses = ["pending", "queued", "running", "waiting_input", "passed", "anomaly", "error", "failed", "blocked", "skipped", "cancelled"];
    for (const status of statuses) {
        card.classList.remove(`status-${status}`);
    }
    card.classList.add(`status-${normalizeOutcomeStatus(module.status)}`);

    const statusNode = card.querySelector('[data-role="module-status"]');
    statusNode.className = statusBadgeClassName(module.status);
    statusNode.dataset.tone = window.__statusBadge.normalizeTone(module.status);
    statusNode.dataset.size = "md";
    statusNode.textContent = statusDisplayLabel({ status: module.status });

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
    const anomaly = states.filter((status) => normalizeOutcomeStatus(status) === "anomaly").length;
    const error = states.filter((status) => normalizeOutcomeStatus(status) === "error").length;
    const blocked = states.filter((status) => status === "blocked").length;
    const finished = passed + anomaly + error + blocked;
    const ratio = total === 0 ? 0 : Math.round((finished / total) * 100);
    bar.style.width = `${ratio}%`;
    bar.classList.toggle("bg-red-500", error > 0);
    bar.classList.toggle("bg-amber-500", error === 0 && anomaly > 0);
    bar.classList.toggle("bg-emerald-500", error === 0 && anomaly === 0);
    label.textContent = `통과 ${passed}/${total}`;
    if (detail) {
        const parts = [`완료 ${finished}/${total}`];
        if (anomaly > 0) {
            parts.push(`이상징후 ${anomaly}`);
        }
        if (error > 0) {
            parts.push(`점검실패 ${error}`);
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
        const scheduleButton = form.querySelector('[data-role="schedule-register"]');
        if (scheduleButton) {
            bindScheduleBuilder(form);
            scheduleButton.addEventListener("click", () => {
                registerSchedule(form.dataset.systemCode, form, scheduleButton);
            });
        }
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

function readSelectedSuiteSystemCodes(form) {
    const codes = [];
    for (const checkbox of form.querySelectorAll('[data-role="suite-system-checkbox"]')) {
        if (checkbox.checked) {
            codes.push(String(checkbox.dataset.systemCode ?? checkbox.value ?? "").trim());
        }
    }
    return codes.filter(Boolean);
}

function readSuiteScopeSystemCodes(form) {
    const codes = [];
    for (const checkbox of form.querySelectorAll('[data-role="suite-system-checkbox"]')) {
        const code = String(checkbox.dataset.systemCode ?? checkbox.value ?? "").trim();
        if (code) {
            codes.push(code);
        }
    }
    return codes;
}

function suiteSystemCheckbox(form, systemCode) {
    return form.querySelector(
        `[data-role="suite-system-checkbox"][data-system-code="${systemCode}"]`,
    );
}

function suiteSystemNeedsAuth(form, systemCode) {
    return suiteSystemCheckbox(form, systemCode)?.dataset.authRequired === "true";
}

// 전체 점검에서 "선택됐으나 아직 적용할 프리셋이 없는" 인증 필요 시스템 목록.
// (프리셋 자체가 없거나, 저장된 프리셋을 하나도 고르지 않은 경우)
function suiteMissingPresetSystems(form) {
    const missing = [];
    for (const systemCode of readSelectedSuiteSystemCodes(form)) {
        if (!suiteSystemNeedsAuth(form, systemCode)) {
            continue;
        }
        const chosen = suitePresetSelection.get(systemCode);
        const presets = presetsBySystem[systemCode] ?? [];
        if (!chosen || !presets.some((preset) => preset.preset_id === chosen)) {
            missing.push(systemCode);
        }
    }
    return missing;
}

function updateSuiteSystemSelectorState(form) {
    const summary = form.querySelector('[data-role="suite-system-selection-summary"]');
    const checkboxes = [...form.querySelectorAll('[data-role="suite-system-checkbox"]')];
    const selectedCount = checkboxes.filter((checkbox) => checkbox.checked).length;
    const totalCount = checkboxes.length;
    if (summary) {
        summary.textContent = `${selectedCount} / ${totalCount} 선택 · ${totalCount - selectedCount}개 제외`;
    }

    const selectedCodes = new Set(readSelectedSuiteSystemCodes(form));
    for (const panel of form.querySelectorAll("[data-suite-auth-for]")) {
        const systemCode = panel.dataset.suiteAuthFor;
        const isSelected = selectedCodes.has(systemCode);
        panel.classList.toggle("is-hidden", !isSelected);

        const status = panel.querySelector('[data-role="suite-preset-status"]');
        if (!status) {
            continue;
        }
        const presets = presetsBySystem[systemCode] ?? [];
        const chosen = suitePresetSelection.get(systemCode);
        if (presets.length === 0) {
            status.textContent = "프리셋 없음";
            status.className = "suite-preset-status suite-preset-status--warn";
        } else if (chosen && presets.some((preset) => preset.preset_id === chosen)) {
            status.textContent = "선택됨";
            status.className = "suite-preset-status suite-preset-status--ok";
        } else {
            status.textContent = "미선택";
            status.className = "suite-preset-status suite-preset-status--pending";
        }
    }
}

function collectSuiteRequest(form) {
    const browserMode = String(form.querySelector('[name="browser_mode"]')?.value ?? "headed").trim();
    const systems = {};
    const selectedCodes = new Set(readSelectedSuiteSystemCodes(form));
    for (const systemCode of selectedCodes) {
        if (!suiteSystemNeedsAuth(form, systemCode)) {
            systems[systemCode] = {};
            continue;
        }
        const chosen = suitePresetSelection.get(systemCode);
        const preset = (presetsBySystem[systemCode] ?? []).find(
            (item) => item.preset_id === chosen,
        );
        if (preset) {
            systems[systemCode] = { ...preset.input_data };
            // 브라우저 모드는 Suite 폼의 공통 선택값만 따른다(프리셋 저장 시 포함된 값 무시).
            delete systems[systemCode].browser_mode;
        }
    }
    return {
        browser_mode: browserMode,
        systems,
        selected_system_codes: [...selectedCodes],
        scope_system_codes: readSuiteScopeSystemCodes(form),
    };
}

async function startSuiteRun(button, form) {
    const feedback = form.querySelector('[data-role="suite-feedback"]');
    setInlineFeedback(feedback, "");

    const selectedCodes = readSelectedSuiteSystemCodes(form);
    if (selectedCodes.length === 0) {
        setInlineFeedback(feedback, "최소 1개 시스템을 선택해야 합니다.");
        return;
    }

    const missing = suiteMissingPresetSystems(form);
    if (missing.length > 0) {
        setInlineFeedback(
            feedback,
            `프리셋을 선택해야 하는 시스템: ${missing.map((code) => code.toUpperCase()).join(", ")}. `
            + "프리셋이 없으면 개별 점검 화면에서 먼저 저장하거나, 해당 시스템의 선택을 해제하세요.",
        );
        return;
    }

    button.disabled = true;
    button.textContent = "시작 중...";

    try {
        const response = await fetch("/api/suites", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify(collectSuiteRequest(form)),
        });

        if (!response.ok) {
            const errorBody = await readErrorMessage(response);
            throw new Error(errorBody || `전체 점검 생성에 실패했습니다. (${response.status})`);
        }

        const suite = await response.json();
        window.location.href = `/suites/${suite.suite_id}`;
    } catch (error) {
        button.disabled = false;
        button.textContent = "전체 점검 시작";
        setInlineFeedback(feedback, error.message.replace(/^Error:\s*/, "") || "전체 점검 생성에 실패했습니다.");
        console.error(error);
    }
}

async function registerSuiteSchedule(form, button) {
    const feedback = form.querySelector('[data-role="suite-schedule-feedback"]');
    setInlineFeedback(feedback, "");

    const selectedCodes = readSelectedSuiteSystemCodes(form);
    if (selectedCodes.length === 0) {
        setInlineFeedback(feedback, "최소 1개 시스템을 선택해야 합니다.");
        return;
    }

    const name = (form.querySelector('[data-role="schedule-name"]')?.value ?? "").trim();
    const built = buildScheduleCron(form);
    if (built.error) {
        setInlineFeedback(feedback, built.error);
        return;
    }

    const missing = suiteMissingPresetSystems(form);
    if (missing.length > 0) {
        setInlineFeedback(
            feedback,
            `프리셋을 선택해야 하는 시스템: ${missing.map((code) => code.toUpperCase()).join(", ")}.`,
        );
        return;
    }

    button.disabled = true;
    button.textContent = "등록 중...";
    try {
        const response = await fetch("/api/schedules/suites", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                cron: built.cron,
                name,
                ...collectSuiteRequest(form),
            }),
        });
        if (!response.ok) {
            const errorBody = await readErrorMessage(response);
            throw new Error(errorBody || `예약 등록에 실패했습니다. (${response.status})`);
        }
        setInlineFeedback(feedback, "전체 점검 예약이 등록되었습니다.", "success");
        const nameInput = form.querySelector('[data-role="schedule-name"]');
        if (nameInput) {
            nameInput.value = "";
        }
        refreshScheduleList();
    } catch (error) {
        setInlineFeedback(feedback, error.message.replace(/^Error:\s*/, "") || "예약 등록에 실패했습니다.");
        console.error(error);
    } finally {
        button.disabled = false;
        button.textContent = "예약 등록";
    }
}

function bindSuiteForm() {
    const form = document.getElementById("suite-form");
    if (!form) {
        return;
    }
    for (const checkbox of form.querySelectorAll('[data-role="suite-system-checkbox"]')) {
        checkbox.addEventListener("change", () => {
            updateSuiteSystemSelectorState(form);
        });
    }
    const selectAllButton = form.querySelector('[data-role="suite-system-select-all"]');
    if (selectAllButton) {
        selectAllButton.addEventListener("click", () => {
            for (const checkbox of form.querySelectorAll('[data-role="suite-system-checkbox"]')) {
                checkbox.checked = true;
            }
            updateSuiteSystemSelectorState(form);
        });
    }
    const deselectAllButton = form.querySelector('[data-role="suite-system-deselect-all"]');
    if (deselectAllButton) {
        deselectAllButton.addEventListener("click", () => {
            for (const checkbox of form.querySelectorAll('[data-role="suite-system-checkbox"]')) {
                checkbox.checked = false;
            }
            updateSuiteSystemSelectorState(form);
        });
    }
    updateSuiteSystemSelectorState(form);
    bindScheduleBuilder(form);
    const scheduleButton = form.querySelector('[data-role="suite-schedule-register"]');
    if (scheduleButton) {
        scheduleButton.addEventListener("click", () => {
            registerSuiteSchedule(form, scheduleButton);
        });
    }
    form.addEventListener("submit", (event) => {
        event.preventDefault();
        const button = document.getElementById("suite-start-button");
        startSuiteRun(button, form);
    });
}

const SUITE_ACTIVE_STATUSES = new Set(["pending", "running", "waiting_input"]);
const SUITE_ACTIVE_MODULE_STATUSES = new Set(["running", "waiting_input"]);
let suiteRunProgressSocket = null;
let suiteRunProgressRunId = null;

function orderedSelectedRunModules(run) {
    const modules = [...(run?.modules ?? [])].sort((left, right) => left.order - right.order);
    const selectedIds = new Set(
        run?.selected_module_ids?.length
            ? run.selected_module_ids
            : modules
                .filter((module) => String(module.status).toLowerCase() !== "skipped")
                .map((module) => module.module_id),
    );
    return modules.filter((module) => selectedIds.has(module.module_id));
}

function computeRunModuleProgress(run) {
    const modules = orderedSelectedRunModules(run);
    const total = modules.length || run?.selected_module_ids?.length || 0;
    if (total === 0) {
        return { current: 0, total: 0, label: "", moduleName: "", tone: "muted" };
    }

    const activeIndex = modules.findIndex((module) =>
        SUITE_ACTIVE_MODULE_STATUSES.has(String(module.status).toLowerCase()),
    );
    if (activeIndex >= 0) {
        const module = modules[activeIndex];
        return {
            current: activeIndex + 1,
            total,
            label: `${activeIndex + 1}/${total}`,
            moduleName: module.name ?? "",
            tone: String(module.status).toLowerCase() === "waiting_input" ? "waiting" : "active",
        };
    }

    const passedCount = modules.filter((module) => String(module.status).toLowerCase() === "passed").length;
    const issueIndex = modules.findIndex((module) => isModuleIssueStatus(module.status));
    const runStatus = normalizeOutcomeStatus(run?.status);

    if (issueIndex >= 0 && (runStatus === "anomaly" || runStatus === "error")) {
        return {
            current: issueIndex + 1,
            total,
            label: `${issueIndex + 1}/${total}`,
            moduleName: modules[issueIndex].name ?? "",
            tone: runStatus === "error" ? "error" : "anomaly",
        };
    }

    if (ACTIVE_RUN_STATUSES.has(runStatus) && passedCount < total) {
        return {
            current: passedCount + 1,
            total,
            label: `${passedCount + 1}/${total}`,
            moduleName: "",
            tone: "active",
        };
    }

    if (runStatus === "passed") {
        return {
            current: total,
            total,
            label: `${total}/${total}`,
            moduleName: "",
            tone: "passed",
        };
    }

    return {
        current: passedCount,
        total,
        label: passedCount > 0 ? `${passedCount}/${total}` : "",
        moduleName: "",
        tone: "muted",
    };
}

function moduleProgressClassName(tone) {
    if (tone === "error") {
        return "mt-1 text-xs font-semibold text-red-600";
    }
    if (tone === "anomaly" || tone === "failed") {
        return "mt-1 text-xs font-semibold text-amber-700";
    }
    if (tone === "passed") {
        return "mt-1 text-xs font-semibold text-emerald-600";
    }
    if (tone === "waiting") {
        return "mt-1 text-xs font-semibold text-amber-700";
    }
    if (tone === "active") {
        return "mt-1 text-xs font-semibold text-indigo-600";
    }
    return "mt-1 text-xs font-medium text-gray-400 is-hidden";
}

function formatStepModuleProgressText(progress, stepStatus) {
    if (!progress.label) {
        return "";
    }
    const status = String(stepStatus ?? "").toLowerCase();
    if (status === "pending") {
        return "";
    }
    if (progress.tone === "error") {
        return `모듈 ${progress.label} 점검실패${progress.moduleName ? ` · ${progress.moduleName}` : ""}`;
    }
    if (progress.tone === "anomaly" || progress.tone === "failed") {
        return `모듈 ${progress.label} 이상징후${progress.moduleName ? ` · ${progress.moduleName}` : ""}`;
    }
    if (progress.tone === "passed" || status === "passed") {
        return `모듈 ${progress.label} 완료`;
    }
    if (progress.tone === "waiting") {
        return `모듈 ${progress.label} · OTP 대기${progress.moduleName ? ` (${progress.moduleName})` : ""}`;
    }
    return `모듈 ${progress.label} 실행 중${progress.moduleName ? ` · ${progress.moduleName}` : ""}`;
}

function findSuiteStepCardByRunId(runId) {
    if (!runId) {
        return null;
    }
    return document.querySelector(`.suite-step-card[data-run-id="${runId}"]`);
}

function updateSuiteStepModuleProgress(run) {
    const card = findSuiteStepCardByRunId(run?.run_id);
    if (!card) {
        return;
    }
    const progressNode = card.querySelector('[data-role="step-module-progress"]');
    if (!progressNode) {
        return;
    }
    const stepStatus = card.querySelector('[data-role="step-status"]')?.textContent ?? "";
    const progress = computeRunModuleProgress(run);
    const text = formatStepModuleProgressText(progress, stepStatus);
    progressNode.textContent = text;
    progressNode.className = moduleProgressClassName(text ? progress.tone : "muted");
    progressNode.classList.toggle("is-hidden", !text);

    if (run.run_id === suiteRunProgressRunId) {
        updateSuiteProgressDetailWithModule(run);
    }
}

function updateSuiteProgressDetailWithModule(run) {
    const detail = document.getElementById("suite-progress-detail");
    if (!detail || !run) {
        return;
    }
    const progress = computeRunModuleProgress(run);
    const systemLabel = `${run.system_name} (${String(run.system_code ?? "").toUpperCase()})`;
    if (!progress.label) {
        detail.textContent = `현재: ${systemLabel}`;
        return;
    }
    if (progress.tone === "waiting") {
        detail.textContent = `현재: ${systemLabel} · 모듈 ${progress.label} · OTP 대기`;
        return;
    }
    detail.textContent = `현재: ${systemLabel} · 모듈 ${progress.label}`;
}

async function refreshSuiteRunProgress(runId) {
    if (!runId) {
        return;
    }
    try {
        const response = await fetch(`/api/runs/${runId}`);
        if (!response.ok) {
            return;
        }
        const run = await response.json();
        updateSuiteStepModuleProgress(run);
    } catch (error) {
        console.error(error);
    }
}

function closeSuiteRunProgressSocket() {
    if (suiteRunProgressSocket) {
        suiteRunProgressSocket.close();
        suiteRunProgressSocket = null;
    }
    suiteRunProgressRunId = null;
}

function resolveActiveSuiteRunId(suite) {
    if (suite?.awaiting_input_run_id) {
        return suite.awaiting_input_run_id;
    }
    if (suite?.active_run_id) {
        return suite.active_run_id;
    }
    const activeStep = (suite?.steps ?? []).find((step) => {
        const status = String(step.status).toLowerCase();
        return step.run_id && (status === "running" || status === "waiting_input");
    });
    return activeStep?.run_id ?? null;
}

const SUITE_RUN_PROGRESS_REFRESH_EVENTS = new Set([
    "snapshot",
    "module_queued",
    "module_started",
    "module_finished",
    "module_waiting_input",
    "run_waiting_input",
    "run_resumed",
    "run_finished",
    "run_started",
]);

function syncSuiteRunProgressSocket(suite) {
    const runId = resolveActiveSuiteRunId(suite);
    if (!runId) {
        closeSuiteRunProgressSocket();
        return;
    }
    if (runId === suiteRunProgressRunId && suiteRunProgressSocket) {
        refreshSuiteRunProgress(runId);
        return;
    }

    closeSuiteRunProgressSocket();
    suiteRunProgressRunId = runId;
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    suiteRunProgressSocket = new WebSocket(`${protocol}://${window.location.host}/ws/runs/${runId}`);

    suiteRunProgressSocket.addEventListener("message", (event) => {
        const message = JSON.parse(event.data);
        if (message.event_type === "snapshot") {
            updateSuiteStepModuleProgress(message.payload);
            return;
        }
        if (SUITE_RUN_PROGRESS_REFRESH_EVENTS.has(message.event_type)) {
            refreshSuiteRunProgress(runId);
        }
    });

    suiteRunProgressSocket.addEventListener("close", () => {
        if (suiteRunProgressRunId === runId) {
            suiteRunProgressRunId = null;
            suiteRunProgressSocket = null;
        }
    });

    refreshSuiteRunProgress(runId);
}

function refreshFinishedSuiteStepProgress(suite) {
    for (const step of suite?.steps ?? []) {
        const status = String(step.status).toLowerCase();
        if (!step.run_id) {
            continue;
        }
        if (status === "passed" || status === "anomaly" || status === "error" || status === "failed" || status === "cancelled") {
            refreshSuiteRunProgress(step.run_id);
        }
    }
}

function currentSuiteId() {
    return document.getElementById("suite-step-grid")?.dataset.suiteId ?? "";
}

function updateSuiteActions(status) {
    const normalized = String(status ?? "").toLowerCase();
    const isActive = SUITE_ACTIVE_STATUSES.has(normalized);
    const cancelButton = document.getElementById("suite-cancel");
    if (cancelButton) {
        cancelButton.classList.toggle("hidden", !isActive);
        if (!isActive) {
            cancelButton.disabled = false;
            cancelButton.textContent = "전체 점검 취소";
        }
    }
}

function updateSuiteProgress(suite) {
    const steps = suite.steps ?? [];
    const skipped = steps.filter((step) => String(step.status).toLowerCase() === "skipped").length;
    const selectedTotal = steps.length - skipped;
    const passed = steps.filter((step) => String(step.status).toLowerCase() === "passed").length;
    const label = document.getElementById("suite-progress-label");
    const bar = document.getElementById("suite-progress-bar");
    const detail = document.getElementById("suite-progress-detail");
    if (label) {
        const skippedSuffix = skipped > 0 ? ` (${skipped}개 제외)` : "";
        label.textContent = `통과 ${passed}/${selectedTotal || steps.length}${skippedSuffix}`;
    }
    if (bar) {
        const denominator = selectedTotal || steps.length;
        bar.style.width = denominator > 0 ? `${Math.round((passed / denominator) * 100)}%` : "0%";
    }
    if (detail) {
        const currentIndex = suite.current_step_index ?? 0;
        const currentStep = steps.find((step) => step.order === currentIndex) ?? steps[currentIndex];
        if (String(suite.status).toLowerCase() === "waiting_input") {
            const waitingStep = steps.find((step) => step.run_id && step.run_id === suite.awaiting_input_run_id);
            if (waitingStep) {
                detail.textContent = `현재: ${waitingStep.system_name} (${waitingStep.system_code?.toUpperCase() ?? ""}) · OTP 대기`;
            } else {
                detail.textContent = "OTP 입력 대기 중입니다.";
            }
        } else if (
            currentStep
            && String(currentStep.status).toLowerCase() !== "skipped"
            && SUITE_ACTIVE_STATUSES.has(String(suite.status).toLowerCase())
        ) {
            detail.textContent = `현재: ${currentStep.system_name} (${currentStep.system_code?.toUpperCase() ?? ""})`;
        } else {
            detail.textContent = skipped > 0 ? `${skipped}개 시스템이 선택에서 제외되었습니다.` : "";
        }
    }
}

function updateSuiteStepCard(step) {
    const card = document.querySelector(`.suite-step-card[data-step-index="${step.order}"]`);
    if (!card) {
        return;
    }
    const status = String(step.status ?? "").toLowerCase();
    card.dataset.runId = step.run_id ?? "";
    card.className = `suite-step-card rounded-2xl border border-gray-200 bg-white p-5 shadow-sm status-${status}`;
    const statusNode = card.querySelector('[data-role="step-status"]');
    if (statusNode) {
        statusNode.textContent = step.status ?? "";
        statusNode.className = `inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold ${statusBadgeClassName(step.status)}`;
        statusNode.dataset.tone = window.__statusBadge.normalizeTone(step.status);
    }
    const linkNode = card.querySelector('[data-role="step-run-link"]');
    if (linkNode) {
        if (status === "skipped") {
            linkNode.innerHTML = '<span class="text-gray-400">건너뜀 (선택 제외)</span>';
        } else if (step.run_id) {
            linkNode.innerHTML = `<a href="/runs/${step.run_id}" class="font-medium text-indigo-600 hover:underline">${step.run_id}</a>`;
        } else {
            linkNode.innerHTML = '<span class="text-gray-400">대기 중</span>';
        }
    }
    if (status === "running" || status === "waiting_input") {
        card.classList.add("ring-2", "ring-indigo-200");
    } else {
        card.classList.remove("ring-2", "ring-indigo-200");
    }

    if (!step.run_id) {
        const progressNode = card.querySelector('[data-role="step-module-progress"]');
        if (progressNode) {
            progressNode.textContent = "";
            progressNode.className = "mt-1 text-xs font-medium text-gray-400 is-hidden";
        }
    }
}

function updateSuiteOtpPanel(suite) {
    const panel = document.getElementById("suite-otp-panel");
    if (!panel) {
        return;
    }
    const awaitingRunId = suite.awaiting_input_run_id ?? "";
    const prompt = suite.awaiting_input_prompt ?? "현재 시스템 로그인에서 OTP 입력이 필요합니다.";
    panel.dataset.runId = awaitingRunId;
    const promptNode = document.getElementById("suite-otp-prompt");
    if (promptNode) {
        promptNode.textContent = prompt;
    }
    panel.classList.toggle("is-hidden", !awaitingRunId);
}

function renderSuiteSnapshot(suite) {
    const statusNode = document.getElementById("suite-status");
    if (statusNode) {
        statusNode.textContent = window.__statusBadge.statusLabel(suite.status);
        statusNode.className = "status-badge";
        statusNode.dataset.size = "md";
        statusNode.dataset.tone = window.__statusBadge.normalizeTone(suite.status);
        statusNode.dataset.status = suite.status;
    }
    updateSuiteActions(suite.status);
    updateSuiteProgress(suite);
    updateSuiteOtpPanel(suite);
    for (const step of suite.steps ?? []) {
        updateSuiteStepCard(step);
    }
    syncSuiteRunProgressSocket(suite);
    refreshFinishedSuiteStepProgress(suite);
}

async function cancelSuite(button) {
    if (!window.confirm("진행 중인 전체 점검을 취소하시겠습니까? 현재 시스템 Run도 함께 중단됩니다.")) {
        return;
    }
    button.disabled = true;
    button.textContent = "취소 요청됨...";
    try {
        const response = await fetch(`/api/suites/${currentSuiteId()}/cancel`, { method: "POST" });
        if (!response.ok) {
            throw new Error(await readErrorMessage(response));
        }
    } catch (error) {
        button.disabled = false;
        button.textContent = "전체 점검 취소";
        showToast(`취소에 실패했습니다: ${error.message}`);
        console.error(error);
    }
}

function bindSuiteActions() {
    const cancelButton = document.getElementById("suite-cancel");
    if (cancelButton) {
        cancelButton.addEventListener("click", () => cancelSuite(cancelButton));
    }
    updateSuiteActions(document.getElementById("suite-status")?.dataset.status);
}

async function submitSuiteOtp(suiteId, otpCode, form) {
    const button = form.querySelector("button[type='submit']");
    const feedback = document.querySelector('[data-role="suite-otp-feedback"]');
    setInlineFeedback(feedback, "");
    button.disabled = true;
    button.textContent = "제출 중...";

    try {
        const response = await fetch(`/api/suites/${suiteId}/otp`, {
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

function bindSuiteOtpForm() {
    const form = document.getElementById("suite-otp-form");
    const panel = document.getElementById("suite-otp-panel");
    if (!form || !panel) {
        return;
    }

    form.addEventListener("submit", (event) => {
        event.preventDefault();
        const suiteId = panel.dataset.suiteId;
        const otpCode = String(new FormData(form).get("otp_code") || "").trim();
        if (!otpCode) {
            setInlineFeedback(document.querySelector('[data-role="suite-otp-feedback"]'), "OTP 코드를 입력하세요.");
            return;
        }
        submitSuiteOtp(suiteId, otpCode, form);
    });
}

function bindSuiteSocket() {
    const grid = document.getElementById("suite-step-grid");
    if (!grid) {
        return;
    }

    const suiteId = grid.dataset.suiteId;
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const socket = new WebSocket(`${protocol}://${window.location.host}/ws/suites/${suiteId}`);

    socket.addEventListener("message", (event) => {
        const message = JSON.parse(event.data);
        const suite = message.payload ?? message;

        if (message.event_type === "snapshot") {
            renderSuiteSnapshot(suite);
            return;
        }

        if (suite.status) {
            const statusNode = document.getElementById("suite-status");
            if (statusNode) {
                statusNode.textContent = window.__statusBadge.statusLabel(suite.status);
                statusNode.className = "status-badge";
                statusNode.dataset.size = "md";
                statusNode.dataset.tone = window.__statusBadge.normalizeTone(suite.status);
                statusNode.dataset.status = suite.status;
            }
            updateSuiteActions(suite.status);
        }

        renderSuiteSnapshot(suite);
    });
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
    updateRunActions(document.getElementById("run-status")?.dataset.status);
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
            const snapshotStatusNode = document.getElementById("run-status");
            snapshotStatusNode.textContent = window.__statusBadge.statusLabel(message.payload.status);
            snapshotStatusNode.className = "status-badge";
            snapshotStatusNode.dataset.size = "md";
            snapshotStatusNode.dataset.tone = window.__statusBadge.normalizeTone(message.payload.status);
            snapshotStatusNode.dataset.status = message.payload.status;
            updateRunActions(message.payload.status);
            updateOtpPanel(message.payload);
            updateComparisonPanel(message.payload);
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
            runStatus.textContent = window.__statusBadge.statusLabel(message.run_status);
            runStatus.className = "status-badge";
            runStatus.dataset.size = "md";
            runStatus.dataset.tone = window.__statusBadge.normalizeTone(message.run_status);
            runStatus.dataset.status = message.run_status;
            updateRunActions(message.run_status);
        }

        if (message.event_type === "module_waiting_input" && message.payload?.module) {
            updateOtpPanel({
                awaiting_input_module_id: message.payload.module.module_id,
                awaiting_input_prompt: "휴대폰으로 받은 OTP를 입력하세요.",
            });
        }

        if (message.event_type === "run_waiting_input" || message.event_type === "run_resumed" || message.event_type === "run_finished") {
            updateOtpPanel(message.payload);
        }

        if (message.event_type === "run_finished") {
            updateComparisonPanel(message.payload);
        }
    });
}

function updateComparisonPanel(runPayload) {
    const panel = document.getElementById("comparison-panel");
    if (!panel) {
        return;
    }
    const comparison = runPayload?.comparison;
    const hasBaseline = Boolean(comparison && comparison.has_baseline);
    panel.classList.toggle("is-hidden", !hasBaseline);
    if (!hasBaseline) {
        return;
    }

    const link = document.getElementById("comparison-baseline-link");
    if (link && comparison.baseline_run_id) {
        link.href = `/runs/${comparison.baseline_run_id}`;
        link.textContent = `기준 Run: ${comparison.baseline_run_id}`;
    }

    const body = document.getElementById("comparison-body");
    if (!body) {
        return;
    }
    body.innerHTML = "";
    const groups = [
        { label: "새 이상징후", names: comparison.newly_failed ?? [], cls: "bg-amber-100 text-amber-800" },
        { label: "복구됨", names: comparison.recovered ?? [], cls: "bg-emerald-100 text-emerald-700" },
        { label: "지속 이상징후", names: comparison.still_failing ?? [], cls: "bg-orange-100 text-orange-700" },
    ];
    let hasAny = false;
    for (const group of groups) {
        for (const name of group.names) {
            hasAny = true;
            const chip = document.createElement("span");
            chip.className = `inline-flex items-center gap-1 rounded-full px-2.5 py-1 font-medium ${group.cls}`;
            chip.textContent = `${group.label}: ${name}`;
            body.appendChild(chip);
        }
    }
    if (!hasAny) {
        const note = document.createElement("span");
        note.className = "text-gray-500";
        note.textContent = "직전 실행과 비교해 모듈 상태 변화가 없습니다.";
        body.appendChild(note);
    }
}

document.addEventListener("DOMContentLoaded", () => {
    bindModuleSelectors();
    bindSystemCardExpand();
    bindSystemButtons();
    bindSuiteForm();
    bindPresetPanels();
    loadPresets();
    bindRunsOverview();
    bindRunsHistory();
    bindSchedulesOverview();
    bindLogControls();
    startRuntimeTicker();
    bindRunActions();
    bindOtpForm();
    bindSuiteActions();
    bindSuiteOtpForm();
    bindSuiteSocket();
    bindRunSocket();
});
