import { describe, expect, it } from 'vitest';
import { formatHeatmapMonthLabel, getVisibleHeatmapWeeks } from './ProcessingOverview';

describe('getVisibleHeatmapWeeks', () => {
  it('keeps a readable minimum range when the container is narrow', () => {
    expect(getVisibleHeatmapWeeks(0)).toBe(26);
    expect(getVisibleHeatmapWeeks(320)).toBe(26);
  });

  it('shows more weeks instead of enlarging the cells on wider screens', () => {
    expect(getVisibleHeatmapWeeks(640)).toBe(35);
    expect(getVisibleHeatmapWeeks(1200)).toBe(68);
  });

  it('uses the viewport width when the measured width is unreliable', () => {
    expect(getVisibleHeatmapWeeks(0, 1200)).toBe(68);
    expect(getVisibleHeatmapWeeks(120, 2200)).toBe(126);
  });

  it('caps the range at a sane multi-year maximum', () => {
    expect(getVisibleHeatmapWeeks(4000)).toBe(156);
  });
});

describe('formatHeatmapMonthLabel', () => {
  it('uses the app locale for month abbreviations', () => {
    expect(formatHeatmapMonthLabel('2026-03-01', 'en')).toBe('Mar');
    expect(formatHeatmapMonthLabel('2026-03-01', 'nl')).toBe('mrt');
  });
});
