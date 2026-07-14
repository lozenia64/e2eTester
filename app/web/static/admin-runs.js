// 관리자 Run 이력 — /admin/runs 전용
(() => {
  const root = document.getElementById("runs-table-body");
  if (!root) return;

  const statusBadgeClasses = {
    PASSED: "bg-green-100 text-green-700",
    ANOMALY: "bg-amber-100 text-amber-800",
    FAILED: "bg-amber-100 text-amber-800",
    ERROR: "bg-red-100 text-red-700",
    RUNNING: "bg-blue-100 text-blue-700",
    PENDING: "bg-gray-100 text-gray-600",
    CANCELLED: "bg-gray-100 text-gray-500",
    WAITING_INPUT: "bg-yellow-100 text-yellow-700",
  };

  function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text ?? "";
    return div.innerHTML;
  }

  function buildRunsQuery() {
    const params = new URLSearchParams({ limit: "200" });
    const systemCode = document.getElementById("filter-system").value;
    const userName = document.getElementById("filter-user-name").value.trim();
    const runStatus = document.getElementById("filter-status").value;
    if (systemCode) params.set("system_code", systemCode);
    if (userName) params.set("user_name", userName);
    if (runStatus) params.set("status", runStatus);
    return params.toString();
  }

  function renderRunsTable(runs) {
    const tbody = document.getElementById("runs-table-body");
    if (runs.length === 0) {
      tbody.innerHTML =
        '<tr><td colspan="6" class="px-4 py-8 text-center text-sm text-gray-400">Run 없음</td></tr>';
      return;
    }
    tbody.innerHTML = runs
      .map((r) => {
        const cls = statusBadgeClasses[r.status] || "bg-gray-100 text-gray-600";
        const label = escapeHtml(r.status_label || r.status);
        const runId = escapeHtml(r.run_id);
        const systemLabel = escapeHtml(r.system_name || r.system_code);
        const userLabel = escapeHtml(r.created_by_user_name || "(시스템)");
        const at = r.requested_at ? new Date(r.requested_at).toLocaleString("ko-KR") : "—";
        const canDelete = !["RUNNING", "PENDING", "WAITING_INPUT"].includes(r.status);
        const deleteBtn = canDelete
          ? `<button type="button" class="delete-run-btn rounded border border-red-200 px-2 py-1 text-xs font-semibold text-red-600 hover:bg-red-50" data-run-id="${runId}">삭제</button>`
          : '<span class="text-xs text-gray-300">—</span>';
        return `<tr class="hover:bg-gray-50">
            <td class="px-4 py-3 font-mono text-xs text-gray-600"><a href="/runs/${encodeURIComponent(r.run_id)}" class="hover:underline text-indigo-600">${escapeHtml(r.run_id.slice(0, 12))}…</a></td>
            <td class="px-4 py-3 text-sm">${systemLabel}</td>
            <td class="px-4 py-3 text-sm text-gray-600">${userLabel}</td>
            <td class="px-4 py-3"><span class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${cls}">${label}</span></td>
            <td class="px-4 py-3 text-xs text-gray-500">${escapeHtml(at)}</td>
            <td class="px-4 py-3 text-right">${deleteBtn}</td>
        </tr>`;
      })
      .join("");
  }

  async function deleteRun(runId) {
    const confirmed = window.confirm(
      `Run ${runId} 을(를) 영구 삭제하시겠습니까?\n\nDB 기록·로그·스크린샷이 모두 삭제되며 사용자 화면에서도 사라집니다.`
    );
    if (!confirmed) return;

    const response = await fetch(`/api/admin/runs/${encodeURIComponent(runId)}`, { method: "DELETE" });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      window.alert(body.detail || `삭제에 실패했습니다. (${response.status})`);
      return;
    }
    await loadRunsPage();
  }

  function isSameLocalDay(iso, reference = new Date()) {
    if (!iso) return false;
    const d = new Date(iso);
    return (
      d.getFullYear() === reference.getFullYear() &&
      d.getMonth() === reference.getMonth() &&
      d.getDate() === reference.getDate()
    );
  }

  async function loadRunsPage() {
    const [runsRes, usersRes, systemsRes] = await Promise.all([
      fetch(`/api/admin/runs?${buildRunsQuery()}`),
      fetch("/api/admin/users"),
      fetch("/api/admin/systems"),
    ]);
    const runs = await runsRes.json();
    const users = await usersRes.json();
    const systems = await systemsRes.json();

    document.getElementById("card-total-users").textContent = users.length;
    document.getElementById("card-total-runs").textContent = runs.length;

    const todayRuns = runs.filter((r) => isSameLocalDay(r.requested_at));
    document.getElementById("card-today-runs").textContent = todayRuns.length;

    const systemSelect = document.getElementById("filter-system");
    if (systemSelect.options.length <= 1) {
      systems.forEach((system) => {
        const option = document.createElement("option");
        option.value = system.system_code;
        option.textContent = system.system_name || system.system_code;
        systemSelect.appendChild(option);
      });
    }

    const filterParts = [];
    const selectedSystem = systemSelect.options[systemSelect.selectedIndex];
    if (systemSelect.value) filterParts.push(`시스템: ${selectedSystem.textContent}`);
    const statusSelect = document.getElementById("filter-status");
    const selectedStatus = statusSelect.options[statusSelect.selectedIndex];
    if (statusSelect.value) filterParts.push(`상태: ${selectedStatus.textContent}`);
    const userName = document.getElementById("filter-user-name").value.trim();
    if (userName) filterParts.push(`실행자: ${userName}`);
    document.getElementById("runs-filter-meta").textContent = filterParts.length
      ? `${filterParts.join(" · ")} · ${runs.length}건`
      : `최근 ${runs.length}건`;

    renderRunsTable(runs);
  }

  document.getElementById("btn-filter").addEventListener("click", loadRunsPage);
  document.getElementById("btn-reset").addEventListener("click", () => {
    document.getElementById("filter-system").value = "";
    document.getElementById("filter-status").value = "";
    document.getElementById("filter-user-name").value = "";
    loadRunsPage();
  });
  document.getElementById("filter-user-name").addEventListener("keydown", (event) => {
    if (event.key === "Enter") loadRunsPage();
  });
  document.getElementById("runs-table-body").addEventListener("click", (event) => {
    const button = event.target.closest(".delete-run-btn");
    if (!button) return;
    deleteRun(button.dataset.runId);
  });

  loadRunsPage();
})();
