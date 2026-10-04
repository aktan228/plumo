"use client";

import { Header } from "@/components/landing/header";
import { Footer } from "@/components/landing/footer";
import { Landing } from "@/components/landing/landing";
import { useLanguage } from "@/lib/i18n";

export default function Home() {
  const { t } = useLanguage();
  return (
    <>
      <a className="skip-link" href="#main">{t.skip}</a>
      <Header />
      <Landing />
      <Footer />
    </>
  );
}
