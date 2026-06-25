'use strict';

const REFRESH_MS = 5000;

const STATUS_BADGE = {
    RUNNING: 'bg-blue-100 text-blue-700',
    WAITING_INPUT: 'bg-yellow-100 text-yellow-800',
    PENDING: 'bg-gray-100 text-gray-600',
    PASSED: 'bg-green-100 text-green-700',
    FAILED: 'bg-amber-100 text-amber-800',
    CANCELLED: 'bg-gray-100 text-gray-500',
};

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text ?? '';
    return div.innerHTML;
}

function fmtTs(iso) {
    if (!iso) return '—';
    return new Date(iso).toLocaleString('ko-KR', {
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
    });
}

function badge(status) {
    const cls = STATUS_BADGE[status] || 'bg-gray-100 text-gray-600';
    return `<span class="inline-flex rounded-full px-2 py-0.5 text-xs font-semibold ${cls}">${escapeHtml(status)}</span>`;
}

function renderKpis(snapshot) {
    const runtime = snapshot.runtime || {};
    const runs = snapshot.runs || {};
    const suites = snapshot.suites || {};
    const schedules = snapshot.schedules || {};
    const cards = [
        { label: '진행 중 Run', value: runs.active_count ?? 0, sub: `전체 ${runs.total ?? 0}건` },
        { label: '진행 중 Suite', value: suites.active_count ?? 0, sub: `전체 ${suites.total ?? 0}건` },
        { label: '실행 큐 대기', value: runtime.run_queue_pending ?? 0, sub: `워커 ${runtime.run_queue_workers ?? 0}개` },
        { label: '활성 예약', value: schedules.enabled_count ?? 0, sub: `24h 내 ${schedules.due_within_24h_count ?? 0}건` },
    ];
    document.getElementById('ops-kpi-cards').innerHTML = cards.map((card) => `
        <div class="status-metric-card">
            <p class="text-xs font-semibold uppercase tracking-wider text-gray-400">${escapeHtml(card.label)}</p>
            <p class="mt-2 text-3xl font-bold text-gray-900">${escapeHtml(String(card.value))}</p>
            <p class="mt-1 text-xs text-gray-500">${escapeHtml(card.sub)}</p>
        </div>
    `).join('');
}

function renderActiveRuns(runs) {
    const tbody = document.getElementById('ops-active-runs');
    const items = runs.active || [];
    document.getElementById('ops-active-runs-count').textContent = `${items.length}건`;
    if (!items.length) {
        tbody.innerHTML = '<tr><td colspan="4" class="px-4 py-6 text-center text-gray-400">진행 중 Run 없음</td></tr>';
        return;
    }
    tbody.innerHTML = items.map((run) => `
        <tr class="hover:bg-gray-50">
            <td class="px-4 py-2"><a href="/runs/${encodeURIComponent(run.run_id)}" class="font-mono text-xs text-indigo-600 hover:underline">${escapeHtml(run.run_id)}</a></td>
            <td class="px-4 py-2">${escapeHtml(run.system_code)}</td>
            <td class="px-4 py-2">${badge(run.status)}</td>
            <td class="px-4 py-2 text-xs text-gray-600">${escapeHtml(run.triggered_by || '—')}</td>
        </tr>
    `).join('');
}

function renderActiveSuites(suites) {
    const tbody = document.getElementById('ops-active-suites');
    const items = suites.active || [];
    document.getElementById('ops-active-suites-count').textContent = `${items.length}건`;
    if (!items.length) {
        tbody.innerHTML = '<tr><td colspan="3" class="px-4 py-6 text-center text-gray-400">진행 중 Suite 없음</td></tr>';
        return;
    }
    tbody.innerHTML = items.map((suite) => `
        <tr class="hover:bg-gray-50">
            <td class="px-4 py-2"><a href="/suites/${encodeURIComponent(suite.suite_id)}" class="font-mono text-xs text-indigo-600 hover:underline">${escapeHtml(suite.suite_id)}</a></td>
            <td class="px-4 py-2">${badge(suite.status)}</td>
            <td class="px-4 py-2 text-xs text-gray-600">${escapeHtml(String((suite.current_step_index ?? 0) + 1))} / ${escapeHtml(String(suite.step_total))}</td>
        </tr>
    `).join('');
}

