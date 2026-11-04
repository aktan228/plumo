"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useLanguage } from "@/lib/i18n";
import { api } from "@/lib/api/client";
import type { WizardStorage } from "@/features/create-agent/use-wizard-storage";
import type { AgentDraft } from "@/features/create-agent/wizard-model";
import { publicationGaps, setupCanPublish } from "./setup-publication";
import { ScenarioHistory } from "./scenario-history";
import { validHandoffPhrases } from "./scenario-model";

type TextField = "company" | "description" | "audience" | "name" | "greeting" | "goal" | "fallback" | "handoffRules" | "qualificationPrompt" | "openingQuestion" | "handoffKeywords";
type Limits = { used_messages: number; daily_messages: number; session_messages: number; charged_usd: number; daily_budget_usd: number };
const fieldClass = "w-full rounded-lg border border-solid border-plumo-line bg-white px-3 py-2.5 font-[inherit] text-sm text-plumo-ink disabled:bg-plumo-line/20 focus:outline-2 focus:outline-plumo-blue";
const button = "inline-flex min-h-10 cursor-pointer items-center justify-center rounded-lg border border-solid border-plumo-line bg-white px-4 py-2 text-sm text-plumo-ink hover:bg-plumo-soft focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-plumo-blue disabled:cursor-default disabled:opacity-50";
const primary = `${button} border-plumo-blue bg-plumo-blue text-white hover:bg-plumo-blue/90`;
const bounds: Record<TextField, number> = { company: 200, description: 3000, audience: 2000, name: 60, greeting: 1000, goal: 1500, fallback: 1000, handoffRules: 1500, qualificationPrompt: 1500, openingQuestion: 300, handoffKeywords: 1000 };

