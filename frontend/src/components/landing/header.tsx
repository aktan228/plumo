"use client";

import Image from "next/image";
import Link from "next/link";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { LanguageSwitch, useLanguage } from "@/lib/i18n";

export function Header() {
  const { t, locale } = useLanguage();
  const [menuOpen, setMenuOpen] = useState(false);
  const [menuPresent, setMenuPresent] = useState(false);
  const shellRef = useRef<HTMLDivElement>(null);
  const burgerRef = useRef<HTMLButtonElement>(null);
  const pendingAnchor = useRef<string | null>(null);
  const [visible, setVisible] = useState(true);
  const [scrolled, setScrolled] = useState(false);
  const [focused, setFocused] = useState(false);
  const headerRef = useRef<HTMLElement>(null);
  const reducedMotion = useReducedMotion();

  useEffect(() => {
    let previous = Math.max(0, window.scrollY);
    let distance = 0;
    let direction = 0;
    let frame = 0;

    const update = () => {
      frame = 0;
      // Clamp Safari overscroll so the header does not flicker at page edges.
      const max = Math.max(0, document.documentElement.scrollHeight - window.innerHeight);
      const current = Math.min(max, Math.max(0, window.scrollY));
      const delta = current - previous;
      previous = current;
      setScrolled(current > 12);

      if (current <= 80) {
        setVisible(true);
        distance = 0;
        direction = 0;
        return;
      }
      if (Math.abs(delta) < 1) return;
      const nextDirection = delta > 0 ? 1 : -1;
      if (nextDirection !== direction) distance = 0;
      direction = nextDirection;
      distance += Math.abs(delta);
      // Ignore tiny wheel/trackpad movements before changing visibility.
      if (distance >= (direction > 0 ? 20 : 10)) {
        setVisible(direction < 0);
        distance = 0;
      }
    };
    const onScroll = () => {
      if (!frame) frame = window.requestAnimationFrame(update);
    };
    update();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      window.removeEventListener("scroll", onScroll);
      if (frame) window.cancelAnimationFrame(frame);
    };
  }, []);

  const links = locale === "en"
    ? [["product", "Product"], ["demo", "Live demo"], ["channels", "Channels"], ["statistics", "Statistics"], ["pilot", "Discuss a pilot"]]
    : [["product", "Продукт"], ["demo", "Демо"], ["channels", "Каналы"], ["statistics", "Статистика"], ["pilot", "Обсудить пилот"]];
  const closeMenu = () => setMenuOpen(false);

  useEffect(() => {
    if (!menuPresent) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const background = Array.from(document.querySelectorAll<HTMLElement>("main, .site-footer, .skip-link"));
    const previousInert = background.map((element) => element.inert);
    background.forEach((element) => { element.inert = true; });
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); setMenuOpen(false); }
      if (event.key !== "Tab") return;
      const elements = Array.from(shellRef.current?.querySelectorAll<HTMLElement>("a[href], button:not([disabled])") ?? []);
      const first = elements[0];
      const last = elements[elements.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      background.forEach((element, index) => { element.inert = previousInert[index]; });
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [menuPresent]);

  const shown = visible || focused || menuPresent;
  const menuLabel = locale === "en" ? "Navigation" : "Навигация";
  const easing = [0.76, 0, 0.24, 1] as const;

  return (
    <div ref={shellRef} role={menuPresent ? "dialog" : undefined} aria-modal={menuPresent ? true : undefined} aria-label={menuPresent ? menuLabel : undefined}>
    <motion.header
      ref={headerRef}
      className={`site-header${scrolled ? " is-scrolled" : ""}${menuPresent ? " menu-active" : ""}`}
      initial={false}
      animate={{ y: shown ? "0%" : "-110%" }}
      transition={reducedMotion ? { duration: 0 } : {
        duration: shown ? 0.38 : 0.26,
        ease: [0.22, 1, 0.36, 1],
      }}
      style={{ pointerEvents: shown ? "auto" : "none" }}
      onFocusCapture={() => setFocused(true)}
      onBlurCapture={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setFocused(false);
      }}
    >
      <div className="header-inner">
        <Link href="/" className="brand" aria-label={t.home} onClick={closeMenu}>
          <span className="brand-crop">
            <Image src="/images/plumo-logo.png" alt="" width={172} height={172} priority className="brand-image" />
          </span>
        </Link>
        <div className="header-actions">
        <Link href="/login" className="login-link" onClick={closeMenu}>
          {t.login}
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M5 12h14m-6-6 6 6-6 6" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </Link>
        <button ref={burgerRef} type="button" className={`menu-toggle${menuOpen ? " is-open" : ""}`} aria-expanded={menuOpen} aria-controls="plumo-menu" aria-label={locale === "en" ? (menuOpen ? "Close menu" : "Open menu") : (menuOpen ? "Закрыть меню" : "Открыть меню")} onClick={() => {
          if (menuPresent && !menuOpen) return;
          if (!menuOpen) setMenuPresent(true);
          setMenuOpen(!menuOpen);
        }}>
          <span /><span />
        </button>
        </div>
      </div>
    </motion.header>
    <AnimatePresence onExitComplete={() => {
      setMenuPresent(false);
      burgerRef.current?.focus({ preventScroll: true });
      const anchor = pendingAnchor.current;
      pendingAnchor.current = null;
      if (anchor) requestAnimationFrame(() => {
        const target = document.getElementById(anchor);
        target?.scrollIntoView({ behavior: reducedMotion ? "instant" : "smooth" });
        if (target) { target.setAttribute("tabindex", "-1"); target.focus({ preventScroll: true }); }
        window.history.replaceState(null, "", `#${anchor}`);
      });
    }}>
      {menuOpen && <motion.div id="plumo-menu" className="burger-panel" initial={{ y: reducedMotion ? 0 : "-100%", opacity: reducedMotion ? 0 : 1 }} animate={{ y: 0, opacity: 1 }} exit={{ y: reducedMotion ? 0 : "-100%", opacity: reducedMotion ? 0 : 1 }} transition={{ duration: reducedMotion ? 0 : 0.75, ease: easing }}>
        <div className="burger-content">
          <nav aria-label={menuLabel}>
            <ul>{links.map(([id, label], index) => <li key={id}>
              <motion.div initial={{ y: reducedMotion ? 0 : "115%", opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: reducedMotion ? 0 : "-90%", opacity: 0, transition: { duration: reducedMotion ? 0 : 0.45, delay: reducedMotion ? 0 : (links.length - index - 1) * 0.06, ease: easing } }} transition={{ duration: reducedMotion ? 0 : 0.72, delay: reducedMotion ? 0 : 0.2 + index * 0.09, ease: easing }}>
                <a href={`#${id}`} onClick={(event) => { event.preventDefault(); pendingAnchor.current = id; closeMenu(); }}>{label}<span className="menu-arrow" aria-hidden="true">↗</span></a>
              </motion.div>
            </li>)}</ul>
          </nav>
          <motion.div className="burger-bottom" initial={{ opacity: 0, y: reducedMotion ? 0 : 35 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: reducedMotion ? 0 : -24, transition: { duration: reducedMotion ? 0 : 0.25 } }} transition={{ duration: reducedMotion ? 0 : 0.55, delay: reducedMotion ? 0 : 0.22 + links.length * 0.09, ease: easing }}>
            <a href="mailto:contact@plumo.app">contact@plumo.app</a>
            <LanguageSwitch />
          </motion.div>
        </div>
      </motion.div>}
    </AnimatePresence>
    </div>
  );
}
