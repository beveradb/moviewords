/** Chart tick/tooltip value. Per-million rates are big (1 decimal is plenty);
 * per-film averages are often < 1, where 1 decimal would flatten them to 0. */
export function formatChartValue(v: number): string {
  if (v === 0) return '0'
  if (Math.abs(v) >= 1) return String(Math.round(v * 10) / 10)
  return String(Number(v.toPrecision(2)))
}