export function AgentSettings({ active, storage, materialEditing, scenario = false }: { active: boolean; storage: WizardStorage; materialEditing: boolean; scenario?: boolean }) {
  const { locale } = useLanguage();
  const ru = locale === "ru";
  const draft = storage.snapshot.settings;
  const [confirm, setConfirm] = useState(false);
  const [limits, setLimits] = useState<Limits | null>(null);
  const [limitsError, setLimitsError] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const blocked = !storage.ready || storage.finishing || storage.status === "conflict" || storage.status === "expired";
  const gaps = publicationGaps(storage.snapshot);
  const labels: Record<TextField, string> = ru ? {
    qualificationPrompt: "Что выяснить у клиента", openingQuestion: "Первый уточняющий вопрос", handoffKeywords: "Фразы клиента для передачи человеку",
    company: "Название бизнеса", description: "Чем занимается бизнес", audience: "Для кого работает бизнес", name: "Имя агента", greeting: "Приветствие", goal: "Цель разговора", fallback: "Ответ при отсутствии подтверждённых данных", handoffRules: "Когда передавать человеку",
  } : {
    qualificationPrompt: "What to clarify", openingQuestion: "First qualifying question", handoffKeywords: "Customer phrases that require handoff",
    company: "Business name", description: "What the business does", audience: "Target audience", name: "Agent name", greeting: "Greeting", goal: "Conversation goal", fallback: "Reply when confirmed information is missing", handoffRules: "When to hand off to a person",
  };
  const c = ru ? {
    title: "Настройки бизнеса и агента", intro: "Изменения автоматически сохраняются в общий черновик. Ответы клиентам изменятся после публикации.", business: "Бизнес", agent: "Агент", behavior: "Поведение в диалоге", purpose: "Задача агента", sales: "Входящие продажи", support: "Поддержка", tone: "Тон общения", friendly: "Дружелюбный", formal: "Деловой", language: "Основной язык", languageHint: "Язык интерфейса выбирается отдельно. Агент также учитывает язык обращения клиента; качество каждого языка проверяется на материалах бизнеса.", save: "Сохранить черновик", saved: "Черновик сохранён", saving: "Сохраняем…", dirty: "Есть несохранённые изменения", live: "Текущий черновик опубликован", loading: "Загружаем настройки…", retry: "Повторить", publish: "Опубликовать", confirm: "Будут применены настройки агента и все материалы общего черновика, включая изменения в мастере и базе знаний. Сохранённые отключения материалов также вступят в силу. Ответы в каналах включаются отдельно.", confirmAction: "Применить настройки и материалы", cancel: "Отмена", conflict: "Настройки изменились в другой вкладке. Ваш черновик остаётся на экране. Скачайте его перед загрузкой актуальной версии и перенесите нужные изменения.", expired: "Сессия завершена. Скачайте черновик перед повторным входом.", failed: "Не удалось сохранить или опубликовать настройки. Ввод остаётся на экране. Повторите запрос.", download: "Скачать черновик", reload: "Загрузить актуальную версию", signin: "Войти", required: "Для публикации заполните", materials: "Добавьте хотя бы один материал в базу знаний.", pending: "В мастере остался незавершённый материал. Завершите или очистите этот ввод.", editing: "В базе знаний открыт редактор материала. Сначала сохраните материал в черновик или отмените редактирование.", wizard: "Открыть мастер", test: "Проверить ответы", channels: "Каналы и ответы агента", channelsText: "Подключение каналов, проверка и включение ответов доступны в интеграциях. Публикация настроек сама по себе агента не включает.", integrations: "Открыть интеграции", limits: "Лимиты", workingLimits: "Рабочие лимиты обращений и расходов согласует команда пилота. В этом разделе пока показаны только лимиты тестирования.", testLimits: "Лимиты тестирования", messages: "Сообщения за день", conversation: "Сообщений в одном тесте", cost: "Оценка расхода тестов за день", limitsFailed: "Не удалось загрузить лимиты тестирования.", after: "После публикации начните новый тест, чтобы проверить изменённую версию.",
  } : {
    title: "Business and agent settings", intro: "Changes are saved automatically to the shared draft. Customer replies change after publication.", business: "Business", agent: "Agent", behavior: "Conversation behavior", purpose: "Agent purpose", sales: "Inbound sales", support: "Support", tone: "Tone", friendly: "Friendly", formal: "Formal", language: "Primary language", languageHint: "Interface language is selected separately. The agent also considers the customer's language; check each language using your business materials.", save: "Save draft", saved: "Draft saved", saving: "Saving…", dirty: "Unsaved changes", live: "Current draft is published", loading: "Loading settings…", retry: "Retry", publish: "Publish", confirm: "Agent settings and all materials in the shared draft will be applied, including wizard and knowledge base changes. Saved material disabling will take effect as well. Channel replies are enabled separately.", confirmAction: "Apply settings and materials", cancel: "Cancel", conflict: "Another tab changed these settings. Your draft remains on screen. Download it before loading the current version, then reapply the changes you need.", expired: "Your session ended. Download the draft before signing in again.", failed: "Could not save or publish settings. Your input remains on screen. Retry the request.", download: "Download draft", reload: "Load current version", signin: "Sign in", required: "Complete these fields to publish", materials: "Add at least one material to the knowledge base.", pending: "There is unfinished material input in the wizard. Complete or clear it first.", editing: "A material editor is open in the knowledge base. Save that material to the draft or cancel editing first.", wizard: "Open wizard", test: "Test replies", channels: "Channels and agent replies", channelsText: "Connect channels, verify them and enable replies in Integrations. Publishing settings does not switch the agent on.", integrations: "Open integrations", limits: "Limits", workingLimits: "Agree live traffic and spending limits with the pilot team. This section currently shows test limits only.", testLimits: "Test limits", messages: "Messages today", conversation: "Messages per test conversation", cost: "Estimated test spending today", limitsFailed: "Could not load test limits.", after: "After publishing, start a new test to check the updated version.",
  };

  useEffect(() => {
    if (!active || scenario) return;
    const controller = new AbortController();
    void api<{ limits: Limits }>("testing/sessions", { signal: controller.signal }).then(data => { setLimits(data.limits); setLimitsError(false); }).catch(() => { if (!controller.signal.aborted) setLimitsError(true); });
    return () => controller.abort();
  }, [active, refresh, scenario]);
  useEffect(() => { setConfirm(false); }, [storage.snapshot]);

  function change<K extends keyof AgentDraft>(key: K, value: AgentDraft[K]) {
    storage.change(previous => ({ ...previous, settings: { ...previous.settings, [key]: value } }));
  }
  function textField(key: TextField, multiline = false) {
    return <label key={key} className="grid gap-2 text-sm"><span>{labels[key]}{["company", "description", "name", "greeting", "goal", "fallback"].includes(key) ? " *" : ""}</span>{multiline ? <textarea className={fieldClass} rows={3} value={draft[key]} maxLength={bounds[key]} disabled={blocked} onChange={event => change(key, event.target.value)} /> : <input className={fieldClass} value={draft[key]} maxLength={bounds[key]} disabled={blocked} onChange={event => change(key, event.target.value)} />}</label>;
  }
  function download() {
    const url = URL.createObjectURL(new Blob([JSON.stringify(storage.snapshot, null, 2)], { type: "application/json" }));
    const anchor = document.createElement("a"); anchor.href = url; anchor.download = "plumo-settings-draft.json"; anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  const failed = ["error", "conflict", "expired"].includes(storage.status);
  const status = storage.status === "saving" ? c.saving : storage.status === "dirty" ? c.dirty : storage.completed ? c.live : c.saved;
  const validPhrases = validHandoffPhrases(draft.handoffKeywords);
  const canPublish = !blocked && !materialEditing && !storage.completed && validPhrases && setupCanPublish(storage.snapshot);

  return <section className="h-full overflow-y-auto p-4 md:p-6"><div className="mx-auto max-w-[1100px]">
    <h2 className="m-0 text-2xl font-semibold">{scenario ? (ru ? "Сценарий агента" : "Agent scenario") : c.title}</h2>
    <p className="mb-4 mt-2 text-sm leading-6 text-plumo-muted">{c.intro}</p>
    {!validPhrases && <p role="alert" className="rounded-lg bg-plumo-soft p-3 text-sm">{ru ? "Фразы передачи: не более 10 непустых строк, каждая по 2–100 символов и с буквами или цифрами. Исправьте поле в сценарии для сохранения и публикации." : "Handoff phrases: at most 10 nonempty lines, each 2–100 characters and containing letters or digits. Correct the scenario field to save and publish."}</p>}
    <div className="mb-5 flex flex-wrap items-center gap-3"><span role="status" className="text-xs text-plumo-muted">{failed ? c.failed : storage.ready ? status : c.loading}</span><button type="button" className={button} disabled={blocked} onClick={() => void storage.flush()}>{c.save}</button><button type="button" className={primary} disabled={!canPublish} onClick={() => setConfirm(true)}>{c.publish}</button><a href="#testing" className="text-sm text-plumo-blue underline">{c.test}</a></div>
    {failed && <div role="alert" className="mb-5 rounded-xl border border-solid border-plumo-line bg-plumo-soft p-4 text-sm leading-6"><p className="m-0">{storage.status === "conflict" ? c.conflict : storage.status === "expired" ? c.expired : c.failed}</p><div className="mt-3 flex flex-wrap gap-2"><button type="button" className={button} onClick={download}>{c.download}</button>{storage.status === "conflict" ? <button type="button" className={button} disabled={materialEditing} onClick={() => void storage.reload()}>{c.reload}</button> : storage.status === "expired" ? <Link href="/login?next=/dashboard%23settings" className={button}>{c.signin}</Link> : <button type="button" className={button} onClick={() => { if (storage.ready) void storage.flush(); else void storage.reload(); }}>{c.retry}</button>}</div></div>}
    {storage.ready && !setupCanPublish(storage.snapshot) && <div className="mb-5 rounded-xl border border-solid border-plumo-line bg-white p-4 text-sm leading-6">{gaps.fields.length > 0 && <p className="m-0">{c.required}: {gaps.fields.map(key => labels[key]).join(", ")}.</p>}{gaps.materials && <p className="mb-0 mt-2"><a href="#knowledge" className="text-plumo-blue underline">{c.materials}</a></p>}{gaps.pendingSource && <p className="mb-0 mt-2">{c.pending} <Link href="/create/wizard" className="text-plumo-blue underline">{c.wizard}</Link></p>}</div>}
    {materialEditing && <p className="mb-5 rounded-xl bg-plumo-soft p-4 text-sm leading-6"><a href="#knowledge" className="text-plumo-blue underline">{c.editing}</a></p>}
    {confirm && <div role="group" aria-label={c.publish} className="mb-5 rounded-xl border border-solid border-plumo-blue/30 bg-plumo-soft p-4 text-sm leading-6"><p className="m-0">{c.confirm}</p><div className="mt-3 flex flex-wrap gap-2"><button type="button" className={primary} disabled={!canPublish} onClick={() => void storage.complete()}>{storage.finishing ? c.saving : c.confirmAction}</button><button type="button" className={button} disabled={storage.finishing} onClick={() => setConfirm(false)}>{c.cancel}</button></div></div>}
    <div className="grid items-start gap-5 lg:grid-cols-2">
      {scenario ? <>
        <section className="grid gap-4 rounded-2xl border border-solid border-plumo-line bg-white p-5 lg:col-span-2">
          <h3 className="m-0 text-base font-semibold">{ru ? "Задача и ход разговора" : "Task and conversation flow"}</h3>
          <label className="grid gap-2 text-sm">{c.purpose}<select className={fieldClass} value={draft.purpose} disabled={blocked} onChange={event => change("purpose", event.target.value as AgentDraft["purpose"])}><option value="sales">{c.sales}</option><option value="support">{c.support}</option></select></label>
          {textField("goal", true)}{textField("qualificationPrompt", true)}{textField("greeting", true)}{textField("openingQuestion", true)}
          <p className="m-0 text-sm leading-6 text-plumo-muted">{ru ? "Например: выяснить цель покупки, район и бюджет. Модель получает эти указания и должна задавать по одному вопросу с учётом истории. Первый вопрос сервер добавляет только к первому приветствию и /start; уберите другой вопрос из приветствия. Проверяйте дополнительные уточнения в тестировании с рабочей моделью." : "Example: clarify the purchase purpose, location and budget. The model receives these instructions and should ask one relevant question at a time. The server appends the opening question only to the first greeting or /start; remove any other question from the greeting. Check further clarification using the configured model."}</p>
          {textField("handoffRules", true)}{textField("handoffKeywords", true)}
          <p className="m-0 text-sm leading-6 text-plumo-muted">{ru ? "Условия выше получает модель. Фразы сервер проверяет буквально, без учёта регистра и пунктуации: до 10 строк, по 2–100 символов. Например: «хочу возврат» или «срочная жалоба». Совпадение целой фразы создаёт передачу; обязательные правила безопасности и просьба о человеке действуют всегда." : "The model receives the conditions above. The server checks literal whole phrases regardless of case or punctuation: up to 10 lines, 2–100 characters each. For example: “request refund”. A match creates a handoff; mandatory safety rules and requests for a person always apply."}</p>
          {textField("fallback", true)}
          <p className="m-0 text-sm leading-6 text-plumo-muted">{ru ? "Если подтверждённых фактов недостаточно, агент использует этот ответ и передаёт вопрос сотруднику. Сценарий не разрешает выдумывать факты или подтверждать встречу без записи. Голосовой сценарий здесь не настраивается." : "If confirmed facts are missing, the agent uses this reply and hands the question to a person. Scenarios cannot authorize invented facts or unreserved appointments. These controls do not configure voice."}</p>
          <a href="#testing" className="text-sm text-plumo-blue underline">{c.test}</a>
        </section>
        <div className="lg:col-span-2"><ScenarioHistory active={active} published={storage.completed} ru={ru} /></div>
      </> : <>
      <section className="grid gap-4 rounded-2xl border border-solid border-plumo-line bg-white p-5"><h3 className="m-0 text-base font-semibold">{c.business}</h3>{textField("company")}{textField("description", true)}{textField("audience", true)}<label className="grid gap-2 text-sm">{c.purpose}<select className={fieldClass} value={draft.purpose} disabled={blocked} onChange={event => change("purpose", event.target.value as AgentDraft["purpose"])}><option value="sales">{c.sales}</option><option value="support">{c.support}</option></select></label></section>
      <section className="grid gap-4 rounded-2xl border border-solid border-plumo-line bg-white p-5"><h3 className="m-0 text-base font-semibold">{c.agent}</h3>{textField("name")}<label className="grid gap-2 text-sm">{c.tone}<select className={fieldClass} value={draft.tone} disabled={blocked} onChange={event => change("tone", event.target.value as AgentDraft["tone"])}><option value="friendly">{c.friendly}</option><option value="formal">{c.formal}</option></select></label><label className="grid gap-2 text-sm">{c.language}<select className={fieldClass} value={draft.language} disabled={blocked} onChange={event => change("language", event.target.value as AgentDraft["language"])}><option value="ru">Русский</option><option value="en">English</option></select></label><p className="m-0 text-sm leading-6 text-plumo-muted">{c.languageHint}</p></section>
      <section className="grid gap-4 rounded-2xl border border-solid border-plumo-line bg-white p-5 lg:col-span-2"><h3 className="m-0 text-base font-semibold">{c.behavior}</h3>{textField("greeting", true)}{textField("goal", true)}{textField("fallback", true)}{textField("handoffRules", true)}<p className="m-0 text-sm leading-6 text-plumo-muted">{c.after}</p></section>
      <section className="rounded-2xl border border-solid border-plumo-line bg-white p-5"><h3 className="m-0 text-base font-semibold">{c.channels}</h3><p className="mb-4 mt-3 text-sm leading-6 text-plumo-muted">{c.channelsText}</p><a href="#integrations" className={button}>{c.integrations}</a></section>
      <section className="rounded-2xl border border-solid border-plumo-line bg-white p-5"><h3 className="m-0 text-base font-semibold">{c.limits}</h3><p className="mb-4 mt-3 text-sm leading-6 text-plumo-muted">{c.workingLimits}</p><h4 className="m-0 text-sm font-semibold">{c.testLimits}</h4>{limitsError ? <p role="alert" className="text-sm">{c.limitsFailed} <button type="button" className={button} onClick={() => setRefresh(value => value + 1)}>{c.retry}</button></p> : limits ? <dl className="mb-0 mt-3 grid gap-3 text-sm"><div><dt className="text-plumo-muted">{c.messages}</dt><dd className="m-0 mt-1">{limits.used_messages} / {limits.daily_messages}</dd></div><div><dt className="text-plumo-muted">{c.conversation}</dt><dd className="m-0 mt-1">{limits.session_messages}</dd></div><div><dt className="text-plumo-muted">{c.cost}</dt><dd className="m-0 mt-1">${limits.charged_usd.toFixed(2)} / ${limits.daily_budget_usd.toFixed(2)}</dd></div></dl> : <p className="text-sm text-plumo-muted">{c.loading}</p>}</section>
      </>}
    </div>
  </div></section>;
}
