"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { useLanguage } from "@/lib/i18n";
import "./landing.css";
import { Hero } from "./hero";
import { CustomerSituations } from "./customer-situations";
import { VoiceCallDemo } from "./voice-call-demo";
import { DialogueToLead } from "./dialogue-to-lead";
import { SetupPipeline } from "./setup-pipeline";
import { Statistics } from "./statistics";
import { PilotCTA } from "./pilot-cta";
import { FAQ } from "./faq";
import { Pricing, pricingRequestLabel, type PricingRequest } from "./pricing";
import { DemoChoice } from "./demo-choice";
import { DemoContactForm } from "./demo-contact-form";

const copy = {
  ru: {
    label: "ДЛЯ РАЗГОВОРОВ, КОТОРЫЕ ВАЖНЫ", title: "Ваш клиент уже", title2: "начал разговор.", title3: "Plumo продолжит.",
    intro: "ИИ-ассистент для входящих обращений. От первого вопроса до готовой заявки — с вниманием к клиенту и контекстом для вашей команды.",
    try: "Посмотреть демо", pilot: "Обсудить пилот", note: "Знакомьтесь с продуктом · Без регистрации", sample: "Демонстрационный сценарий",
    person: "Айбек", incoming: "Новое обращение", question: "Ищу квартиру для семьи. Есть варианты?", answer: "Давайте подберём. Какой район и сколько комнат рассматриваете?",
    lead: "Заявка для менеджера", need: "Квартира для семьи", rooms: "2 комнаты · южная часть города", context: "Потребность и история — в одной карточке", next: "Следующий шаг", nextValue: "Согласовать просмотр", strip: ["Внимание к каждому запросу", "Контекст между разговорами", "Человек всегда рядом"],
    demoLabel: "01 / ПОПРОБУЙТЕ САМИ", demoTitle: "Хороший разговор\nначинается с внимания.", demoDesc: "Пройдите короткий пример подбора квартиры. Выберите вопрос и посмотрите, как обращение становится заявкой.", demoNotice: "Интерактивный пример с готовыми ответами и вымышленными объектами. Это не подключённый ИИ.",
    chatTitle: "Plumo · агентство недвижимости", chatStatus: "Демо-режим", welcome: "Здравствуйте! Помогу с вопросами о квартире и передам ваш запрос менеджеру. Что вас интересует?",
    prompts: ["Какие квартиры есть?", "Можно записаться на просмотр?", "Хочу поговорить с человеком"],
    replies: ["В нашем вымышленном каталоге — двухкомнатная квартира 64 м² в южной части города. Какой метраж вы рассматриваете?", "Да, в этом примере можно оставить пожелание на субботу. Менеджер должен проверить расписание и подтвердить время — запись пока не создана.", "В реальном подключении менеджер получит историю и ваш запрос. В этом демо уведомление не отправляется."],
    reset: "Начать заново", choose: "Выберите вопрос ниже", memoryLabel: "02 / КОНТЕКСТ", memoryTitle: "Начинайте с того,\nна чём остановились.", memoryDesc: "Покупателю не хочется рассказывать всё заново. Plumo задуман так, чтобы потребность, детали и следующий шаг оставались с клиентом.", memoryPoints: ["Краткое резюме вместо поиска по переписке", "Факты из базы знаний вашего бизнеса", "Передача человеку вместе с историей"], memoryNote: "Объединение чатов и звонков — следующий этап продукта.", memoryCard: "КАРТОЧКА КЛИЕНТА", memorySummary: "Интересуется двухкомнатной квартирой. Предпочитает южную часть города. Хочет обсудить просмотр в субботу.", source: "Из демонстрационного диалога", human: "Передать менеджеру", humanNote: "Пример карточки — передача не выполняется",
    processLabel: "03 / КАК РАБОТАЕТ", processTitle: "Ваш бизнес.\nВаши правила общения.", steps: [ ["Знакомимся", "Определяем один сценарий и то, что должно стать результатом разговора."], ["Добавляем знания", "Собираем услуги, цены и ответы. Вы проверяете, что всё верно."], ["Проверяем вместе", "Прогоняем реальные вопросы и настраиваем передачу вашей команде."], ["Запускаем пилот", "Подключаем согласованный канал и разбираем результаты обращений."] ],
    channelLabel: "04 / КАНАЛЫ", channelTitle: "Там, где начинается\nваш следующий разговор.", channelDesc: "Начинаем с одного канала. Остальные подключаем по результатам пилота и технической проверки.", channels: [["↗", "Веб-чат", "Демо на этой странице"], ["↗", "WhatsApp", "Планируется"], ["◎", "Instagram", "Планируется"], ["➤", "Telegram", "Планируется"], ["↗", "Телефония", "Техническая проверка впереди"]],
    statsLabel: "05 / РЕЗУЛЬТАТ В ЦИФРАХ", statsTitle: "Видно не только разговор.\nВиден следующий шаг.", statsDesc: "Обращения, заявки и передачи менеджеру — показатели, по которым будем оценивать пилот.", statsBadge: "Пример данных · не результаты клиентов", statsPeriod: "Обращения за неделю", statsUnits: "обращений", days: ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"], metrics: ["Обращений", "Заявок на встречу", "Передано человеку"],
    faqLabel: "06 / ВОПРОСЫ", faqTitle: "Давайте проясним.", faqs: [["Plumo заменит моего менеджера?", "Задача Plumo — обработать первичный запрос и собрать контекст. Сложные вопросы, переговоры и завершение сделки остаются у вашей команды."], ["Откуда агент знает цены и условия?", "Из утверждённых данных вашего бизнеса. Если нужной информации нет, сценарий должен предусматривать уточнение у менеджера."], ["Какие языки предусмотрены?", "Продукт ориентирован на русский и кыргызский, включая смешанную речь. Качество агента проверяется отдельно перед пилотом. Интерфейс сайта сейчас доступен на русском и английском; кыргызская версия будет добавлена позже."], ["Можно подключить существующий номер?", "Это проверяется с вашим оператором и провайдером телефонии. До технического теста мы не обещаем подключение любого номера."], ["Демо действительно создаёт заявку на просмотр?", "Нет. На этой странице показан сценарий с вымышленными данными. Демо не отправляет уведомления менеджеру и не резервирует время."], ["Как попасть в пилот?", "Расскажите о бизнесе через форму ниже. Мы обсудим канал, задачу, условия и критерии результата до запуска."]],
    ctaLabel: "НАЧНЁМ С ВАШЕГО БИЗНЕСА", ctaTitle: "Дадим следующему\nразговору продолжение.", ctaDesc: "Расскажите, какие обращения приходят вашей команде. Вместе выберем сценарий для первого пилота.", name: "Ваше имя", business: "Компания", email: "Электронная почта", message: "Что хотите автоматизировать?", send: "Подготовить письмо", mailNote: "Откроется ваша почта с заполненным письмом. Отправку подтверждаете вы.", mailReady: "Почтовая программа запрошена. Если она не открылась, напишите на contact@plumo.app. Заявка через сайт не отправлялась.", subject: "Заявка на пилот Plumo",
  },
  en: {
    label: "FOR CONVERSATIONS THAT MATTER", title: "Your customer", title2: "started a conversation.", title3: "Plumo takes it further.", intro: "An AI assistant for inbound inquiries. From the first question to a qualified request, with care for your customer and context for your team.", try: "Explore the demo", pilot: "Discuss a pilot", note: "Meet the product · No sign-up needed", sample: "Illustrative scenario", person: "Aibek", incoming: "New inquiry", question: "Looking for an apartment for my family. Any options?", answer: "Let's find a fit. Which area and how many rooms are you looking for?", lead: "Request for the manager", need: "Family apartment", rooms: "2 rooms · south of the city", context: "Needs and history, in one place", next: "Next step", nextValue: "Arrange a viewing", strip: ["Attention to every inquiry", "Context across conversations", "A human within reach"],
    demoLabel: "01 / TRY THE FLOW", demoTitle: "A good conversation\nstarts with listening.", demoDesc: "Explore a short apartment inquiry. Pick a question and see how a conversation turns into a request.", demoNotice: "Interactive example with scripted replies and fictional properties. No live AI is connected.", chatTitle: "Plumo · real estate agency", chatStatus: "Demo mode", welcome: "Hello! I can help with apartment questions and prepare a request for a manager. What would you like to know?", prompts: ["What apartments are available?", "Can I arrange a viewing?", "I'd like to speak to a person"], replies: ["Our fictional catalog has a two-room, 64 m² apartment in the south of the city. What size are you looking for?", "In this example, you can request Saturday. A manager needs to check availability and confirm the time. No booking has been made.", "In a live integration, a manager would receive your request and conversation history. This demo does not send a notification."], reset: "Start again", choose: "Choose a question below",
    memoryLabel: "02 / CONTEXT", memoryTitle: "Pick up right where\nyou left off.", memoryDesc: "Customers shouldn't have to repeat their story. Plumo is designed to keep their needs, details and next step together.", memoryPoints: ["A concise summary instead of searching through messages", "Facts from your business knowledge base", "Conversation history passed to your team"], memoryNote: "Linking chats and calls is a future product milestone.", memoryCard: "CUSTOMER CONTEXT", memorySummary: "Interested in a two-room apartment. Prefers the south of the city. Would like to discuss a Saturday viewing.", source: "From an illustrative conversation", human: "Hand off to a manager", humanNote: "Example card — no handoff is performed",
    processLabel: "03 / HOW IT WORKS", processTitle: "Your business.\nYour way of talking.", steps: [["Get acquainted", "Choose one workflow and define what a successful conversation looks like."], ["Add your knowledge", "Collect services, prices and answers. You review the information."], ["Test together", "Try real customer questions and define when your team takes over."], ["Launch a pilot", "Connect an agreed channel and review the outcomes together."]],
    channelLabel: "04 / CHANNELS", channelTitle: "Where your next\nconversation begins.", channelDesc: "We start with one channel. More follow after the pilot and technical validation.", channels: [["↗", "Web chat", "Demo on this page"], ["↗", "WhatsApp", "Planned"], ["◎", "Instagram", "Planned"], ["➤", "Telegram", "Planned"], ["↗", "Phone calls", "Technical validation pending"]],
    statsLabel: "05 / MEASURE WHAT MATTERS", statsTitle: "See the conversation.\nUnderstand the next step.", statsDesc: "Inquiries, meeting requests and human handoffs — the metrics we will use to evaluate a pilot.", statsBadge: "Sample data · not customer results", statsPeriod: "Weekly inquiries", statsUnits: "inquiries", days: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"], metrics: ["Inquiries", "Meeting requests", "Human handoffs"],
    faqLabel: "06 / QUESTIONS", faqTitle: "Let's clear things up.", faqs: [["Will Plumo replace my sales manager?", "Plumo is designed to handle initial inquiries and gather context. Complex questions, negotiation and closing the deal stay with your team."], ["Where do prices and terms come from?", "From your approved business information. When a fact is missing, the workflow should ask a manager rather than invent an answer."], ["Which languages are planned?", "The product targets Russian and Kyrgyz, including mixed speech. Agent quality is evaluated separately before a pilot. This website is available in Russian and English; Kyrgyz will follow."], ["Can we use our existing phone number?", "That needs to be checked with your carrier and telephony provider. Compatibility is confirmed through a technical test."], ["Does the demo actually book a viewing?", "No. It illustrates a workflow using fictional data. It does not notify a manager or reserve a time slot."], ["How can I join a pilot?", "Tell us about your business using the form below. We will discuss the channel, workflow, terms and success criteria before launch."]],
    ctaLabel: "LET'S START WITH YOUR BUSINESS", ctaTitle: "Give the next conversation\na next chapter.", ctaDesc: "Tell us what your customers ask. Together, we'll choose a workflow for your first pilot.", name: "Your name", business: "Company", email: "Email address", message: "What would you like to automate?", send: "Prepare an email", mailNote: "Opens your email app with a draft. You review and send it.", mailReady: "Your email app has been requested. If it didn't open, write to contact@plumo.app. No request was submitted through this website.", subject: "Plumo pilot inquiry",
  },
};

