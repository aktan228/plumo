"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

// Kyrgyz is reserved, but is not selectable until its translations are ready.
export type Locale = "ru" | "en" | "ky";
type ActiveLocale = Exclude<Locale, "ky">;
const ru = {
  home: "Plumo — главная", login: "Войти", register: "Создать аккаунт",
  loginTitle: "Вход", registerTitle: "Регистрация", resetTitle: "Сброс пароля",
  loginDescription: "Войдите в свой аккаунт Plumo", registerDescription: "Создайте свой аккаунт Plumo",
  emailPlaceholder: "Введите вашу почту", passwordPlaceholder: "Ваш пароль",
  recover: "Восстановить", or: "или", googleLogin: "Войти через Google",
  googleUnavailable: "Вход через Google ещё не подключён. Данные не отправлены.",
  noAccount: "Ещё нет аккаунта?", hasAccount: "Уже есть аккаунт?",
  email: "Почта", password: "Пароль", name: "Имя",
  namePlaceholder: "Как вас зовут", show: "Показать", hide: "Скрыть",
  forgot: "Забыли пароль?", resetAction: "Отправить ссылку",
  resetDescription: "Укажите почту вашего аккаунта, чтобы восстановить доступ.",
  backLogin: "Вернуться ко входу", backHome: "На главную",
  passwordHint: "От 10 до 128 символов", language: "Язык сайта",
  unavailable: "Не удалось создать аккаунт. Повторите попытку.",
  resetUnavailable: "Пароль меняет администратор команды Plumo. Письмо не отправлено.",
  verifyTitle: "Подтвердите почту", verifyDescription: "Подтвердите почту, чтобы открыть свой кабинет Plumo.",
  verifyResendDescription: "Укажите почту, чтобы получить новую ссылку подтверждения.", verifyAction: "Подтвердить почту",
  verifyRequired: "Сначала подтвердите почту аккаунта:", verifySent: "Аккаунт создан. Откройте письмо и подтвердите почту:",
  mailDeliveryFailed: "Аккаунт создан, но письмо отправить не удалось. Повторите отправку через минуту:",
  emailRequestAccepted: "Если для этой почты доступно это действие, проверьте входящие и спам. Письмо не пришло? Попробуйте ещё раз через минуту.",
  resendEmail: "Отправить письмо ещё раз", sendingEmail: "Отправляем…", useAnotherEmail: "Указать другую почту",
  newPasswordTitle: "Новый пароль", newPasswordDescription: "Задайте новый пароль для вашего аккаунта.", newPassword: "Новый пароль",
  confirmPassword: "Повторите пароль", passwordMismatch: "Пароли не совпадают.", savePassword: "Сохранить пароль", savingPassword: "Сохраняем…",
  passwordChanged: "Пароль изменён. Старые сессии завершены. Войдите с новым паролем.",
  linkInvalid: "Ссылка недействительна, истекла или уже использована. Запросите новую.", requestNewLink: "Получить новую ссылку",
  accountLimited: "Слишком много попыток. Попробуйте позже.", mailNotConfigured: "Отправка писем пока не настроена. Попробуйте позже.",
  registering: "Создаём аккаунт…", registerConflict: "Не удалось создать аккаунт. Попробуйте войти или укажите другую почту.",
  registerInvalid: "Проверьте имя, почту и пароль.", registerName: "Укажите имя от 1 до 100 символов.",
  registerEmail: "Укажите корректную почту.", registerPassword: "Пароль должен содержать от 10 до 128 символов и не состоять только из пробелов.",
  registerLimited: "Слишком много попыток регистрации. Попробуйте через час.",
  signingIn: "Входим…", loginWrong: "Неверная почта или пароль.",
  loginLocked: "Слишком много попыток. Подождите 15 минут.", loginOffline: "Сервер недоступен. Повторите через минуту.",
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
  loginDescription: "Sign in to your Plumo account", registerDescription: "Create your Plumo account",
  emailPlaceholder: "Enter your email", passwordPlaceholder: "Your password",
  recover: "Reset it", or: "or", googleLogin: "Sign in with Google",
  googleUnavailable: "Google sign-in is not connected yet. No data was sent.",
  noAccount: "Don't have an account?", hasAccount: "Already have an account?",
  email: "Email", password: "Password", name: "Name",
  namePlaceholder: "Your name", show: "Show", hide: "Hide",
  forgot: "Forgot password?", resetAction: "Send reset link",
  resetDescription: "Enter your account email to recover access.",
  backLogin: "Back to sign in", backHome: "Back to home",
  passwordHint: "10 to 128 characters", language: "Website language",
  unavailable: "Could not create your account. Please try again.",
  resetUnavailable: "A Plumo team administrator resets passwords. No email was sent.",
  verifyTitle: "Verify your email", verifyDescription: "Confirm your email to open your Plumo workspace.",
  verifyResendDescription: "Enter your email to request a new verification link.", verifyAction: "Verify email",
  verifyRequired: "First verify the email for your account:", verifySent: "Account created. Open the verification email sent to:",
  mailDeliveryFailed: "Account created, but the email could not be sent. Try sending again in a minute:",
  emailRequestAccepted: "If this action is available for that email, check your inbox and spam. No email? Try again in a minute.",
  resendEmail: "Send email again", sendingEmail: "Sending…", useAnotherEmail: "Use another email",
  newPasswordTitle: "New password", newPasswordDescription: "Choose a new password for your account.", newPassword: "New password",
  confirmPassword: "Repeat password", passwordMismatch: "Passwords do not match.", savePassword: "Save password", savingPassword: "Saving…",
  passwordChanged: "Password changed. Old sessions have ended. Sign in with your new password.",
  linkInvalid: "This link is invalid, expired or already used. Request a new link.", requestNewLink: "Request a new link",
  accountLimited: "Too many attempts. Try again later.", mailNotConfigured: "Email delivery is not configured yet. Try again later.",
  registering: "Creating account…", registerConflict: "Could not create an account. Try signing in or use another email.",
  registerInvalid: "Check your name, email and password.", registerName: "Enter a name between 1 and 100 characters.",
  registerEmail: "Enter a valid email.", registerPassword: "Use 10 to 128 characters; the password cannot consist only of spaces.",
  registerLimited: "Too many registration attempts. Please try again in an hour.",
  signingIn: "Signing in…", loginWrong: "Wrong email or password.",
  loginLocked: "Too many attempts. Wait 15 minutes.", loginOffline: "The server is unavailable. Retry in a minute.",
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
    <button type="button" lang="ky" disabled aria-pressed={false}
      aria-label={locale === "en" ? "Кыргызча — translation coming soon" : "Кыргызча — перевод готовится"}
      title={locale === "en" ? "Kyrgyz translation coming soon" : "Кыргызский перевод готовится"}>KY</button>
  </div>;
}