function renderSchedules(schedules) {
    const tbody = document.getElementById('ops-schedules');
    const items = (schedules.upcoming || []).filter((row) => row.due_within_24h);
    if (!items.length) {
        tbody.innerHTML = '<tr><td colspan="5" class="px-4 py-8 text-center text-gray-400">24시간 내 예정된 실행 없음</td></tr>';
        return;
    }
    tbody.innerHTML = items.map((schedule) => `
        <tr class="hover:bg-gray-50">
            <td class="px-4 py-2 text-sm">${escapeHtml(schedule.name || schedule.schedule_id)}</td>
            <td class="px-4 py-2 text-xs text-gray-600">${escapeHtml(schedule.schedule_kind)}</td>
            <td class="px-4 py-2 text-xs text-gray-600">${escapeHtml(schedule.system_code || '—')}</td>
            <td class="px-4 py-2 text-xs text-gray-600">${escapeHtml(fmtTs(schedule.next_run_at))}</td>
            <td class="px-4 py-2">${schedule.last_run_status ? badge(schedule.last_run_status) : '<span class="text-xs text-gray-400">—</span>'}</td>
        </tr>
    `).join('');
}

function eventLevelClass(level) {
    const normalized = (level || 'info').toLowerCase();
    if (normalized === 'error' || normalized === 'exception') return 'border-l-red-500 bg-red-50/40';
    if (normalized === 'warning') return 'border-l-amber-500 bg-amber-50/40';
    return 'border-l-indigo-500 bg-white';
}

function renderEvents(events) {
    const container = document.getElementById('ops-events');
    if (!events.length) {
        container.innerHTML = '<p class="px-6 py-8 text-center text-sm text-gray-400">아직 운영 이벤트가 없습니다</p>';
        return;
    }
    container.innerHTML = events.slice().reverse().map((event) => {
        const fields = event.fields || {};
        const detailParts = Object.entries(fields)
            .filter(([key]) => !['event', 'message'].includes(key))
            .slice(0, 6)
            .map(([key, value]) => `${key}=${value}`);
        return `
            <div class="border-l-4 px-4 py-3 ${eventLevelClass(event.level)}">
                <div class="flex flex-wrap items-center gap-2">
                    <span class="font-mono text-xs font-semibold text-gray-800">${escapeHtml(event.event)}</span>
                    <span class="text-xs text-gray-400">${escapeHtml(fmtTs(event.ts))}</span>
                </div>
                <p class="mt-1 text-sm text-gray-700">${escapeHtml(event.message || event.event)}</p>
                ${detailParts.length ? `<p class="mt-1 font-mono text-xs text-gray-500">${escapeHtml(detailParts.join(' · '))}</p>` : ''}
            </div>
        `;
    }).join('');
}

async function loadOpsSnapshot() {
    const res = await fetch('/api/admin/ops/snapshot');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
}

async function refresh() {
    try {
        const snapshot = await loadOpsSnapshot();
        renderKpis(snapshot);
        renderActiveRuns(snapshot.runs || {});
        renderActiveSuites(snapshot.suites || {});
        renderSchedules(snapshot.schedules || {});
        renderEvents(snapshot.recent_events || []);
        document.getElementById('ops-refresh-meta').textContent =
            `갱신 ${fmtTs(snapshot.generated_at)} · log ${snapshot.runtime?.log_format || 'console'}`;
    } catch (err) {
        document.getElementById('ops-refresh-meta').textContent = `오류: ${err.message}`;
    }
}

document.getElementById('btn-ops-refresh').addEventListener('click', () => { refresh(); });
refresh();
setInterval(refresh, REFRESH_MS);
