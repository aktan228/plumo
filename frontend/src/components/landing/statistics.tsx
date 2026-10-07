"use client";

import { useMemo, useState, type CSSProperties } from "react";
import { useReducedMotion } from "motion/react";
import { AreaChart, Area } from "@/components/charts/area-chart";
import { Grid } from "@/components/charts/grid";
import { YAxis } from "@/components/charts/y-axis";
import { ChartTooltip } from "@/components/charts/tooltip/chart-tooltip";
import { useLanguage } from "@/lib/i18n";
import "./statistics.css";

// Fixed illustrative data: the 7-day view is the last seven days of this same month.
const inquiries = [11, 15, 13, 18, 20, 12, 14, 16, 21, 18, 14, 22, 24, 17, 20, 26, 19, 23, 27, 21, 25, 22, 28, 12, 18, 14, 25, 19, 16, 24];
const leads = [2, 3, 3, 4, 5, 2, 3, 4, 5, 4, 3, 5, 6, 4, 5, 6, 4, 6, 7, 5, 6, 5, 7, 3, 4, 3, 7, 5, 4, 6];
const handoffs = [1, 2, 2, 2, 3, 1, 2, 2, 3, 2, 2, 3, 3, 2, 3, 4, 2, 3, 4, 2, 3, 3, 4, 1, 3, 2, 4, 3, 2, 3];
const rows = inquiries.map((value, index) => ({ date: new Date(Date.UTC(2026, 8, index + 1, 12)), inquiries: value, leads: leads[index], handoffs: handoffs[index] }));
const keys = ["inquiries", "leads", "handoffs"] as const;
type Metric = typeof keys[number];

const copy = {
  ru: {
    title: "Разговоры в цифрах.", accent: "Результат на виду.", intro: "Следите за потоком обращений и тем, как клиенты переходят к следующему шагу.",
    overview: "Обзор обращений", sample: "Пример данных", periods: ["7 дней", "30 дней"], periodLabel: "Период статистики", seriesLabel: "Показатель графика",
    labels: { inquiries: "Обращения", leads: "Заявки на встречу", handoffs: "Передачи менеджеру" },
    notes: { inquiries: "Новые разговоры с клиентами", leads: "Клиент оставил пожелание на встречу", handoffs: "Нужен ответ вашей команды" },
    daily: "Динамика по дням", unit: "за выбранный период", detail: "Выберите день", chartHelp: "Наведите на график или выберите день ниже", rate: "Обращений с заявкой", rateNote: "Заявка означает интерес к встрече. Время подтверждает менеджер.", disclaimer: "Иллюстрация аналитики на вымышленных данных.",
  },
  en: {
    title: "Conversations in numbers.", accent: "Outcomes in sight.", intro: "Follow incoming inquiries and see how customers move to the next step.",
    overview: "Inquiry overview", sample: "Sample data", periods: ["7 days", "30 days"], periodLabel: "Statistics period", seriesLabel: "Chart metric",
    labels: { inquiries: "Inquiries", leads: "Meeting requests", handoffs: "Manager handoffs" },
    notes: { inquiries: "New customer conversations", leads: "Customers requesting a meeting", handoffs: "Your team’s input is needed" },
    daily: "Daily activity", unit: "in the selected period", detail: "Choose a day", chartHelp: "Hover over the chart or choose a day below", rate: "Inquiries with a meeting request", rateNote: "A request expresses interest in a meeting. Your manager confirms the time.", disclaimer: "Illustrative analytics using fictional data.",
  },
};

const theme = {
  "--chart-background": "#fff", "--chart-foreground": "#111113", "--chart-foreground-muted": "#73737c", "--chart-grid": "#eaeaec", "--chart-label": "#73737c", "--chart-line-primary": "#2b55ff", "--chart-crosshair": "#2b55ff", "--chart-tooltip-background": "#111113", "--chart-tooltip-foreground": "#fff", "--chart-tooltip-muted": "#aeb2bd", "--chart-indicator-color": "#2b55ff",
} as CSSProperties;

