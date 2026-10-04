import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";
import { LanguageProvider } from "@/lib/i18n";

export const metadata: Metadata = {
  title: "Plumo — каждый разговор имеет продолжение",
  description: "ИИ-ассистент для входящих обращений бизнеса.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return <html lang="ru"><body><LanguageProvider>{children}</LanguageProvider></body></html>;
}
