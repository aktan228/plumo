"use client";

import Image from "next/image";
import Link from "next/link";
import { useLanguage } from "@/lib/i18n";

// Set official profile URLs once the company accounts are confirmed.
const socials = [
  { name: "Instagram", href: process.env.NEXT_PUBLIC_INSTAGRAM_URL || "https://www.instagram.com/plumo.ai/", path: "M7 2h10a5 5 0 0 1 5 5v10a5 5 0 0 1-5 5H7a5 5 0 0 1-5-5V7a5 5 0 0 1 5-5Zm5 5a5 5 0 1 0 0 10 5 5 0 0 0 0-10Zm6-2h.01", stroke: true },
  { name: "X", href: process.env.NEXT_PUBLIC_X_URL, path: "M18.9 2H22l-6.8 7.8L23.2 22h-6.3L12 14.6 5.5 22H2.3l8.2-9.4L.8 2h6.5l4.5 6.8L18.9 2Zm-1.1 18h1.7L6.3 4H4.5l13.3 16Z", stroke: false },
  { name: "LinkedIn", href: process.env.NEXT_PUBLIC_LINKEDIN_URL, path: "M5 3a2 2 0 1 0 0 4 2 2 0 0 0 0-4ZM3 9h4v12H3V9Zm6 0h4v1.7c.7-1.2 1.8-2 3.5-2 3.2 0 4.5 2 4.5 5.3v7h-4v-6.2c0-1.7-.3-2.8-1.8-2.8-1.6 0-2.2 1.2-2.2 2.8V21H9V9Z", stroke: false },
];

export function Footer() {
  const { t } = useLanguage();
  return <footer className="site-footer">
    <div className="footer-inner">
      <div className="footer-main">
        <div className="footer-brand-block">
          <Link href="/" className="brand" aria-label={t.home}><span className="brand-crop"><Image src="/images/plumo-logo.png" alt="" width={172} height={172} className="brand-image" /></span></Link>
          <p className="footer-tagline">{t.footerTagline}</p>
        </div>
        <div className="footer-contact-block">
          <h2>{t.footerContact}</h2>
          <address>
            <a className="footer-email" href="mailto:contact@plumo.app">contact@plumo.app <span aria-hidden="true">↗</span></a>
            <a className="footer-phone" href="tel:+996555144667">+996 555 144 667</a>
            <p className="footer-address">{t.footerAddress}</p>
          </address>
        </div>
      </div>
      <div className="footer-bottom">
        <p>© {new Date().getFullYear()} Plumo. {t.footerRights}</p>
        <div className="footer-socials" role="group" aria-label={t.footerSocials}>
          {socials.map(({ name, href, path, stroke }) => {
            const icon = <svg viewBox="0 0 24 24" width="20" height="20" fill={stroke ? "none" : "currentColor"} stroke={stroke ? "currentColor" : undefined} strokeWidth={stroke ? 1.7 : undefined} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={path} /></svg>;
            // Only accept external HTTPS URLs. No invented company profiles.
            const valid = href?.startsWith("https://");
            return valid ? <a key={name} href={href} target="_blank" rel="noopener noreferrer" aria-label={`${name} — ${t.footerNewTab}`} className="social-icon">{icon}</a>
              : <span key={name} className="social-icon social-unconfigured" role="img" aria-label={`${name}: ${t.footerSoon}`} title={`${name}: ${t.footerSoon}`}>{icon}</span>;
          })}
        </div>
      </div>
    </div>
  </footer>;
}
