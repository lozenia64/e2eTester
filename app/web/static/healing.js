// 자가 치유 센터 — /api/healing/* 를 불러와 3탭(복구 콘솔/승인 대기 패치/내구성 맵)을 렌더한다.
// self_healing.html 이 로드된 페이지에서만 동작한다(다른 페이지에서는 no-op).

(() => {
  const root = document.querySelector(".heal");
  if (!root) return;

  const $ = (sel, el = document) => el.querySelector(sel);
  const $$ = (sel, el = document) => Array.from(el.querySelectorAll(sel));

  const ACTION_META = {
    AUTO_HEALED: { label: "자동 복구", pill: "bg-green-100 text-green-700" },
    SUGGESTED: { label: "승인 대기 제안", pill: "bg-amber-100 text-amber-700" },
    NO_CANDIDATE: { label: "복구 실패", pill: "bg-red-100 text-red-700" },
  };
  const GRADE_META = {
    green: { label: "안정", dot: "heal-dot--green" },
    amber: { label: "주의", dot: "heal-dot--amber" },
    red: { label: "취약", dot: "heal-dot--red" },
  };

  const state = {
    metrics: null,
    events: [],
    systems: [],
    policies: [],
    patches: [],
    patchCounts: {},
    durability: null,
    filterSystem: "",
    patchStatus: "PROPOSED",
    durSystem: "",
    durGrade: "",
  };

  const esc = (v) =>
    String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  function relTime(iso) {
    if (!iso) return "";
    const diff = Date.now() - new Date(iso).getTime();
    const min = Math.floor(diff / 60000);
    if (min < 1) return "방금";
    if (min < 60) return `${min}분 전`;
    const hr = Math.floor(min / 60);
    if (hr < 24) return `${hr}시간 전`;
    const day = Math.floor(hr / 24);
    if (day < 30) return `${day}일 전`;
    return new Date(iso).toLocaleDateString("ko-KR");
  }

  function fmtMs(ms) {
    if (ms == null) return "–";
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(1)}초`;
  }

  async function getJson(url) {
    const res = await fetch(url, { headers: { Accept: "application/json" } });
    if (!res.ok) throw new Error(`${url}: ${res.status}`);
    return res.json();
  }

  async function send(url, method, body) {
    const res = await fetch(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!res.ok) {
      let detail = `${res.status}`;
      try { detail = (await res.json()).detail || detail; } catch (_) { /* noop */ }
      throw new Error(detail);
    }
    return res.json();
  }

  // ── 로드 ────────────────────────────────────────────────────────────────
  async function load() {
    $("#heal-loading")?.classList.remove("hidden");
    $("#heal-error")?.classList.add("hidden");
    try {
      const [metrics, events, policies, patches, durability] = await Promise.all([
        getJson("/api/healing/metrics"),
        getJson("/api/healing/events"),
        getJson("/api/healing/policy"),
        getJson(`/api/healing/patches${state.patchStatus ? `?status=${state.patchStatus}` : ""}`),
        getJson("/api/healing/durability"),
      ]);
      state.metrics = metrics;
      state.events = events.items || [];
      state.systems = events.systems || [];
      state.policies = policies.policies || [];
      state.patches = patches.items || [];
      state.patchCounts = patches.counts || {};
      state.durability = durability;
      renderAll();
    } catch (_) {
      $("#heal-error")?.classList.remove("hidden");
    } finally {
      $("#heal-loading")?.classList.add("hidden");
    }
  }

  async function reloadPatches() {
    const data = await getJson(`/api/healing/patches${state.patchStatus ? `?status=${state.patchStatus}` : ""}`);
    state.patches = data.items || [];
    state.patchCounts = data.counts || {};
    renderPatches();
    renderKpi();
  }

  function renderAll() {
    renderKpi();
    renderPolicies();
    populateSystemFilters();
    renderEvents();
    renderChronic();
    renderPatches();
    renderDurability();
    revealAll();
  }

  function revealAll() {
    requestAnimationFrame(() => $$(".heal-reveal").forEach((el) => el.classList.add("is-in")));
  }

  // ── KPI ─────────────────────────────────────────────────────────────────
  function renderKpi() {
    const kpi = state.metrics?.kpi || {};
    $('[data-kpi="month_auto_recovered"]').textContent = kpi.month_auto_recovered ?? 0;
    $('[data-kpi="unattended_rate"]').textContent =
      kpi.unattended_rate == null ? "–" : `${kpi.unattended_rate}%`;
    $('[data-kpi="mttr"]').textContent = fmtMs(kpi.mttr_ms);
    const pending = state.patchCounts.proposed ?? kpi.pending_patches ?? 0;
    $('[data-kpi="pending_patches"]').textContent = pending;
    const tabBadge = $("#heal-tab-patch-count");
    tabBadge.textContent = pending;
    tabBadge.classList.toggle("hidden", !pending);
    const navBadge = document.getElementById("nav-healing-badge");
    if (navBadge) {
      navBadge.textContent = pending > 99 ? "99+" : String(pending);
      navBadge.classList.toggle("hidden", !pending);
    }
  }

  // ── 정책 패널 ────────────────────────────────────────────────────────────
  function renderPolicies() {
    const list = $("#heal-policy-list");
    list.innerHTML = "";
    for (const policy of state.policies) {
      const row = document.createElement("div");
      row.className = "flex flex-wrap items-center gap-3 rounded-xl border border-gray-100 bg-gray-50/60 px-3 py-2";
      const pct = Math.round(policy.confidence_threshold * 100);
      row.innerHTML = `
        <span class="w-44 truncate text-xs font-bold text-gray-700">${esc(policy.system_name || policy.system_code)}
          ${policy.system_code === "*" ? "" : `<span class="font-mono text-[10px] text-gray-400">${esc(policy.system_code)}</span>`}
        </span>
        <label class="flex items-center gap-1.5 text-[11px] font-semibold text-gray-500">
          <input type="checkbox" data-role="enabled" ${policy.auto_heal_enabled ? "checked" : ""}
                 class="h-3.5 w-3.5 rounded border-gray-300 text-indigo-600">
          auto-heal
        </label>
        <input type="range" data-role="threshold" min="50" max="99" value="${pct}"
               class="h-1.5 flex-1 min-w-[8rem] accent-indigo-600">
        <span data-role="threshold-label" class="w-20 text-right font-mono text-[11px] text-gray-500">신뢰도 ≥ ${pct}%</span>
        <button type="button" data-role="save"
                class="rounded-lg bg-white px-2.5 py-1 text-[11px] font-semibold text-indigo-600 shadow-sm ring-1 ring-gray-200 hover:bg-indigo-50">저장</button>
      `;
      const slider = row.querySelector('[data-role="threshold"]');
      const label = row.querySelector('[data-role="threshold-label"]');
      slider.addEventListener("input", () => { label.textContent = `신뢰도 ≥ ${slider.value}%`; });
      row.querySelector('[data-role="save"]').addEventListener("click", async () => {
        try {
          const data = await send("/api/healing/policy", "PUT", {
            policies: [{
              system_code: policy.system_code,
              auto_heal_enabled: row.querySelector('[data-role="enabled"]').checked,
              confidence_threshold: Number(slider.value) / 100,
            }],
          });
          state.policies = data.policies || [];
          renderPolicies();
          const saved = $("#heal-policy-saved");
          saved.classList.remove("hidden");
          setTimeout(() => saved.classList.add("hidden"), 1500);
        } catch (err) {
          alert(`정책 저장 실패: ${err.message}`);
        }
      });
      list.appendChild(row);
    }
  }

  // ── 치유 이벤트(파이프라인 카드) ─────────────────────────────────────────
  function populateSystemFilters() {
    for (const sel of [$("#heal-filter-system"), $("#heal-dur-system")]) {
      if (!sel) continue;
      const current = sel.value;
      const isDur = sel.id === "heal-dur-system";
      sel.innerHTML = '<option value="">전체 시스템</option>';
      const values = isDur
        ? [...new Set((state.durability?.rows || []).map((r) => r.system))]
        : state.systems.map((s) => s.system_code);
      for (const value of values) {
        const opt = document.createElement("option");
        opt.value = value;
        opt.textContent = isDur
          ? value
          : (state.systems.find((s) => s.system_code === value)?.system_name || value);
        sel.appendChild(opt);
      }
      sel.value = current || "";
    }
  }

  function pipelineHtml(ev) {
    const verified = ev.retry_succeeded === true;
    const failedRetry = ev.retry_succeeded === false;
    const stages = [
      { label: "① 탐지", on: true, note: ev.broken_selector },
      { label: "② AI 진단", on: ev.candidates_considered > 0, note: `후보 ${ev.candidates_considered}개` },
      { label: "③ 대체 셀렉터", on: !!ev.healed_selector, note: ev.healed_selector || "후보 없음" },
      { label: "④ 재실행 검증", on: verified ? true : failedRetry ? "fail" : false, note: verified ? "성공" : failedRetry ? "실패" : "미실행" },
      { label: "⑤ 결과", on: ev.action === "AUTO_HEALED" ? verified || "fail" : ev.action === "SUGGESTED" ? true : "fail", note: ACTION_META[ev.action]?.label || ev.action },
    ];
    return `<div class="heal-pipe">${stages
      .map(
        (s, i) => `${i ? '<span class="heal-pipe__arrow">→</span>' : ""}
          <span class="heal-pipe__stage" data-on="${s.on === true ? "true" : s.on === "fail" ? "fail" : "false"}" title="${esc(s.note)}">${s.label}</span>`
      )
      .join("")}</div>`;
  }

  function gaugeHtml(confidence) {
    const pct = Math.round((confidence || 0) * 100);
    const color = pct >= 75 ? "var(--st-passed)" : pct >= 50 ? "var(--st-anomaly)" : "var(--st-error)";
    return `
      <div class="flex items-center gap-2">
        <div class="heal-gauge w-28"><div class="heal-gauge__fill" style="width:${pct}%;background:${color}"></div></div>
        <span class="font-mono text-[11px] font-bold text-gray-600">${pct}%</span>
      </div>`;
  }

  function renderEvents() {
    const list = $("#heal-event-list");
    list.innerHTML = "";
    const items = state.events.filter(
      (ev) => !state.filterSystem || ev.system_code === state.filterSystem
    );
    $("#heal-event-empty").classList.toggle("hidden", items.length > 0);
    for (const ev of items.slice(0, 60)) {
      const meta = ACTION_META[ev.action] || { label: ev.action, pill: "bg-gray-100 text-gray-600" };
      const card = document.createElement("article");
      card.className = "heal-reveal heal-card rounded-2xl border border-gray-100 bg-white p-4 shadow-sm";
      card.innerHTML = `
        <div class="flex flex-wrap items-center gap-2">
          <span class="rounded-full px-2 py-0.5 text-[11px] font-bold ${meta.pill}">${meta.label}</span>
          <span class="text-xs font-semibold text-gray-500">${esc(ev.system_name || ev.system_code)}</span>
          <span class="text-gray-300">·</span>
          <span class="text-sm font-bold text-gray-900">${esc(ev.module_name || ev.module_id)}</span>
          ${ev.heal_count >= 3 ? '<span class="rounded bg-red-100 px-1.5 py-0.5 text-[10px] font-bold text-red-700">만성 ' + ev.heal_count + "회</span>" : ""}
          <span class="ml-auto text-[11px] text-gray-400">${relTime(ev.created_at)} · ${fmtMs(ev.duration_ms)}</span>
        </div>
        <div class="mt-3">${pipelineHtml(ev)}</div>
        <div class="mt-3 grid gap-2 text-xs sm:grid-cols-2">
          <div class="rounded-lg bg-red-50/70 px-2.5 py-1.5">
            <p class="text-[10px] font-bold text-red-400">깨진 셀렉터</p>
            <p class="break-all font-mono text-[11px] text-red-700">${esc(ev.broken_selector)}</p>
          </div>
          <div class="rounded-lg bg-green-50/70 px-2.5 py-1.5">
            <p class="text-[10px] font-bold text-green-500">대체 셀렉터</p>
            <p class="break-all font-mono text-[11px] text-green-700">${esc(ev.healed_selector || "—")}</p>
          </div>
        </div>
        <div class="mt-2.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-gray-400">
          ${gaugeHtml(ev.confidence)}
          <a href="/runs/${esc(ev.run_id)}" class="font-medium text-indigo-600 hover:underline">Run 보기 →</a>
          ${ev.page_url ? `<span class="truncate max-w-[18rem]" title="${esc(ev.page_url)}">${esc(ev.page_url)}</span>` : ""}
        </div>
        ${ev.error_excerpt ? `<details class="mt-2 text-[11px] text-gray-400"><summary class="cursor-pointer font-semibold">실패 로그 발췌</summary><pre class="mt-1 overflow-x-auto rounded-lg bg-gray-50 p-2 font-mono text-[10px] leading-relaxed text-gray-500">${esc(ev.error_excerpt)}</pre></details>` : ""}
      `;
      list.appendChild(card);
    }
  }

  function renderChronic() {
    const wrap = $("#heal-chronic");
    const rows = state.metrics?.chronic || [];
    if (!rows.length) {
      wrap.innerHTML = '<p class="text-xs text-gray-400">만성으로 승격된 셀렉터가 없습니다. 👍</p>';
      return;
    }
    wrap.innerHTML = `
      <table class="w-full min-w-[36rem] text-left text-xs">
        <thead><tr class="text-[11px] text-gray-400">
          <th class="py-1.5 pr-3 font-semibold">시스템</th>
          <th class="py-1.5 pr-3 font-semibold">셀렉터</th>
          <th class="py-1.5 pr-3 font-semibold">치유 횟수</th>
          <th class="py-1.5 pr-3 font-semibold">최근 대체</th>
          <th class="py-1.5 font-semibold">마지막 발생</th>
        </tr></thead>
        <tbody>${rows
          .map(
            (r) => `<tr class="border-t border-gray-100">
              <td class="py-2 pr-3 font-semibold text-gray-600">${esc(r.system_code)}</td>
              <td class="py-2 pr-3 break-all font-mono text-[11px] text-gray-700">${esc(r.broken_selector)}</td>
              <td class="py-2 pr-3"><span class="rounded bg-red-100 px-1.5 py-0.5 font-bold text-red-700">${r.heal_count}회</span></td>
              <td class="py-2 pr-3 break-all font-mono text-[11px] text-gray-500">${esc(r.last_healed_selector || "—")}</td>
              <td class="py-2 text-gray-400">${relTime(r.last_seen)}</td>
            </tr>`
          )
          .join("")}</tbody>
      </table>`;
  }

  // ── 패치 ────────────────────────────────────────────────────────────────
  function diffHtml(diff) {
    return (diff || "")
      .split("\n")
      .slice(0, 80)
      .map((line) => {
        const cls = line.startsWith("+") ? "add" : line.startsWith("-") ? "del" : "meta";
        return `<span class="${cls}">${esc(line) || "&nbsp;"}</span>`;
      })
      .join("");
  }

  function renderPatches() {
    const list = $("#heal-patch-list");
    list.innerHTML = "";
    $("#heal-patch-empty").classList.toggle("hidden", state.patches.length > 0);
    for (const patch of state.patches) {
      const card = document.createElement("article");
      card.className = "heal-reveal heal-card rounded-2xl border border-gray-100 bg-white p-4 shadow-sm";
      const statusPill =
        patch.status === "PROPOSED"
          ? '<span class="rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-bold text-amber-700">승인 대기</span>'
          : patch.status === "APPROVED"
            ? `<span class="rounded-full bg-green-100 px-2 py-0.5 text-[11px] font-bold text-green-700">승인됨${patch.applied ? " · 소스 반영" : ""}</span>`
            : '<span class="rounded-full bg-gray-100 px-2 py-0.5 text-[11px] font-bold text-gray-500">거절됨</span>';
      card.innerHTML = `
        <div class="flex flex-wrap items-center gap-2">
          ${statusPill}
          <span class="text-xs font-semibold text-gray-500">${esc(patch.system_name || patch.system_code)}</span>
          <span class="break-all font-mono text-[11px] text-gray-400">${esc(patch.file_path)}</span>
          <span class="ml-auto text-[11px] text-gray-400">${relTime(patch.created_at)}</span>
        </div>
        <div class="mt-2 flex flex-wrap items-center gap-2 text-[11px]">
          <span class="break-all rounded bg-red-50 px-1.5 py-0.5 font-mono text-red-700">${esc(patch.broken_selector)}</span>
          <span class="text-gray-300">→</span>
          <span class="break-all rounded bg-green-50 px-1.5 py-0.5 font-mono text-green-700">${esc(patch.healed_selector)}</span>
          <span class="text-gray-400">(${patch.occurrences}곳)</span>
        </div>
        ${(patch.warnings || []).map((w) => `<p class="mt-2 rounded-lg bg-amber-50 px-2.5 py-1.5 text-[11px] text-amber-700">⚠ ${esc(w)}</p>`).join("")}
        <pre class="heal-diff mt-3 rounded-xl bg-gray-50 p-3 font-mono">${diffHtml(patch.diff)}</pre>
        ${patch.decided_by ? `<p class="mt-2 text-[11px] text-gray-400">${esc(patch.status === "APPROVED" ? "승인" : "거절")}: ${esc(patch.decided_by)} · ${relTime(patch.decided_at)}${patch.note ? ` · ${esc(patch.note)}` : ""}</p>` : ""}
        <div class="mt-3 flex flex-wrap items-center gap-2 border-t border-gray-100 pt-3" data-role="actions"></div>
      `;
      const actions = card.querySelector('[data-role="actions"]');
      const dl = document.createElement("a");
      dl.href = `/api/healing/patches/${encodeURIComponent(patch.patch_id)}/download`;
      dl.className = "rounded-lg bg-white px-2.5 py-1.5 text-[11px] font-semibold text-gray-600 shadow-sm ring-1 ring-gray-200 hover:bg-gray-50";
      dl.textContent = ".patch 다운로드";
      actions.appendChild(dl);
      if (patch.status === "PROPOSED") {
        const approve = document.createElement("button");
        approve.type = "button";
        approve.className = "rounded-lg bg-indigo-600 px-3 py-1.5 text-[11px] font-bold text-white shadow-sm hover:bg-indigo-500";
        approve.textContent = "승인 → 소스 반영";
        approve.addEventListener("click", async () => {
          if (!confirm(`승인하면 ${patch.file_path} 의 셀렉터가 즉시 교체됩니다. 진행할까요?`)) return;
          try {
            await send(`/api/healing/patches/${encodeURIComponent(patch.patch_id)}/approve`, "POST", {});
            await reloadPatches();
          } catch (err) {
            alert(`승인 실패: ${err.message}`);
          }
        });
        const reject = document.createElement("button");
        reject.type = "button";
        reject.className = "rounded-lg bg-white px-3 py-1.5 text-[11px] font-semibold text-red-600 shadow-sm ring-1 ring-red-200 hover:bg-red-50";
        reject.textContent = "거절";
        reject.addEventListener("click", async () => {
          const note = prompt("거절 사유(선택):", "") ?? "";
          try {
            await send(`/api/healing/patches/${encodeURIComponent(patch.patch_id)}/reject`, "POST", { note });
            await reloadPatches();
          } catch (err) {
            alert(`거절 실패: ${err.message}`);
          }
        });
        actions.append(approve, reject);
      }
      list.appendChild(card);
    }
    revealAll();
  }

  // ── 내구성 맵 ────────────────────────────────────────────────────────────
  function renderDurability() {
    const dur = state.durability;
    if (!dur) return;
    for (const grade of ["green", "amber", "red"]) {
      $(`[data-dur="${grade}"]`).textContent = dur.summary?.[grade] ?? 0;
    }

    const repair = $("#heal-repair");
    const repairRows = dur.needs_repair || [];
    repair.innerHTML = repairRows.length
      ? repairRows
          .map(
            (r) => `<div class="flex flex-wrap items-center gap-2 rounded-xl border border-red-100 bg-red-50/60 px-3 py-2 text-xs">
              <span class="rounded bg-red-100 px-1.5 py-0.5 font-bold text-red-700">${r.heal_count}회+ 깨짐</span>
              <span class="break-all font-mono text-[11px] text-gray-700">${esc(r.selector)}</span>
              <span class="ml-auto font-mono text-[10px] text-gray-400">${esc(r.file)}:${r.line}</span>
            </div>`
          )
          .join("")
      : '<p class="text-xs text-gray-400">반복해서 깨진 셀렉터가 없습니다. 👍</p>';

    const durTable = (rows) => `
      <table class="w-full min-w-[42rem] text-left text-xs">
        <thead><tr class="text-[11px] text-gray-400">
          <th class="py-1.5 pr-3 font-semibold">등급</th>
          <th class="py-1.5 pr-3 font-semibold">셀렉터</th>
          <th class="py-1.5 pr-3 font-semibold">시스템</th>
          <th class="py-1.5 pr-3 font-semibold">위치</th>
          <th class="py-1.5 pr-3 font-semibold">안정성</th>
          <th class="py-1.5 pr-3 font-semibold">치유 이력</th>
          <th class="py-1.5 font-semibold">비고</th>
        </tr></thead>
        <tbody>${rows
          .map((r) => {
            const g = GRADE_META[r.grade] || GRADE_META.amber;
            return `<tr class="border-t border-gray-100">
              <td class="py-2 pr-3 whitespace-nowrap"><span class="heal-dot ${g.dot} mr-1"></span>${g.label}</td>
              <td class="py-2 pr-3 break-all font-mono text-[11px] text-gray-700">${esc(r.selector)}</td>
              <td class="py-2 pr-3 whitespace-nowrap text-gray-500">${esc(r.system)}</td>
              <td class="py-2 pr-3 whitespace-nowrap font-mono text-[10px] text-gray-400">${esc(r.file.split("/").slice(-2).join("/"))}:${r.line}</td>
              <td class="py-2 pr-3 font-mono">${r.score}점</td>
              <td class="py-2 pr-3">${r.heal_count ? `<span class="rounded bg-red-100 px-1.5 py-0.5 font-bold text-red-700">${r.heal_count}회</span>` : '<span class="text-gray-300">—</span>'}</td>
              <td class="py-2 text-[11px] text-gray-400">${esc((r.notes || []).join(" / "))}</td>
            </tr>`;
          })
          .join("")}</tbody>
      </table>`;

    $("#heal-top-risky").innerHTML = durTable(dur.top_risky || []);

    const filtered = (dur.rows || []).filter(
      (r) =>
        (!state.durSystem || r.system === state.durSystem) &&
        (!state.durGrade || r.grade === state.durGrade)
    );
    // 취약(위험) 순으로 정렬해 상위 300개까지 표시.
    filtered.sort((a, b) => b.risk - a.risk);
    $("#heal-dur-table").innerHTML = filtered.length
      ? durTable(filtered.slice(0, 300))
      : '<p class="text-xs text-gray-400">조건에 맞는 셀렉터가 없습니다.</p>';
  }

  // ── 탭/필터 이벤트 ───────────────────────────────────────────────────────
  $$(".heal-tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      $$(".heal-tab").forEach((t) => t.setAttribute("aria-selected", String(t === tab)));
      $$("[data-panel]").forEach((panel) =>
        panel.classList.toggle("hidden", panel.dataset.panel !== tab.dataset.tab)
      );
      revealAll();
    });
  });
  $("#heal-filter-system")?.addEventListener("change", (e) => {
    state.filterSystem = e.target.value;
    renderEvents();
    revealAll();
  });
  $("#heal-patch-status")?.addEventListener("change", async (e) => {
    state.patchStatus = e.target.value;
    await reloadPatches();
  });
  $("#heal-dur-system")?.addEventListener("change", (e) => {
    state.durSystem = e.target.value;
    renderDurability();
  });
  $("#heal-dur-grade")?.addEventListener("change", (e) => {
    state.durGrade = e.target.value;
    renderDurability();
  });
  $("#heal-refresh")?.addEventListener("click", load);

  load();
})();