export function Statistics() {
  const { locale } = useLanguage();
  const c = copy[locale];
  const reduced = Boolean(useReducedMotion());
  const [period, setPeriod] = useState<7 | 30>(7);
  const [metric, setMetric] = useState<Metric>("inquiries");
  const [selected, setSelected] = useState(6);
  const data = useMemo(() => rows.slice(-period), [period]);
  const totals = useMemo(() => data.reduce((sum, row) => ({ inquiries: sum.inquiries + row.inquiries, leads: sum.leads + row.leads, handoffs: sum.handoffs + row.handoffs }), { inquiries: 0, leads: 0, handoffs: 0 }), [data]);
  const dateFormat = new Intl.DateTimeFormat(locale === "ru" ? "ru-RU" : "en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
  const fullDate = new Intl.DateTimeFormat(locale === "ru" ? "ru-RU" : "en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });
  const number = new Intl.NumberFormat(locale === "ru" ? "ru-RU" : "en-GB");
  const dateRange = `${dateFormat.format(data[0].date)} — ${dateFormat.format(data[data.length - 1].date)}, 2026`;
  const chosen = data[Math.min(selected, data.length - 1)];

  return <section id="statistics" aria-labelledby="statistics-title" className="mx-auto max-w-[1440px] px-6 py-20 text-plumo-ink md:px-8 md:py-28 lg:px-16">
    <div className="flex flex-col justify-between gap-6 lg:flex-row lg:items-end"><h2 id="statistics-title" className="!text-[clamp(36px,4.7vw,64px)] !font-bold !leading-[1.06]">{c.title}<br /><span className="text-plumo-blue">{c.accent}</span></h2><p className="m-0 max-w-[340px] text-[16px] leading-relaxed text-plumo-muted">{c.intro}</p></div>
    <div className="mt-12 overflow-hidden rounded-[32px] border border-solid border-plumo-line bg-white shadow-[0_16px_70px_#11111306] md:mt-16">
      <div className="flex flex-wrap items-center justify-between gap-5 px-5 py-6 md:px-8"><div><h3 className="m-0 text-[18px] font-semibold tracking-tight">{c.overview}</h3><p className="mb-0 mt-2 text-[11px] text-plumo-muted">{dateRange} · {c.sample}</p></div><div role="group" aria-label={c.periodLabel} className="flex gap-1 rounded-full bg-[#f3f4f6] p-1">{([7, 30] as const).map((days, index) => <button key={days} type="button" aria-pressed={period === days} onClick={() => { setPeriod(days); setSelected(days - 1); }} className={`cursor-pointer rounded-full border-0 px-5 py-2.5 font-[inherit] text-[12px] transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-plumo-blue ${period === days ? "bg-plumo-ink text-white" : "bg-transparent text-plumo-muted hover:text-plumo-ink"}`}>{c.periods[index]}</button>)}</div></div>
      <div role="group" aria-label={c.seriesLabel} className="grid grid-cols-1 border-0 border-y border-solid border-plumo-line md:grid-cols-3">{keys.map((key, index) => <button key={key} type="button" aria-pressed={metric === key} onClick={() => setMetric(key)} className={`relative flex cursor-pointer items-center justify-between gap-4 border-0 border-solid px-5 py-5 text-left font-[inherit] transition-colors focus-visible:z-10 focus-visible:outline-2 focus-visible:outline-offset-[-3px] focus-visible:outline-plumo-blue md:block md:px-8 md:py-7 ${index ? "border-t border-plumo-line md:border-l md:border-t-0" : ""} ${metric === key ? "bg-plumo-soft" : "bg-white hover:bg-[#fafafa]"}`}><span className="block"><span className={`block text-[12px] ${metric === key ? "text-plumo-blue" : "text-plumo-muted"}`}>{c.labels[key]}</span><span className="mt-2 hidden text-[11px] text-plumo-muted md:block">{c.notes[key]}</span></span><strong className={`block text-[38px] font-medium leading-none tracking-[-0.045em] tabular-nums md:mt-5 md:text-[46px] ${metric === key ? "text-plumo-blue" : "text-plumo-ink"}`}>{number.format(totals[key])}</strong>{metric === key && <span aria-hidden="true" className="absolute inset-x-0 bottom-0 h-[2px] bg-plumo-blue" />}</button>)}</div>
      <div className="grid grid-cols-1 xl:grid-cols-[1fr_260px]">
        <div className="min-w-0 px-4 pb-6 pt-7 md:px-8"><div className="mb-3 flex flex-wrap items-center justify-between gap-2"><h4 className="m-0 text-[13px] font-medium">{c.labels[metric]} <span className="font-normal text-plumo-muted">/ {c.daily.toLowerCase()}</span></h4><span className="text-[10px] text-plumo-muted">{c.unit}</span></div>
          <div className="plumo-analytics-chart" style={theme} role="img" aria-label={`${c.labels[metric]}: ${number.format(totals[metric])}. ${dateRange}`}>
            <AreaChart key={`${period}-${metric}`} data={data} animationDuration={reduced ? 0 : 900} yDomainTween={!reduced} margin={{ top: 24, left: 36, right: 12, bottom: 12 }} style={{ height: 280, aspectRatio: "auto", touchAction: "pan-y" }}>
              <Grid horizontal numTicksRows={4} stroke="#eaeaec" strokeDasharray="3,5" />
              <Area dataKey={metric} fill="#2b55ff" stroke="#2b55ff" strokeWidth={2.5} fillOpacity={0.18} animate={!reduced} showHighlight={!reduced} />
              <YAxis numTicks={4} formatLargeNumbers={false} />
              <ChartTooltip showDatePill={false} damping={reduced ? 0 : 20} indicatorColor="#2b55ff" content={({ point }) => <div className="px-4 py-3 text-white"><p className="m-0 text-[11px] text-white/60">{fullDate.format(point.date as Date)}</p><p className="mb-0 mt-2 flex items-center justify-between gap-5 text-[12px]"><span>{c.labels[metric]}</span><strong className="text-[18px] tabular-nums">{number.format(Number(point[metric]))}</strong></p></div>} />
            </AreaChart>
          </div>
          <div aria-hidden="true" className="ml-9 mr-3 flex justify-between text-[10px] text-plumo-muted">{[0, Math.round((period - 1) / 3), Math.round((period - 1) * 2 / 3), period - 1].map(index => <span key={index}>{dateFormat.format(data[index].date)}</span>)}</div>
          <div className="mt-7 flex flex-wrap items-center justify-between gap-2 text-[11px]"><label htmlFor="statistics-day" className="text-plumo-muted">{c.detail}</label><output htmlFor="statistics-day" className="text-plumo-ink">{dateFormat.format(chosen.date)} <span className="mx-2 text-plumo-line">/</span><strong className="text-plumo-blue tabular-nums">{chosen[metric]}</strong> {c.labels[metric].toLowerCase()}</output></div>
          <input id="statistics-day" type="range" min={0} max={period - 1} value={selected} onChange={event => setSelected(Number(event.target.value))} aria-valuetext={`${fullDate.format(chosen.date)}: ${chosen[metric]} ${c.labels[metric]}`} className="mx-0 mb-0 mt-3 h-5 w-full cursor-pointer accent-plumo-blue" />
        </div>
        <aside className="m-4 mt-0 flex flex-col justify-between rounded-[24px] bg-plumo-ink p-6 text-white md:m-6 xl:ml-0 xl:mt-6"><div><p className="m-0 max-w-[190px] text-[13px] leading-relaxed text-white/65">{c.rate}</p><p className="mb-0 mt-6 text-[56px] leading-none tracking-[-0.06em] tabular-nums">{Math.round(totals.leads / totals.inquiries * 100)}<span className="ml-1 text-[28px] text-white/50">%</span></p><div className="mt-6 flex h-2 overflow-hidden rounded-full bg-white/15"><div className="h-full rounded-full bg-plumo-blue transition-[width] duration-500 motion-reduce:transition-none" style={{ width: `${totals.leads / totals.inquiries * 100}%` }} /></div><p className="mb-0 mt-3 text-[11px] text-white/45">{totals.leads} / {totals.inquiries}</p></div><p className="mb-0 mt-8 border-0 border-t border-solid border-white/15 pt-5 text-[12px] leading-[1.7] text-white/60">{c.rateNote}</p></aside>
      </div>
    </div>
    <div className="mt-5 flex flex-wrap justify-between gap-2 text-[11px] text-plumo-muted"><span>{c.disclaimer}</span><span>{c.chartHelp}</span></div>
  </section>;
}
