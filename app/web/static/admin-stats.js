'use strict';

const CHART_IDS = [
    'chart-system-runs',
    'chart-user-runs',
    'chart-system-savings',
    'chart-module-pass-fail',
];

const PLOTLY_CONFIG = {
    displayModeBar: false,
    responsive: true,
    locale: 'ko',
};

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text ?? '';
    return div.innerHTML;
}

function fmtSavedSeconds(seconds) {
    const s = Math.round(seconds || 0);
    if (s < 60) return `${s}초`;
    if (s >= 3600) {
        const h = Math.floor(s / 3600);
        const m = Math.floor((s % 3600) / 60);
        return `${h}시간 ${String(m).padStart(2, '0')}분`;
    }
    const m = Math.floor(s / 60);
    const rem = s % 60;
    return `${m}분 ${rem}초`;
}

function toLocalDatetimeValue(date) {
    const pad = (n) => String(n).padStart(2, '0');
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function setThisMonthDates() {
    const now = new Date();
    const firstOfMonth = new Date(now.getFullYear(), now.getMonth(), 1, 0, 0);
    document.getElementById('filter-from').value = toLocalDatetimeValue(firstOfMonth);
    document.getElementById('filter-to').value = toLocalDatetimeValue(now);
}

function setLastMonthDates() {
    const now = new Date();
    const firstOfLastMonth = new Date(now.getFullYear(), now.getMonth() - 1, 1, 0, 0);
    const lastOfLastMonth = new Date(now.getFullYear(), now.getMonth(), 0, 23, 59);
    document.getElementById('filter-from').value = toLocalDatetimeValue(firstOfLastMonth);
    document.getElementById('filter-to').value = toLocalDatetimeValue(lastOfLastMonth);
}

function fmtPeriodLabel(iso) {
    if (!iso) return '';
    return new Date(iso).toLocaleString('ko-KR', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
    });
}

function updateStatsMeta(data) {
    const parts = [];
    if (data.period_from || data.period_to) {
        const from = fmtPeriodLabel(data.period_from);
        const to = fmtPeriodLabel(data.period_to);
        if (from && to) parts.push(`기간: ${from} ~ ${to}`);
        else if (from) parts.push(`시작: ${from}`);
        else if (to) parts.push(`종료: ${to}`);
    }
    const gen = data.generated_at ? fmtPeriodLabel(data.generated_at) : '';
    if (gen) parts.push(`생성: ${gen}`);
    document.getElementById('stats-meta').textContent = parts.join(' · ');
}

function isEmptyPlotlyFigure(figure) {
    if (!figure || !figure.layout) return true;
    const annotations = figure.layout.annotations || [];
    return annotations.some((a) => a.text === '표시할 데이터가 없습니다.');
}

function setChartEmpty(chartId, isEmpty) {
    const plotEl = document.getElementById(chartId);
    const emptyEl = document.querySelector(`[data-empty-for="${chartId}"]`);
    if (!plotEl || !emptyEl) return;
    plotEl.classList.toggle('is-hidden', isEmpty);
    emptyEl.classList.toggle('is-hidden', !isEmpty);
}

function destroyCharts() {
    if (typeof Plotly === 'undefined') return;
    CHART_IDS.forEach((id) => {
        const el = document.getElementById(id);
        if (el) Plotly.purge(el);
    });
}

function renderPlotlyChart(chartId, figure) {
    const el = document.getElementById(chartId);
    if (!el || typeof Plotly === 'undefined') return;

    if (isEmptyPlotlyFigure(figure)) {
        Plotly.purge(el);
        setChartEmpty(chartId, true);
        return;
    }

    setChartEmpty(chartId, false);
    const layout = {
        ...figure.layout,
        autosize: true,
    };
    Plotly.react(el, figure.data || [], layout, PLOTLY_CONFIG);
}

function renderCharts(data) {
    destroyCharts();
    const charts = data.charts || {};
    CHART_IDS.forEach((id) => {
        renderPlotlyChart(id, charts[id]);
    });
}

