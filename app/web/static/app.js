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
        const expectedValue = field.dataset.showWhenValue;
        const controllingInput = form.querySelector(`[name="${controllingKey}"]`);
        const input = field.querySelector("input, select, textarea");
        const isVisible = controllingInput && input && controllingInput.value === expectedValue;

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
        input.addEventListener("change", () => syncConditionalFields(form));
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
    if (authMethod && authMethod !== "phone") {
        window.alert("현재는 휴대폰인증만 실행할 수 있습니다. 선택한 인증수단은 아직 준비 중입니다.");
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
    statusNode.className = `status-badge status-${module.status.toLowerCase()}`;
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
            document.getElementById("run-status").className = `status-badge status-${message.payload.status.toLowerCase()}`;
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
            runStatus.className = `status-badge status-${message.run_status.toLowerCase()}`;
        }

        if (message.event_type === "run_waiting_input" || message.event_type === "run_resumed" || message.event_type === "run_finished") {
            updateOtpPanel(message.payload);
        }
    });
}

document.addEventListener("DOMContentLoaded", () => {
    bindSystemButtons();
    bindOtpForm();
    bindRunSocket();
});
