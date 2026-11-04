"use client";

import Link from "next/link";
import { useLanguage } from "@/lib/i18n";
import { plannedSections } from "./navigation";

const linkClass = "inline-flex min-h-10 items-center rounded-lg border border-solid border-plumo-line bg-white px-4 py-2 text-sm text-plumo-blue hover:bg-plumo-soft focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-plumo-blue";

export function DashboardHelp() {
  const { locale } = useLanguage();
  const ru = locale === "ru";
  const steps = ru ? [
    { title: "1. Подготовьте материалы", text: "Добавьте текст, вопросы и ответы или файлы TXT/MD. Завершите настройку, чтобы опубликовать материалы и применить настройки агента. Ссылки на сайты пока не загружают их содержимое.", href: "#knowledge", action: "Открыть базу знаний" },
    { title: "2. Проверьте ответы", text: "Задайте агенту вопросы по вашим материалам. Проверьте цены, условия и передачу человеку. Если показан mock, используется демонстрационная модель. Один успешный ответ ещё не подтверждает качество всех ответов.", href: "#testing", action: "Открыть тест" },
    { title: "3. Подключите Telegram", text: "Подключите бота бизнеса, пройдите контрольную проверку и отдельно включите ответы агента. Затем напишите боту с другого аккаунта.", href: "#integrations", action: "Открыть интеграции" },
    { title: "4. Обработайте обращение", text: "Откройте диалог, нажмите «Взять диалог» и ответьте клиенту. Когда будете готовы, верните диалог агенту. При неизвестном результате отправки сначала проверьте сообщение в канале.", href: "#chats", action: "Открыть диалоги" },
  ] : [
    { title: "1. Prepare your materials", text: "Add text, Q&A or TXT/MD files. Complete setup to publish materials and apply agent settings. Website links do not yet import their content.", href: "#knowledge", action: "Open knowledge base" },
    { title: "2. Test the replies", text: "Ask questions about your materials. Check prices, terms and handoff. A mock label means a demo model is in use. One successful reply does not confirm overall answer quality.", href: "#testing", action: "Open test" },
    { title: "3. Connect Telegram", text: "Connect your business bot, complete verification and switch on agent replies separately. Then message the bot from another account.", href: "#integrations", action: "Open integrations" },
    { title: "4. Handle an enquiry", text: "Open a conversation, select Take conversation and reply to the customer. Return it to the agent when ready. If delivery is unknown, check the message in the channel before retrying.", href: "#chats", action: "Open conversations" },
  ];

  return <section className="min-h-0 flex-1 overflow-y-auto p-4 md:p-6">
    <div className="mx-auto max-w-[1000px]">
      <h2 className="m-0 text-2xl font-semibold">{ru ? "Как начать работу" : "Getting started"}</h2>
      <p className="mb-6 mt-2 text-sm leading-6 text-plumo-muted">{ru ? "Рабочий путь сопровождаемого пилота: материалы → тест → Telegram → диалог с клиентом." : "The supported pilot flow: materials → test → Telegram → customer conversation."}</p>
      <div className="grid gap-4 lg:grid-cols-2">{steps.map(step => <article key={step.href} className="flex flex-col items-start rounded-2xl border border-solid border-plumo-line bg-white p-5">
        <h3 className="m-0 text-base font-semibold">{step.title}</h3>
        <p className="mb-5 mt-3 flex-1 text-sm leading-6 text-plumo-muted">{step.text}</p>
        {step.href.startsWith("#") ? <a href={step.href} className={linkClass}>{step.action}</a> : <Link href={step.href} className={linkClass}>{step.action}</Link>}
      </article>)}</div>
      <div className="mt-6 rounded-2xl border border-solid border-plumo-line bg-white p-5">
        <h3 className="m-0 text-base font-semibold">{ru ? "Условия пилота и поддержка" : "Pilot terms and support"}</h3>
        <p className="mb-0 mt-3 text-sm leading-6 text-plumo-muted">{ru ? "Участие, лимиты, время реакции менеджера и способ связи с поддержкой согласуйте с сотрудником Plumo, который организует ваш пилот. Автоматическая покупка подписки в кабинете пока недоступна." : "Agree participation, limits, manager response hours and your support contact with the Plumo team member arranging your pilot. Automatic subscription purchase is not available in the dashboard yet."}</p>
      </div>
      <div className="mt-6 rounded-2xl border border-solid border-plumo-line bg-plumo-soft/40 p-5">
        <h3 className="m-0 text-base font-semibold">{ru ? "Следующие этапы кабинета" : "Upcoming dashboard features"}</h3>
        <p className="mb-0 mt-2 text-sm leading-6 text-plumo-muted">{ru ? "Эти функции ещё не доступны. Список описывает план развития без обещания даты запуска." : "These features are not available yet. This roadmap does not promise a release date."}</p>
        <ul className="mb-0 mt-3 space-y-2 pl-5 text-sm text-plumo-muted">{plannedSections.map(item => <li key={item.en}>{item[locale]}</li>)}</ul>
      </div>
    </div>
  </section>;
}
