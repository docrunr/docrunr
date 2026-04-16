import { AreaChart } from '@mantine/charts';
import {
  Alert,
  Box,
  Group,
  Paper,
  SegmentedControl,
  SimpleGrid,
  Stack,
  Text,
  Tooltip,
  useComputedColorScheme,
} from '@mantine/core';
import { useElementSize, useViewportSize } from '@mantine/hooks';
import {
  IconAlertTriangle,
  IconChecks,
  IconClock,
  IconFileDescription,
  IconStack2,
  IconTypography,
} from '@tabler/icons-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { TooltipContentProps } from 'recharts';
import { useWorkerAuth } from '../../../app/useWorkerAuth';
import { useWorkerMode } from '../../../contexts/useWorkerMode';
import { usePolling } from '../../../hooks/usePolling';
import { fetchJobs, fetchOverview } from '../../../services/workerApi';
import type { AnyJob, WorkerOverview } from '../../../services/workerApi.types';
import { formatFileSize } from '../../../utils/file-size';
import { getTimeBucketAverages, getTimeBucketSums } from '../../processing/lib/metric-series';
import {
  getMimeCountsPerTimeBucket,
  getProfileCountsPerTimeBucket,
} from '../../processing/lib/mime-series';
import type { OverviewTimeRange } from '../../processing/lib/time-buckets';
import {
  formatHeatmapMonthLabel,
  getVisibleHeatmapWeeks,
  HEATMAP_GAP,
  HEATMAP_MONTH_LABELS_HEIGHT,
  HEATMAP_RECT_RADIUS,
  HEATMAP_RECT_SIZE,
  HEATMAP_VIEWPORT_PADDING_RIGHT,
  HEATMAP_WEEKDAY_LABELS,
  HEATMAP_WEEKDAY_LABELS_WIDTH,
  parseUtcDateKey,
} from './processingOverviewHeatmap';
import { ServerUptime } from './ServerUptime';
import { StatCard } from './StatCard';

type CpuChartPoint = { sample: number; cpu: number };
type HeatmapCell = { date: string | null; value: number | null };
type HeatmapMonthLabel = { date: string; weekIndex: number };

