const HEATMAP_MIN_WEEKS = 26;
const HEATMAP_MAX_WEEKS = 156;
export const HEATMAP_RECT_SIZE = 13;
export const HEATMAP_GAP = 4;
export const HEATMAP_RECT_RADIUS = 3;
export const HEATMAP_WEEKDAY_LABELS_WIDTH = 30;
export const HEATMAP_MONTH_LABELS_HEIGHT = 24;
export const HEATMAP_VIEWPORT_PADDING_RIGHT = 16;
const HEATMAP_MIN_RELIABLE_VIEWPORT_WIDTH = 160;
export const HEATMAP_WEEKDAY_LABELS = ['M', '', 'W', '', 'F', '', 'S'];

export function parseUtcDateKey(value: string): Date {
  const [year, month, day] = value.split('-').map(Number);
  return new Date(Date.UTC(year, (month ?? 1) - 1, day ?? 1));
}

export function getVisibleHeatmapWeeks(measuredWidth: number, fallbackViewportWidth: number = 0) {
  const sourceWidth =
    measuredWidth >= HEATMAP_MIN_RELIABLE_VIEWPORT_WIDTH ? measuredWidth : fallbackViewportWidth;
  const availableWidth = Math.max(
    sourceWidth - HEATMAP_WEEKDAY_LABELS_WIDTH - HEATMAP_VIEWPORT_PADDING_RIGHT,
    0
  );
  const visibleWeeks =
    availableWidth > 0
      ? Math.floor((availableWidth + HEATMAP_GAP) / (HEATMAP_RECT_SIZE + HEATMAP_GAP))
      : HEATMAP_MIN_WEEKS;

  return Math.min(HEATMAP_MAX_WEEKS, Math.max(HEATMAP_MIN_WEEKS, visibleWeeks));
}

export function formatHeatmapMonthLabel(date: string, locale: string): string {
  return parseUtcDateKey(date).toLocaleDateString(locale, {
    month: 'short',
    timeZone: 'UTC',
  });
}