export function Landing() {
  const router = useRouter();
  const { locale } = useLanguage();
  const c = copy[locale];
  const [mailReady, setMailReady] = useState(false);
  const [pricingChoice, setPricingChoice] = useState<PricingRequest | null>(null);
  const [demoOpen, setDemoOpen] = useState(false);
  const [demoStep, setDemoStep] = useState<"choice" | "expert">("choice");
  const [demoPath, setDemoPath] = useState<"expert" | "self" | null>(null);

  function openDemo(request: PricingRequest | null = null, step: "choice" | "expert" = "choice") {
    setPricingChoice(request);
    setDemoStep(step);
    setMailReady(false);
    setDemoOpen(true);
  }

  function followPath(path: "expert" | "self") {
    setDemoPath(path);
    if (path === "expert") {
      setDemoStep("expert");
    } else {
      setDemoOpen(false);
      const params = pricingChoice ? new URLSearchParams({ plan: pricingChoice.choice, volume: String(pricingChoice.volume), billing: pricingChoice.billing, voice: String(pricingChoice.voice) }) : null;
      router.push(`/create/wizard${params ? `?${params}` : ""}`);
    }
  }

  function prepareMail(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const pathLabel = demoPath ? (locale === "ru" ? (demoPath === "self" ? "После самостоятельного демо" : "Демо с сотрудником") : (demoPath === "self" ? "After the self-guided demo" : "Demo with the team")) : "";
    const body = `${pathLabel ? `${pathLabel}\n\n` : ""}${c.name}: ${data.get("name")}\n${c.business}: ${data.get("company")}\n${c.email}: ${data.get("email")}\n\n${data.get("message")}`;
    window.location.href = `mailto:contact@plumo.app?subject=${encodeURIComponent(c.subject)}&body=${encodeURIComponent(pricingChoice ? `${locale === "ru" ? "Тариф / запрос" : "Plan / inquiry"}: ${pricingRequestLabel(locale, pricingChoice)}\n\n${body}` : body)}`;
    setMailReady(true);
  }
  return <main id="main" className="landing">
    <Hero onDemo={() => openDemo()} />
    <CustomerSituations />

    <VoiceCallDemo />

    <DialogueToLead onDiscuss={() => { setDemoPath("self"); openDemo(pricingChoice, "expert"); }} />

    <SetupPipeline onDemo={() => openDemo()} />

    <Statistics />

    <Pricing onChoose={request => openDemo(request)} onDemo={openDemo} />

    <FAQ items={c.faqs} />

    <PilotCTA onDemo={() => openDemo(pricingChoice)} />
    {demoOpen && <DemoChoice onClose={() => setDemoOpen(false)} onSelect={followPath} step={demoStep} onBack={() => setDemoStep("choice")}
      expertForm={<DemoContactForm onSubmit={prepareMail} selection={pricingChoice} mailReady={mailReady} formCopy={c} />} />}
  </main>;
}