function formatUtcDateKey(value: Date): string {
  const year = value.getUTCFullYear();
  const month = String(value.getUTCMonth() + 1).padStart(2, '0');
  const day = String(value.getUTCDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function getWeekAlignedTrailingUtcDateRange(
  weeks: number,
  now: Date = new Date()
): {
  startDate: string;
  endDate: string;
} {
  const end = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
  const currentWeekStart = new Date(end);
  const dayOffset = (currentWeekStart.getUTCDay() + 6) % 7;
  currentWeekStart.setUTCDate(currentWeekStart.getUTCDate() - dayOffset);

  const start = new Date(currentWeekStart);
  start.setUTCDate(start.getUTCDate() - (Math.max(weeks, 1) - 1) * 7);

  return {
    startDate: formatUtcDateKey(start),
    endDate: formatUtcDateKey(end),
  };
}

function buildDailyHeatmapData(
  jobs: AnyJob[],
  startDate: string,
  endDate: string
): Record<string, number> {
  const startMs = Date.parse(`${startDate}T00:00:00.000Z`);
  const endMs = Date.parse(`${endDate}T23:59:59.999Z`);
  const buckets: Record<string, number> = {};

  for (const job of jobs) {
    if (!job.finished_at) continue;
    const finishedAt = new Date(job.finished_at);
    const finishedMs = finishedAt.getTime();
    if (Number.isNaN(finishedMs) || finishedMs < startMs || finishedMs > endMs) continue;
    const key = formatUtcDateKey(finishedAt);
    buckets[key] = (buckets[key] ?? 0) + 1;
  }

  return buckets;
}

const CPU_TRANSITION_DURATION_MS = 900;

function addUtcDays(date: Date, days: number): Date {
  return new Date(date.getTime() + days * 24 * 60 * 60 * 1000);
}

function buildHeatmapCalendar(
  startDate: string,
  endDate: string,
  data: Record<string, number>,
  weeksCount: number
): { weeks: HeatmapCell[][]; monthLabels: HeatmapMonthLabel[] } {
  const start = parseUtcDateKey(startDate);
  const end = parseUtcDateKey(endDate);
  const weeks: HeatmapCell[][] = [];
  const monthLabels: HeatmapMonthLabel[] = [];
  let previousMonth = -1;

  for (let weekIndex = 0; weekIndex < weeksCount; weekIndex += 1) {
    const weekStart = addUtcDays(start, weekIndex * 7);
    const week: HeatmapCell[] = [];
    let labelDate: string | null = null;

    for (let dayIndex = 0; dayIndex < 7; dayIndex += 1) {
      const day = addUtcDays(weekStart, dayIndex);
      const inRange = day >= start && day <= end;
      const date = formatUtcDateKey(day);

      if (!inRange) {
        week.push({ date: null, value: null });
        continue;
      }

      if (labelDate == null && day.getUTCDate() === 1) {
        labelDate = date;
      }

      week.push({
        date,
        value: data[date] ?? 0,
      });
    }

    const firstVisibleCell = week.find((cell) => cell.date);
    if (firstVisibleCell?.date) {
      const month = parseUtcDateKey(firstVisibleCell.date).getUTCMonth();
      if (weekIndex === 0 || month !== previousMonth) {
        monthLabels.push({ date: firstVisibleCell.date, weekIndex });
        previousMonth = month;
      } else if (labelDate) {
        monthLabels.push({ date: labelDate, weekIndex });
        previousMonth = parseUtcDateKey(labelDate).getUTCMonth();
      }
    }

    weeks.push(week);
  }

  return { weeks, monthLabels };
}

function getHeatmapColorIndex(value: number | null, maxRaw: number, colorCount: number): number {
  if (colorCount <= 1 || value == null || value <= 0 || maxRaw <= 0) {
    return 0;
  }

  return Math.round(((colorCount - 1) * Math.sqrt(value)) / Math.sqrt(maxRaw));
}

/** Linear bands on raw counts (used when there is no peak to sqrt-scale against). */
function buildLinearHeatmapLegendRanges(
  maxValue: number,
  colorCount: number
): Array<{ min: number; max: number }> {
  if (colorCount <= 0) {
    return [];
  }

  const upperBound = Math.max(1, maxValue);
  return Array.from({ length: colorCount }, (_, index) => {
    const min = Math.floor((index * upperBound) / colorCount) + 1;
    const max =
      index === colorCount - 1 ? upperBound : Math.floor(((index + 1) * upperBound) / colorCount);

    return {
      min: Math.min(min, upperBound),
      max: Math.max(Math.min(max, upperBound), Math.min(min, upperBound)),
    };
  });
}

/**
 * Raw processed-file counts per legend swatch when the heatmap maps `sqrt(count)` linearly
 * (Mantine uses `round((colorCount - 1) * sqrt(v) / sqrt(peak))`).
 */
function buildSqrtHeatmapLegendRanges(
  maxRaw: number,
  colorCount: number
): Array<{ min: number; max: number }> {
  if (colorCount <= 0) {
    return [];
  }

  const M = Math.floor(maxRaw);
  if (M <= 0) {
    return buildLinearHeatmapLegendRanges(0, colorCount);
  }

  const mult = colorCount - 1;
  const ranges: Array<{ min: number; max: number }> = [];

  for (let k = 0; k < colorCount; k++) {
    const pLow = k === 0 ? 0 : (k - 0.5) / mult;
    const pHigh = k === mult ? 1 : (k + 0.5) / mult;

    let minV: number;
    let maxV: number;

    if (k === 0) {
      minV = 1;
      maxV = Math.min(M, Math.floor(pHigh * pHigh * M - 1e-9));
    } else if (k === mult) {
      minV = Math.max(1, Math.ceil(pLow * pLow * M - 1e-12));
      maxV = M;
    } else {
      minV = Math.max(1, Math.ceil(pLow * pLow * M - 1e-12));
      maxV = Math.min(M, Math.floor(pHigh * pHigh * M - 1e-9));
    }

    if (maxV < minV) {
      maxV = minV;
    }
    ranges.push({ min: minV, max: maxV });
  }

  return ranges;
}

export function ProcessingOverview() {
  const { t, i18n } = useTranslation();
  const { canFetchProtected } = useWorkerAuth();
  const { mode } = useWorkerMode();
  const [timeRange, setTimeRange] = useState<OverviewTimeRange>('1h');
  const [overview, setOverview] = useState<WorkerOverview | null>(null);
  const [, setOverviewRefreshing] = useState(false);
  const [overviewError, setOverviewError] = useState<string | null>(null);
  const [overviewJobs, setOverviewJobs] = useState<AnyJob[]>([]);
  const [animatedCpuChartData, setAnimatedCpuChartData] = useState<CpuChartPoint[]>([]);
  const { ref: heatmapViewportRef, width: heatmapViewportWidth } = useElementSize<HTMLDivElement>();
  const { width: viewportWidth } = useViewportSize();
  const heatmapScrollRef = useRef<HTMLDivElement | null>(null);
  const animatedCpuChartDataRef = useRef<CpuChartPoint[]>([]);
  const previousCpuHistoryRef = useRef<number[]>([]);
  const nextCpuSampleIdRef = useRef(0);
  const visibleHeatmapWeeks = useMemo(
    () => getVisibleHeatmapWeeks(heatmapViewportWidth, viewportWidth),
    [heatmapViewportWidth, viewportWidth]
  );

  const processedHeatmapRange = useMemo(
    () => getWeekAlignedTrailingUtcDateRange(visibleHeatmapWeeks),
    [visibleHeatmapWeeks]
  );
  const processedSparkline = useMemo(
    () => getTimeBucketSums(overviewJobs, timeRange, () => 1),
    [overviewJobs, timeRange]
  );
  const processedInRange = useMemo(
    () => processedSparkline.reduce((sum, v) => sum + v, 0),
    [processedSparkline]
  );
  const rangeJobs = useMemo(() => {
    const now = Date.now();
    const rangeMs =
      timeRange === '1h'
        ? 60 * 60 * 1000
        : timeRange === '12h'
          ? 12 * 60 * 60 * 1000
          : timeRange === '1d'
            ? 24 * 60 * 60 * 1000
            : 7 * 24 * 60 * 60 * 1000;
    const cutoff = now - rangeMs;
    return overviewJobs.filter((j) => {
      if (!j.finished_at) return false;
      const t = new Date(j.finished_at).getTime();
      return !Number.isNaN(t) && t >= cutoff;
    });
  }, [overviewJobs, timeRange]);
  const failedInRange = useMemo(
    () => rangeJobs.filter((j) => j.status === 'error').length,
    [rangeJobs]
  );
  const avgDurationInRange = useMemo(() => {
    if (rangeJobs.length === 0) return 0;
    const total = rangeJobs.reduce((sum, j) => sum + j.duration_seconds, 0);
    return total / rangeJobs.length;
  }, [rangeJobs]);
  const avgTokensInRange = useMemo(() => {
    if (rangeJobs.length === 0) return 0;
    const total = rangeJobs.reduce(
      (sum, j) => sum + ('total_tokens' in j ? (j.total_tokens as number) : 0),
      0
    );
    return total / rangeJobs.length;
  }, [rangeJobs]);
  const avgTokensSparkline = useMemo(
    () =>
      getTimeBucketAverages(overviewJobs, timeRange, (j) => {
        const v = 'total_tokens' in j ? (j.total_tokens as number) : Number.NaN;
        return Number.isFinite(v) ? v : Number.NaN;
      }),
    [overviewJobs, timeRange]
  );
  const totalChunksInRange = useMemo(
    () => rangeJobs.reduce((sum, j) => sum + j.chunk_count, 0),
    [rangeJobs]
  );
  const avgChunksInRange = useMemo(() => {
    if (rangeJobs.length === 0) return 0;
    return totalChunksInRange / rangeJobs.length;
  }, [rangeJobs, totalChunksInRange]);
  const avgFileSizeInRange = useMemo(() => {
    const sized = rangeJobs.filter(
      (j) =>
        'size_bytes' in j &&
        typeof j.size_bytes === 'number' &&
        Number.isFinite(j.size_bytes) &&
        (j.size_bytes as number) >= 0
    );
    if (sized.length === 0) return null;
    return (
      sized.reduce((sum, j) => sum + (j as { size_bytes: number }).size_bytes, 0) / sized.length
    );
  }, [rangeJobs]);
  const avgFileSizeSparkline = useMemo(
    () =>
      getTimeBucketAverages(overviewJobs, timeRange, (j) => {
        if (!('size_bytes' in j)) return Number.NaN;
        const v = j.size_bytes as number;
        return typeof v === 'number' && Number.isFinite(v) ? v : Number.NaN;
      }),
    [overviewJobs, timeRange]
  );
  const processedGroupByBucket = useMemo(
    () =>
      mode === 'llm'
        ? getProfileCountsPerTimeBucket(overviewJobs, timeRange)
        : getMimeCountsPerTimeBucket(overviewJobs, timeRange),
    [overviewJobs, timeRange, mode]
  );
  const processedHeatmapData = useMemo(
    () =>
      buildDailyHeatmapData(
        overviewJobs,
        processedHeatmapRange.startDate,
        processedHeatmapRange.endDate
      ),
    [overviewJobs, processedHeatmapRange]
  );
  const processedHeatmapPeak = useMemo(() => {
    const values = Object.values(processedHeatmapData);
    return values.length > 0 ? Math.max(...values) : 0;
  }, [processedHeatmapData]);
  const heatmapGridWidth = useMemo(
    () => visibleHeatmapWeeks * HEATMAP_RECT_SIZE + (visibleHeatmapWeeks - 1) * HEATMAP_GAP,
    [visibleHeatmapWeeks]
  );
  const heatmapLegendOffset = useMemo(
    () => Math.max(0, Math.round((HEATMAP_RECT_SIZE + HEATMAP_GAP) / 2) - 4),
    []
  );
  const heatmapCalendar = useMemo(
    () =>
      buildHeatmapCalendar(
        processedHeatmapRange.startDate,
        processedHeatmapRange.endDate,
        processedHeatmapData,
        visibleHeatmapWeeks
      ),
    [
      processedHeatmapData,
      processedHeatmapRange.endDate,
      processedHeatmapRange.startDate,
      visibleHeatmapWeeks,
    ]
  );
  const processedChartDescription = useMemo(() => {
    switch (timeRange) {
      case '1h':
        return t('overview.range.1h');
      case '12h':
        return t('overview.range.12h');
      case '1d':
        return t('overview.range.1d');
      default:
        return t('overview.range.7d');
    }
  }, [timeRange, t]);

  const avgMetricSubtitle = useMemo(
    () => t('overview.avgMetricSub', { range: processedChartDescription }),
    [t, processedChartDescription]
  );

  const formatProcessedHeatmapTooltip = useCallback(
    (date: string, value: number | null) => {
      const dateLabel = new Date(`${date}T00:00:00.000Z`).toLocaleDateString(undefined, {
        day: 'numeric',
        month: 'short',
        year: 'numeric',
        timeZone: 'UTC',
      });
      const count = value ?? 0;
      return t('overview.heatmapTooltip', { count, date: dateLabel });
    },
    [t]
  );

  const renderCpuTooltip = useCallback(
    ({ active, payload }: TooltipContentProps<number, string>) => {
      if (!active || !payload?.length) {
        return null;
      }
      const raw = payload[0]?.value;
      const pct = typeof raw === 'number' && Number.isFinite(raw) ? Math.round(raw) : 0;
      return (
        <Paper withBorder shadow="md" p="xs" radius="md">
          <Text size="sm" fw={700}>
            {t('overview.cpuTooltip', { pct })}
          </Text>
        </Paper>
      );
    },
    [t]
  );

  const computedColorScheme = useComputedColorScheme('light');
  const sparklineColor = computedColorScheme === 'dark' ? 'gray.4' : 'gray.6';
  const heatmapColors =
    computedColorScheme === 'dark'
      ? [
          'var(--mantine-color-dark-6)',
          'var(--mantine-color-dark-4)',
          'var(--mantine-color-gray-6)',
          'var(--mantine-color-gray-4)',
        ]
      : [
          'var(--mantine-color-gray-2)',
          'var(--mantine-color-gray-4)',
          'var(--mantine-color-gray-6)',
          'var(--mantine-color-gray-8)',
        ];
  const cpuHistory = useMemo(() => overview?.cpu.history ?? [], [overview]);
  const cpuSparklineColor = computedColorScheme === 'dark' ? 'gray.3' : 'gray.7';
  const heatmapLegendRanges = useMemo(
    () =>
      processedHeatmapPeak <= 0
        ? buildLinearHeatmapLegendRanges(0, heatmapColors.length)
        : buildSqrtHeatmapLegendRanges(processedHeatmapPeak, heatmapColors.length),
    [processedHeatmapPeak, heatmapColors.length]
  );

  useEffect(() => {
    animatedCpuChartDataRef.current = animatedCpuChartData;
  }, [animatedCpuChartData]);

  useEffect(() => {
    if (cpuHistory.length === 0) {
      setAnimatedCpuChartData([]);
      previousCpuHistoryRef.current = [];
      nextCpuSampleIdRef.current = 0;
      return;
    }

    const previousHistory = previousCpuHistoryRef.current;
    const currentAnimated = animatedCpuChartDataRef.current;

    const animateLatestPoint = (
      baseSeries: CpuChartPoint[],
      startValue: number,
      endValue: number
    ) => {
      if (baseSeries.length === 0 || startValue === endValue) {
        setAnimatedCpuChartData(baseSeries);
        return undefined;
      }

      const start = performance.now();
      let frame = 0;

      const animate = (now: number) => {
        const progress = Math.min((now - start) / CPU_TRANSITION_DURATION_MS, 1);
        const eased = 1 - (1 - progress) * (1 - progress);
        const nextValue = startValue + (endValue - startValue) * eased;

        setAnimatedCpuChartData([
          ...baseSeries.slice(0, -1),
          { ...baseSeries[baseSeries.length - 1], cpu: nextValue },
        ]);

        if (progress < 1) {
          frame = window.requestAnimationFrame(animate);
        }
      };

      frame = window.requestAnimationFrame(animate);
      return () => {
        window.cancelAnimationFrame(frame);
      };
    };

    if (previousHistory.length === 0 || currentAnimated.length === 0) {
      const initialSeries = cpuHistory.map((value) => ({
        sample: nextCpuSampleIdRef.current++,
        cpu: value,
      }));
      setAnimatedCpuChartData(initialSeries);
      previousCpuHistoryRef.current = [...cpuHistory];
      return;
    }

    const appendedSample =
      cpuHistory.length === previousHistory.length + 1 &&
      previousHistory.every((value, index) => value === cpuHistory[index]);

    if (appendedSample) {
      const latestValue = cpuHistory[cpuHistory.length - 1];
      const startValue = previousHistory[previousHistory.length - 1] ?? latestValue;
      const nextSeries = [
        ...currentAnimated,
        {
          sample: nextCpuSampleIdRef.current++,
          cpu: startValue,
        },
      ];

      previousCpuHistoryRef.current = [...cpuHistory];
      return animateLatestPoint(nextSeries, startValue, latestValue);
    }

    const shiftedWindow =
      cpuHistory.length === previousHistory.length &&
      previousHistory.slice(1).every((value, index) => value === cpuHistory[index]);

    if (shiftedWindow && currentAnimated.length > 1) {
      const latestValue = cpuHistory[cpuHistory.length - 1];
      const startValue = currentAnimated[currentAnimated.length - 1]?.cpu ?? latestValue;
      const nextSeries = [
        ...currentAnimated.slice(1),
        {
          sample: nextCpuSampleIdRef.current++,
          cpu: startValue,
        },
      ];

      previousCpuHistoryRef.current = [...cpuHistory];
      return animateLatestPoint(nextSeries, startValue, latestValue);
    }

    const unchanged =
      cpuHistory.length === previousHistory.length &&
      previousHistory.every((value, index) => value === cpuHistory[index]);

    if (unchanged) {
      return;
    }

    const resetSeries = cpuHistory.map((value) => ({
      sample: nextCpuSampleIdRef.current++,
      cpu: value,
    }));
    setAnimatedCpuChartData(resetSeries);
    previousCpuHistoryRef.current = [...cpuHistory];
  }, [cpuHistory]);

  usePolling(
    true,
    async (isMounted) => {
      try {
        setOverviewRefreshing(true);
        const jobsPromise = canFetchProtected
          ? fetchJobs({ limit: 500 }, mode)
          : Promise.resolve({ items: [], count: 0, total: 0, limit: 500 });
        const [nextOverview, nextJobs] = await Promise.all([fetchOverview(mode), jobsPromise]);
        if (!isMounted()) return;

        setOverview(nextOverview);
        setOverviewJobs(nextJobs.items);
        setOverviewError(null);
      } catch (error) {
        if (!isMounted()) return;
        setOverviewError(error instanceof Error ? error.message : 'Unknown request failure');
      } finally {
        if (isMounted()) {
          setOverviewRefreshing(false);
        }
      }
    },
    [canFetchProtected, mode]
  );

  useEffect(() => {
    const viewport = heatmapScrollRef.current;
    if (!viewport) {
      return;
    }

    const frame = window.requestAnimationFrame(() => {
      viewport.scrollLeft = Math.max(0, viewport.scrollWidth - viewport.clientWidth);
    });

    return () => {
      window.cancelAnimationFrame(frame);
    };
  }, [heatmapViewportWidth, processedHeatmapRange.startDate, processedHeatmapRange.endDate]);

  return (
    <Stack gap="md" style={{ flex: 1, minHeight: 0 }}>
      <Stack gap="md">
        <Group justify="flex-end">
          <SegmentedControl
            value={timeRange}
            onChange={(value) => setTimeRange(value as OverviewTimeRange)}
            data={[
              { value: '1h', label: '1h' },
              { value: '12h', label: '12h' },
              { value: '1d', label: '1d' },
              { value: '7d', label: '7d' },
            ]}
            size="xs"
          />
        </Group>

        {overviewError && (
          <Alert color="red" title={t('overview.refreshFailed')}>
            {overviewError}
          </Alert>
        )}

        <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="md">
          <StatCard
            title={t('overview.processed')}
            icon={<IconChecks size={16} stroke={1.8} />}
            value={String(processedInRange)}
            valueLabel={t('overview.total')}
            subtitle={processedChartDescription}
            sparklineData={processedSparkline}
            sparklineColor={sparklineColor}
            sparkBucketMimeCounts={processedGroupByBucket}
          />

          <StatCard
            title={t('overview.failed')}
            icon={<IconAlertTriangle size={16} stroke={1.8} />}
            value={String(failedInRange)}
            subtitle={processedChartDescription}
            sparklineData={getTimeBucketSums(
              overviewJobs.filter((j) => j.status === 'error'),
              timeRange,
              () => 1
            )}
            sparklineColor={sparklineColor}
          />

          <StatCard
            title={t('overview.metricDuration')}
            icon={<IconClock size={16} stroke={1.8} />}
            value={`${avgDurationInRange.toFixed(1)}s`}
            subtitle={avgMetricSubtitle}
            sparklineData={getTimeBucketAverages(
              overviewJobs,
              timeRange,
              (j) => j.duration_seconds
            )}
            sparklineColor={sparklineColor}
          />

          {mode === 'txt' && (
            <StatCard
              title={t('overview.metricTokens')}
              icon={<IconTypography size={16} stroke={1.8} />}
              value={Math.round(avgTokensInRange).toLocaleString()}
              subtitle={avgMetricSubtitle}
              sparklineData={avgTokensSparkline}
              sparklineColor={sparklineColor}
              sparkTooltipFormat={(v) =>
                typeof v === 'number' && Number.isFinite(v) ? Math.round(v).toLocaleString() : ''
              }
            />
          )}

          {mode === 'txt' && (
            <StatCard
              title={t('overview.metricChunks')}
              icon={<IconStack2 size={16} stroke={1.8} />}
              value={avgChunksInRange.toFixed(1)}
              subtitle={avgMetricSubtitle}
              sparklineData={getTimeBucketAverages(overviewJobs, timeRange, (j) => j.chunk_count)}
              sparklineColor={sparklineColor}
            />
          )}

          {mode === 'txt' && (
            <StatCard
              title={t('overview.metricFileSize')}
              icon={<IconFileDescription size={16} stroke={1.8} />}
              value={
                avgFileSizeInRange == null ? '0' : formatFileSize(Math.round(avgFileSizeInRange))
              }
              subtitle={avgMetricSubtitle}
              sparklineData={avgFileSizeSparkline}
              sparklineColor={sparklineColor}
              sparkTooltipFormat={(v) =>
                typeof v === 'number' && Number.isFinite(v) ? formatFileSize(Math.round(v)) : ''
              }
            />
          )}
        </SimpleGrid>

        <Stack gap="xs">
          <Paper withBorder radius="md" p="lg">
            <div
              ref={(node) => {
                heatmapViewportRef(node);
                heatmapScrollRef.current = node;
              }}
              className="heatmapScroll"
              style={{ width: '100%', overflowX: 'auto', overflowY: 'hidden' }}
            >
              <Box
                style={{
                  width: 'max-content',
                  minWidth: '100%',
                  paddingRight: HEATMAP_VIEWPORT_PADDING_RIGHT,
                  boxSizing: 'border-box',
                }}
              >
                <Box
                  style={{
                    display: 'grid',
                    gridTemplateColumns: `${HEATMAP_WEEKDAY_LABELS_WIDTH}px ${heatmapGridWidth}px`,
                    gridTemplateRows: `${HEATMAP_MONTH_LABELS_HEIGHT}px auto`,
                    columnGap: 0,
                    rowGap: HEATMAP_GAP,
                    minWidth: `calc(${HEATMAP_WEEKDAY_LABELS_WIDTH}px + ${heatmapGridWidth}px)`,
                  }}
                >
                  <Box />
                  <Box style={{ position: 'relative', width: heatmapGridWidth }}>
                    {heatmapCalendar.monthLabels.map(({ date, weekIndex }) => (
                      <Text
                        key={date}
                        size="sm"
                        c="dimmed"
                        style={{
                          position: 'absolute',
                          left: weekIndex * (HEATMAP_RECT_SIZE + HEATMAP_GAP),
                          top: 0,
                          whiteSpace: 'nowrap',
                          lineHeight: `${HEATMAP_MONTH_LABELS_HEIGHT}px`,
                          userSelect: 'none',
                        }}
                      >
                        {formatHeatmapMonthLabel(
                          date,
                          i18n.resolvedLanguage || i18n.language || 'en'
                        )}
                      </Text>
                    ))}
                  </Box>
                  <Stack
                    gap={HEATMAP_GAP}
                    justify="space-between"
                    style={{
                      paddingTop: 1,
                      width: HEATMAP_WEEKDAY_LABELS_WIDTH,
                    }}
                  >
                    {HEATMAP_WEEKDAY_LABELS.map((label, index) => (
                      <Text
                        key={`${label}-${index}`}
                        size="sm"
                        c="dimmed"
                        style={{
                          height: HEATMAP_RECT_SIZE,
                          lineHeight: `${HEATMAP_RECT_SIZE}px`,
                          userSelect: 'none',
                        }}
                      >
                        {label}
                      </Text>
                    ))}
                  </Stack>
                  <Box
                    style={{
                      display: 'grid',
                      gridTemplateColumns: `repeat(${visibleHeatmapWeeks}, ${HEATMAP_RECT_SIZE}px)`,
                      gridTemplateRows: `repeat(7, ${HEATMAP_RECT_SIZE}px)`,
                      columnGap: HEATMAP_GAP,
                      rowGap: HEATMAP_GAP,
                      width: heatmapGridWidth,
                    }}
                  >
                    {heatmapCalendar.weeks.flatMap((week, weekIndex) =>
                      week.map((cell, dayIndex) => {
                        const colorIndex = getHeatmapColorIndex(
                          cell.value,
                          processedHeatmapPeak,
                          heatmapColors.length
                        );
                        const backgroundColor =
                          cell.date == null
                            ? 'transparent'
                            : (heatmapColors[colorIndex] ?? heatmapColors[0]);

                        return cell.date ? (
                          <Tooltip
                            key={cell.date}
                            label={formatProcessedHeatmapTooltip(cell.date, cell.value ?? 0)}
                            transitionProps={{ duration: 0 }}
                          >
                            <Box
                              aria-label={formatProcessedHeatmapTooltip(cell.date, cell.value ?? 0)}
                              style={{
                                gridColumn: weekIndex + 1,
                                gridRow: dayIndex + 1,
                                width: HEATMAP_RECT_SIZE,
                                height: HEATMAP_RECT_SIZE,
                                borderRadius: HEATMAP_RECT_RADIUS,
                                backgroundColor,
                                border:
                                  computedColorScheme === 'dark'
                                    ? '1px solid var(--mantine-color-dark-4)'
                                    : '1px solid var(--mantine-color-gray-2)',
                                boxSizing: 'border-box',
                              }}
                            />
                          </Tooltip>
                        ) : (
                          <Box
                            key={`empty-${weekIndex}-${dayIndex}`}
                            aria-hidden="true"
                            style={{
                              gridColumn: weekIndex + 1,
                              gridRow: dayIndex + 1,
                              width: HEATMAP_RECT_SIZE,
                              height: HEATMAP_RECT_SIZE,
                              borderRadius: HEATMAP_RECT_RADIUS,
                              backgroundColor: 'transparent',
                            }}
                          />
                        );
                      })
                    )}
                  </Box>
                </Box>
                <Group
                  gap={HEATMAP_GAP}
                  justify="flex-end"
                  wrap="nowrap"
                  style={{
                    width: '100%',
                    paddingTop: 'var(--mantine-spacing-md)',
                    paddingRight: heatmapLegendOffset,
                  }}
                >
                  {heatmapColors.map((color, index) => {
                    const range = heatmapLegendRanges[index];
                    const primaryLabel =
                      range.min === range.max
                        ? t('overview.heatmapLegend', { count: range.min })
                        : t('overview.heatmapLegendRange', {
                            min: range.min,
                            max: range.max,
                          });
                    const showScaleHint = processedHeatmapPeak > 0;
                    const tooltipLabel = showScaleHint ? (
                      <Stack gap={4}>
                        <Text size="xs">{primaryLabel}</Text>
                        <Text size="xs" c="dimmed">
                          {t('overview.heatmapLegendScaleHint')}
                        </Text>
                      </Stack>
                    ) : (
                      primaryLabel
                    );
                    const ariaLabel = showScaleHint
                      ? `${primaryLabel} ${t('overview.heatmapLegendScaleHint')}`
                      : primaryLabel;

                    return (
                      <Tooltip key={index} label={tooltipLabel} transitionProps={{ duration: 0 }}>
                        <Box
                          aria-label={ariaLabel}
                          style={{
                            width: HEATMAP_RECT_SIZE,
                            height: HEATMAP_RECT_SIZE,
                            borderRadius: HEATMAP_RECT_RADIUS,
                            backgroundColor: color,
                            border:
                              computedColorScheme === 'dark'
                                ? '1px solid var(--mantine-color-dark-4)'
                                : '1px solid var(--mantine-color-gray-3)',
                            flexShrink: 0,
                            cursor: 'help',
                          }}
                        />
                      </Tooltip>
                    );
                  })}
                </Group>
              </Box>
            </div>
          </Paper>
          <ServerUptime uptimeSeconds={overview?.health.uptime_seconds} />
        </Stack>
      </Stack>

      <Box style={{ flex: 1 }} />

      <Paper
        radius={0}
        p={0}
        bg="transparent"
        style={{ marginInline: 'calc(var(--mantine-spacing-md) * -1)' }}
      >
        <Stack gap="xs">
          <AreaChart
            miw={0}
            w="100%"
            h={88}
            data={animatedCpuChartData}
            dataKey="sample"
            curveType="monotone"
            withGradient
            withXAxis={false}
            withYAxis={false}
            withDots={false}
            gridAxis="none"
            series={[{ name: 'cpu', color: cpuSparklineColor }]}
            tooltipProps={{
              content: renderCpuTooltip,
            }}
          />
        </Stack>
      </Paper>
    </Stack>
  );
}
