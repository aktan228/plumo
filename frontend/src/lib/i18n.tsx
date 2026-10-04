"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

// Kyrgyz is reserved, but is not selectable until its translations are ready.
export type Locale = "ru" | "en" | "ky";
type ActiveLocale = Exclude<Locale, "ky">;
const ru = {
  home: "Plumo — главная", login: "Войти", register: "Создать аккаунт",
  loginTitle: "Вход", registerTitle: "Регистрация", resetTitle: "Сброс пароля",
  noAccount: "Ещё нет аккаунта?", hasAccount: "Уже есть аккаунт?",
  email: "Электронная почта", password: "Пароль", name: "Имя",
  namePlaceholder: "Как вас зовут", show: "Показать", hide: "Скрыть",
  forgot: "Забыли пароль?", resetAction: "Отправить ссылку",
  resetDescription: "Укажите почту вашего аккаунта, чтобы восстановить доступ.",
  backLogin: "Вернуться ко входу", backHome: "На главную",
  passwordHint: "Не менее 8 символов", language: "Язык сайта",
  unavailable: "Форма готова. Подключение авторизации в разработке: данные не отправлены, аккаунт не создан.",
  resetUnavailable: "Восстановление пароля ещё не подключено. Письмо не отправлено.",
  previewLabel: "PLUMO / ПЕРВЫЙ ЭКРАН", headline: "Каждый разговор.", headlineAccent: "С продолжением.",
  description: "Здесь появится история Plumo. Сейчас — первый элемент: ваш хедер.",
  scroll: "Прокрутите вниз, затем вверх", down: "Вниз — больше пространства.", up: "Вверх — навигация снова рядом.",
  skip: "К содержимому",
  footerTagline: "Каждый разговор имеет продолжение.", footerContact: "Свяжитесь с нами",
  footerAddress: "Токтоналиева 104/2", footerRights: "Все права защищены.",
  footerSocials: "Социальные сети", footerSoon: "Ссылка скоро появится", footerNewTab: "откроется в новой вкладке",
};
type Messages = { [Key in keyof typeof ru]: string };
const en: Messages = {
  home: "Plumo — home", login: "Sign in", register: "Create account",
  loginTitle: "Sign in", registerTitle: "Create account", resetTitle: "Reset password",
  noAccount: "Don't have an account?", hasAccount: "Already have an account?",
  email: "Email", password: "Password", name: "Name",
  namePlaceholder: "Your name", show: "Show", hide: "Hide",
  forgot: "Forgot password?", resetAction: "Send reset link",
  resetDescription: "Enter your account email to recover access.",
  backLogin: "Back to sign in", backHome: "Back to home",
  passwordHint: "At least 8 characters", language: "Website language",
  unavailable: "The form is ready. Authentication is still in development: no data was sent and no account was created.",
  resetUnavailable: "Password recovery is not connected yet. No email was sent.",
  previewLabel: "PLUMO / FIRST LOOK", headline: "Every conversation.", headlineAccent: "Continued.",
  description: "The Plumo story will appear here. For now, meet your header.",
  scroll: "Scroll down, then back up", down: "Scroll down for more space.", up: "Scroll up. Navigation is back.",
  skip: "Skip to content",
  footerTagline: "Every conversation has a next chapter.", footerContact: "Get in touch",
  footerAddress: "104/2 Toktonalieva Street", footerRights: "All rights reserved.",
  footerSocials: "Social media", footerSoon: "Link coming soon", footerNewTab: "opens in a new tab",
};
export const localeCatalog = {
  ru: { label: "Русский", available: true },
  en: { label: "English", available: true },
  ky: { label: "Кыргызча", available: false },
} as const;
const Context = createContext<{ locale: ActiveLocale; setLocale: (locale: ActiveLocale) => void; t: Messages } | null>(null);

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [locale, updateLocale] = useState<ActiveLocale>("ru");
  useEffect(() => {
    try {
      const saved = localStorage.getItem("plumo-language");
      if (saved === "ru" || saved === "en") updateLocale(saved);
    } catch { /* Storage can be unavailable in private browser contexts. */ }
  }, []);
  useEffect(() => { document.documentElement.lang = locale; }, [locale]);
  function setLocale(value: ActiveLocale) {
    updateLocale(value);
    try { localStorage.setItem("plumo-language", value); } catch { /* In-memory switching still works. */ }
  }
  return <Context.Provider value={{ locale, setLocale, t: locale === "en" ? en : ru }}>{children}</Context.Provider>;
}
export function useLanguage() {
  const value = useContext(Context);
  if (!value) throw new Error("LanguageProvider is required");
  return value;
}
export function LanguageSwitch() {
  const { locale, setLocale, t } = useLanguage();
  return <div className="language-switch" role="group" aria-label={t.language}>
    {(["ru", "en"] as const).map((value) => <button key={value} type="button" lang={value}
      aria-label={localeCatalog[value].label} aria-pressed={locale === value}
      onClick={() => setLocale(value)}>{value.toUpperCase()}</button>)}
  </div>;
}
