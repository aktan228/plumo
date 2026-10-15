// Delay before the next poll: the base interval, doubled per consecutive failure, at most a minute.
export function nextPollDelay(interval: number, failures: number): number {
  if (failures <= 0) return interval;
  return Math.min(60_000, interval * 2 ** Math.min(failures, 6));
}