function renderUserTable(data) {
    const userTbody = document.getElementById('user-stats-tbody');
    if (!data.by_user || data.by_user.length === 0) {
        userTbody.innerHTML = '<tr><td colspan="5" class="px-4 py-8 text-center text-sm text-gray-400">데이터 없음</td></tr>';
        return;
    }
    userTbody.innerHTML = data.by_user.map((u) => `<tr class="hover:bg-gray-50">
        <td class="px-4 py-3 font-medium">${escapeHtml(u.user_name || '(시스템)')}</td>
        <td class="px-4 py-3 text-right">${u.total_runs}</td>
        <td class="px-4 py-3 text-right text-green-700">${u.total_modules_passed}</td>
        <td class="px-4 py-3 text-right text-red-600">${u.total_modules_failed}</td>
        <td class="px-4 py-3 text-right font-semibold text-green-700">${fmtSavedSeconds(u.manual_seconds_saved)}</td>
    </tr>`).join('');
}

function renderSystemTable(data) {
    const sysTbody = document.getElementById('sys-stats-tbody');
    if (!data.by_system || data.by_system.length === 0) {
        sysTbody.innerHTML = '<tr><td colspan="5" class="px-4 py-8 text-center text-sm text-gray-400">데이터 없음</td></tr>';
        return;
    }
    sysTbody.innerHTML = data.by_system.map((s) => `<tr class="hover:bg-gray-50">
        <td class="px-4 py-3 font-medium">${escapeHtml(s.system_name)}</td>
        <td class="px-4 py-3 text-right">${s.runs}</td>
        <td class="px-4 py-3 text-right text-green-700">${s.modules_passed}</td>
        <td class="px-4 py-3 text-right text-red-600">${s.modules_failed}</td>
        <td class="px-4 py-3 text-right font-semibold text-green-700">${fmtSavedSeconds(s.manual_seconds_saved)}</td>
    </tr>`).join('');
}

function updateKpis(data) {
    document.getElementById('stat-total-runs').textContent = data.total_runs;
    document.getElementById('stat-total-users').textContent = data.total_users;
    const totalPassed = (data.by_system || []).reduce((s, x) => s + x.modules_passed, 0);
    document.getElementById('stat-total-passed').textContent = totalPassed;
    const totalSaved = (data.by_system || []).reduce((s, x) => s + (x.manual_seconds_saved || 0), 0);
    document.getElementById('stat-total-saved').textContent = fmtSavedSeconds(totalSaved);
}

async function loadStats() {
    const btnLoad = document.getElementById('btn-load');
    btnLoad.disabled = true;
    btnLoad.classList.add('opacity-70');

    try {
        const from = document.getElementById('filter-from').value;
        const to = document.getElementById('filter-to').value;
        const params = new URLSearchParams();
        if (from) params.set('from', new Date(from).toISOString());
        if (to) params.set('to', new Date(to).toISOString());

        const res = await fetch('/api/admin/stats/usage?' + params.toString());
        if (!res.ok) {
            alert('통계 조회에 실패했습니다.');
            return;
        }
        const data = await res.json();

        updateKpis(data);
        updateStatsMeta(data);
        renderCharts(data);
        renderUserTable(data);
        renderSystemTable(data);
    } finally {
        btnLoad.disabled = false;
        btnLoad.classList.remove('opacity-70');
    }
}

document.getElementById('btn-load').addEventListener('click', loadStats);
document.getElementById('btn-last-month').addEventListener('click', () => {
    setLastMonthDates();
    loadStats();
});
document.getElementById('btn-this-month').addEventListener('click', () => {
    setThisMonthDates();
    loadStats();
});
document.getElementById('btn-csv').addEventListener('click', () => {
    const from = document.getElementById('filter-from').value;
    const to = document.getElementById('filter-to').value;
    const params = new URLSearchParams();
    if (from) params.set('from', new Date(from).toISOString());
    if (to) params.set('to', new Date(to).toISOString());
    window.location.href = '/api/admin/stats/savings/csv?' + params.toString();
});

setThisMonthDates();
loadStats();
