// 사이드바·햄버거 알림 배지 — 로드 시 + 주기 갱신(가벼운 실패 무시)
(() => {
    const BADGE_REFRESH_MS = 60_000;
    const counts = { anomaly: 0, healing: 0, schedule: 0 };

    function badgeNodes(kind) {
        return document.querySelectorAll(`[data-nav-badge="${kind}"]`);
    }

    function updateHamburgerAttention(total) {
        const node = document.getElementById("mobile-nav-attention-badge");
        if (!node) {
            return;
        }
        if (total > 0) {
            node.textContent = total > 99 ? "99+" : String(total);
            node.classList.remove("hidden");
            node.removeAttribute("aria-hidden");
            const toggle = document.getElementById("mobile-nav-toggle");
            if (toggle && toggle.getAttribute("aria-expanded") !== "true") {
                const unread = total > 99 ? "99건 이상" : `${total}건`;
                toggle.setAttribute("aria-label", `메뉴 열기, 조치 필요 ${unread}`);
            }
        } else {
            node.textContent = "";
            node.classList.add("hidden");
            node.setAttribute("aria-hidden", "true");
            const toggle = document.getElementById("mobile-nav-toggle");
            if (toggle && toggle.getAttribute("aria-expanded") !== "true") {
                toggle.setAttribute("aria-label", "메뉴 열기");
            }
        }
    }

    function setBadgeCount(kind, count) {
        const label = count > 99 ? "99+" : String(count);
        badgeNodes(kind).forEach((node) => {
            if (count > 0) {
                node.textContent = label;
                node.classList.remove("hidden");
                node.removeAttribute("aria-hidden");
            } else {
                node.textContent = "";
                node.classList.add("hidden");
                node.setAttribute("aria-hidden", "true");
            }
        });
        counts[kind] = count;
        updateHamburgerAttention(counts.anomaly + counts.healing + counts.schedule);
    }

    function setCounts(partial) {
        if (partial.anomaly != null) {
            setBadgeCount("anomaly", partial.anomaly);
        }
        if (partial.healing != null) {
            setBadgeCount("healing", partial.healing);
        }
        if (partial.schedule != null) {
            setBadgeCount("schedule", partial.schedule);
        }
    }

    async function fetchJson(url) {
        try {
            const res = await fetch(url, { headers: { Accept: "application/json" } });
            if (!res.ok) {
                return null;
            }
            return await res.json();
        } catch {
            return null;
        }
    }

    async function refreshNavBadges() {
        const [anomalies, healing, schedules] = await Promise.all([
            fetchJson("/api/anomalies"),
            fetchJson("/api/healing/patches?status=PROPOSED"),
            fetchJson("/api/schedules/board"),
        ]);

        const partial = {};
        if (anomalies != null) {
            partial.anomaly = anomalies.counts?.unresolved || 0;
        }
        if (healing != null) {
            partial.healing = healing.counts?.proposed || 0;
        }
        if (schedules != null) {
            partial.schedule = schedules.kpi?.attention || 0;
        }

        if (Object.keys(partial).length > 0) {
            setCounts(partial);
        }
    }

    window.E2ENavBadges = {
        refresh: refreshNavBadges,
        setCounts,
        syncHamburgerLabel() {
            updateHamburgerAttention(counts.anomaly + counts.healing + counts.schedule);
        },
    };

    refreshNavBadges().catch(() => { /* noop */ });

    window.setInterval(() => {
        if (!document.hidden) {
            refreshNavBadges().catch(() => { /* noop */ });
        }
    }, BADGE_REFRESH_MS);

    document.addEventListener("visibilitychange", () => {
        if (!document.hidden) {
            refreshNavBadges().catch(() => { /* noop */ });
        }
    });
})();
