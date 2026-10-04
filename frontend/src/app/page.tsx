"use client";

import { Header } from "@/components/landing/header";
import { useLanguage } from "@/lib/i18n";

export default function Home() {
  const { t } = useLanguage();
  return (
    <>
      <a className="skip-link" href="#main">{t.skip}</a>
      <Header />
      <main id="main" className="header-preview">
        <section className="preview-intro">
          <p className="eyebrow"><span />{t.previewLabel}</p>
          <h1>{t.headline}<br /><span>{t.headlineAccent}</span></h1>
          <p className="preview-description">{t.description}</p>
          <div className="scroll-hint"><span>↓</span>{t.scroll}</div>
        </section>
        <section className="preview-space">
          <span className="preview-index">01 — 02</span>
          <p>{t.down}<br />{t.up}</p>
        </section>
      </main>
    </>
  );
}
