import { useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Box,
  Divider,
  Group,
  Paper,
  Stack,
  Text,
  Title,
  useComputedColorScheme,
  useMantineTheme,
} from '@mantine/core';
import { useElementSize } from '@mantine/hooks';
import { AreaChart } from '@mantine/charts';
import type { TooltipContentProps } from 'recharts';
import { FileTypeIcon } from '../../../components/icons/FileTypeIcon';
import { mergeMimeCountsByExtension } from '../../../utils/mime-types';

const MIME_ROWS_MAX = 8;
function formatSparkBucketValue(v: unknown): string {
  if (typeof v === 'number' && Number.isFinite(v)) {
    return Number.isInteger(v) ? v.toLocaleString() : v.toFixed(1);
  }
  return v == null ? '' : String(v);
}

type StatCardProps = {
  /** Card title (e.g. "Processed") */
  title: string;
  /** Icon node shown before the title */
  icon?: React.ReactNode;
  /** Large displayed value */
  value: string;
  /** Small subtitle under the title (e.g. "Last 7 days") */
  subtitle?: string;
  /** Auxiliary label after the value (e.g. "total") */
  valueLabel?: string;
  /** Optional info top-right */
  topRight?: string;
  /** Sparkline data points */
  sparklineData: number[];
  /** Mantine color for the area chart @default "gray.5" */
  sparklineColor?: string;
  /** Override default sparkline tooltip number formatting */
  sparkTooltipFormat?: (value: unknown) => string;
  /** Per-bucket MIME counts (same length/order as sparklineData); shown under the total in the tooltip */
  sparkBucketMimeCounts?: Record<string, number>[];
};

export function StatCard({
  title,
  icon,
  value,
  subtitle,
  valueLabel,
  topRight,
  sparklineData,
  sparklineColor = 'gray.5',
  sparkTooltipFormat,
  sparkBucketMimeCounts,
}: StatCardProps) {
  const { t } = useTranslation();
  const theme = useMantineTheme();
  const colorScheme = useComputedColorScheme('light');
  const { ref: sparklineContainerRef, width: sparklineContainerWidth } =
    useElementSize<HTMLDivElement>();
  const tooltipSurface = colorScheme === 'dark' ? theme.colors.dark[7] : theme.white;
  const tooltipBorderColor = colorScheme === 'dark' ? theme.colors.dark[4] : theme.colors.gray[3];

  const chartData = useMemo(
    () => sparklineData.map((v, idx) => ({ i: idx, value: v })),
    [sparklineData]
  );

  const chartSeries = useMemo(
    () => [{ name: 'value' as const, label: title, color: sparklineColor }],
    [title, sparklineColor]
  );

  const sparkTooltipContent = useCallback(
    ({ active, payload }: TooltipContentProps) => {
      if (!active || !payload?.length) return null;
      const row = payload.find((p) => p.name === 'value') ?? payload[0];
      const raw = row?.value;
      if (raw == null) return null;
      const format = sparkTooltipFormat ?? formatSparkBucketValue;
      const datum = row.payload as { i?: number } | undefined;
      const bucketIdx = typeof datum?.i === 'number' ? datum.i : -1;
      const mimeMap =
        sparkBucketMimeCounts && bucketIdx >= 0 ? sparkBucketMimeCounts[bucketIdx] : undefined;
      const mimeMerged = mimeMap ? mergeMimeCountsByExtension(mimeMap) : [];
      const mimeExtra = mimeMerged.length > MIME_ROWS_MAX ? mimeMerged.length - MIME_ROWS_MAX : 0;
      const mimeRows = mimeMerged.slice(0, MIME_ROWS_MAX);

      return (
        <Paper
          shadow="md"
          p="sm"
          radius="md"
          withBorder
          maw={220}
          styles={{
            root: {
              backgroundColor: tooltipSurface,
              borderColor: tooltipBorderColor,
              boxShadow: theme.shadows.md,
              position: 'relative',
              zIndex: 2,
              isolation: 'isolate',
            },
          }}
        >
          <Stack gap={0}>
            <Text fw={700} size="sm" lh={1.2}>
              {format(raw)}
            </Text>
            {mimeRows.length > 0 && (
              <>
                <Divider my={8} />
                <Stack gap={6}>
                  {mimeRows.map(({ ext, count }) => (
                    <Group key={ext} gap={8} wrap="nowrap" align="center">
                      <span
                        style={{
                          flexShrink: 0,
                          display: 'flex',
                          alignItems: 'center',
                          color: 'var(--mantine-color-dimmed)',
                        }}
                      >
                        <FileTypeIcon extension={ext} />
                      </span>
                      <Text size="xs" fw={500} tt="lowercase" style={{ flex: 1, minWidth: 0 }}>
                        {ext}
                      </Text>
                      <Text size="xs" fw={600} c="dimmed" style={{ flexShrink: 0 }}>
                        {count}
                      </Text>
                    </Group>
                  ))}
                  {mimeExtra > 0 && (
                    <Text size="xs" c="dimmed" pl={23}>
                      {t('metric.more', { count: mimeExtra })}
                    </Text>
                  )}
                </Stack>
              </>
            )}
          </Stack>
        </Paper>
      );
    },
    [
      sparkTooltipFormat,
      sparkBucketMimeCounts,
      tooltipSurface,
      tooltipBorderColor,
      theme.shadows.md,
      t,
    ]
  );

  return (
    <Paper withBorder radius="md" p="lg">
      <Stack gap={6}>
        {/* Header row */}
        <Group justify="space-between" align="center">
          <Group gap={8} align="center">
            {icon && (
              <span style={{ fontSize: 16, lineHeight: 1, display: 'flex', alignItems: 'center' }}>
                {icon}
              </span>
            )}
            <Text fw={500} size="sm" c="dimmed">
              {title}
            </Text>
          </Group>
          {topRight && (
            <Text size="xs" c="dimmed">
              {topRight}
            </Text>
          )}
        </Group>

        {/* Subtitle */}
        {subtitle && (
          <Text size="xs" c="dimmed" mt={-2}>
            {subtitle}
          </Text>
        )}

        {/* Value + chart row */}
        <Group justify="space-between" align="flex-end" mt={4} wrap="nowrap">
          <Group gap={8} align="baseline">
            <Title order={2}>{value}</Title>
            {valueLabel && (
              <Text size="sm" c="dimmed" fw={500}>
                {valueLabel}
              </Text>
            )}
          </Group>
          <div
            ref={sparklineContainerRef}
            style={{
              width: '45%',
              maxWidth: 200,
              minWidth: 0,
              height: 48,
              overflow: 'visible',
            }}
          >
            {sparklineContainerWidth > 0 ? (
              <AreaChart
                miw={0}
                w="100%"
                h={48}
                data={chartData}
                dataKey="i"
                curveType="monotone"
                withGradient
                withXAxis={false}
                withYAxis={false}
                withDots={false}
                gridAxis="none"
                tooltipProps={{
                  position: { y: 60 },
                  wrapperStyle: { zIndex: 10000 },
                  // SVG cursor is painted after the tooltip in DOM order; hide it when the tooltip is tall (MIME list).
                  ...(sparkBucketMimeCounts ? { cursor: false } : {}),
                  content: sparkTooltipContent,
                }}
                series={chartSeries}
              />
            ) : (
              <Box h={48} w="100%" aria-hidden />
            )}
          </div>
        </Group>
      </Stack>
    </Paper>
  );
}
