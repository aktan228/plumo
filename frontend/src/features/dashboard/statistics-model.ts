export function statisticsPeriod(now = new Date()): { from: string; to: string } {
  const local = new Date(now.getTime() + 6 * 60 * 60 * 1000);
  const to = local.toISOString().slice(0, 10);
  local.setUTCDate(local.getUTCDate() - 6);
  return { from: local.toISOString().slice(0, 10), to };
}
export function validStatisticsPeriod(from: string, to: string): boolean {
  const valid = (value: string) => /^\d{4}-\d{2}-\d{2}$/.test(value)
    && Number.isFinite(Date.parse(value)) && new Date(value).toISOString().slice(0, 10) === value;
  if (!valid(from) || !valid(to) || from < "2000-01-01" || to > "2100-12-31") return false;
  const span = (Date.parse(to) - Date.parse(from)) / 86400000;
  return span >= 0 && span <= 91;
}
