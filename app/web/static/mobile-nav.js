// 모바일 슬라이드 내비게이션 — base.html · admin/base.html 공용
(() => {
    const toggle = document.getElementById("mobile-nav-toggle");
    const closeBtn = document.getElementById("mobile-nav-close");
    const backdrop = document.getElementById("mobile-nav-backdrop");
    const sidebar = document.getElementById("app-sidebar");
    if (!toggle || !backdrop || !sidebar) {
        return;
    }

    const desktopMq = window.matchMedia("(min-width: 768px)");
    let isOpen = false;
    let scrollLockY = 0;
    let scrollLocked = false;

    function isMobileNav() {
        return !desktopMq.matches;
    }

    function lockBodyScroll() {
        if (scrollLocked) {
            return;
        }
        scrollLockY = window.scrollY || window.pageYOffset || 0;
        document.body.style.position = "fixed";
        document.body.style.top = `-${scrollLockY}px`;
        document.body.style.left = "0";
        document.body.style.right = "0";
        document.body.style.width = "100%";
        scrollLocked = true;
    }

    function unlockBodyScroll() {
        if (!scrollLocked) {
            return;
        }
        document.body.style.position = "";
        document.body.style.top = "";
        document.body.style.left = "";
        document.body.style.right = "";
        document.body.style.width = "";
        window.scrollTo(0, scrollLockY);
        scrollLocked = false;
    }

    function focusableElements(root) {
        return Array.from(
            root.querySelectorAll(
                'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
            ),
        ).filter((el) => !el.closest(".is-hidden") && el.offsetParent !== null);
    }

    function setSidebarInert(hidden) {
        if (hidden && isMobileNav()) {
            sidebar.setAttribute("inert", "");
            sidebar.setAttribute("aria-hidden", "true");
        } else {
            sidebar.removeAttribute("inert");
            sidebar.removeAttribute("aria-hidden");
        }
    }

    function setMobileNavOpen(open) {
        const active = open && isMobileNav();
        isOpen = active;

        sidebar.classList.toggle("is-open", active);
        backdrop.classList.toggle("is-open", active);
        toggle.classList.toggle("is-open", active);
        toggle.setAttribute("aria-expanded", active ? "true" : "false");
        if (active) {
            toggle.setAttribute("aria-label", "메뉴 닫기");
        } else {
            window.E2ENavBadges?.syncHamburgerLabel?.();
        }
        backdrop.setAttribute("aria-hidden", active ? "false" : "true");
        document.body.classList.toggle("mobile-nav-open", active);
        if (active) {
            lockBodyScroll();
        } else {
            unlockBodyScroll();
        }
        setSidebarInert(!active);

        if (active) {
            sidebar.setAttribute("role", "dialog");
            sidebar.setAttribute("aria-modal", "true");
            toggle.setAttribute("aria-label", "메뉴 닫기");
            const focusTarget = closeBtn || focusableElements(sidebar)[0];
            focusTarget?.focus();
        } else {
            sidebar.removeAttribute("role");
            sidebar.removeAttribute("aria-modal");
            toggle.focus();
        }
    }

    function closeMobileNav() {
        setMobileNavOpen(false);
    }

    toggle.addEventListener("click", () => {
        setMobileNavOpen(!isOpen);
    });
    closeBtn?.addEventListener("click", closeMobileNav);
    backdrop.addEventListener("click", closeMobileNav);

    sidebar.querySelectorAll("a").forEach((link) => {
        link.addEventListener("click", () => {
            if (isMobileNav()) closeMobileNav();
        });
    });
    sidebar.querySelectorAll("form button[type='submit']").forEach((button) => {
        button.addEventListener("click", () => {
            if (isMobileNav()) closeMobileNav();
        });
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && isOpen) {
            event.preventDefault();
            closeMobileNav();
            return;
        }
        if (event.key !== "Tab" || !isOpen) {
            return;
        }

        const items = focusableElements(sidebar);
        if (items.length === 0) {
            return;
        }

        const first = items[0];
        const last = items[items.length - 1];
        if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first.focus();
        }
    });

    desktopMq.addEventListener("change", () => {
        if (desktopMq.matches) {
            unlockBodyScroll();
            closeMobileNav();
            sidebar.removeAttribute("inert");
            sidebar.removeAttribute("aria-hidden");
            sidebar.removeAttribute("role");
            sidebar.removeAttribute("aria-modal");
        } else {
            setSidebarInert(!isOpen);
        }
    });

    if (isMobileNav()) {
        setSidebarInert(true);
    }
})();
