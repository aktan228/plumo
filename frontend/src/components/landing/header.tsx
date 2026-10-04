"use client";

import Image from "next/image";
import Link from "next/link";
import { motion, useReducedMotion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { LanguageSwitch, useLanguage } from "@/lib/i18n";

export function Header() {
  const { t } = useLanguage();
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

  const shown = visible || focused;

  return (
    <motion.header
      ref={headerRef}
      className={`site-header${scrolled ? " is-scrolled" : ""}`}
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
        <Link href="/" className="brand" aria-label={t.home}>
          <span className="brand-crop">
            <Image src="/images/plumo-logo.png" alt="" width={172} height={172} priority className="brand-image" />
          </span>
        </Link>
        <div className="header-actions">
        <LanguageSwitch />
        <Link href="/login" className="login-link">
          {t.login}
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M5 12h14m-6-6 6 6-6 6" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </Link>
        </div>
      </div>
    </motion.header>
  );
}
