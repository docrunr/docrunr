import { AreaChart } from '@mantine/charts';
import { Paper, Stack, Text, useComputedColorScheme } from '@mantine/core';
import { useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import type { TooltipContentProps } from 'recharts';
import type { AnyJob, WorkerMode } from '../../../services/workerApi.types';
import { getTimeBucketSums } from '../../processing/lib/metric-series';

type QueueThroughputChartProps = {
  jobs: AnyJob[];
  mode: WorkerMode;
};

export function QueueThroughputChart({ jobs, mode }: QueueThroughputChartProps) {
  const { t } = useTranslation();
  const computedColorScheme = useComputedColorScheme('light');
  const sparklineColor = computedColorScheme === 'dark' ? 'gray.3' : 'gray.7';
  const tooltipKey = mode === 'llm' ? 'tooltip.embedded' : 'tooltip.processed';

  const renderProcessedTooltip = useCallback(
    ({ active, payload }: TooltipContentProps<number, string>) => {
      if (!active || !payload?.length) {
        return null;
      }
      const raw = payload[0]?.value;
      const count = typeof raw === 'number' && Number.isFinite(raw) ? Math.round(raw) : 0;
      return (
        <Paper withBorder shadow="md" p="xs" radius="md">
          <Text size="sm" fw={700}>
            {t(tooltipKey, { count })}
          </Text>
        </Paper>
      );
    },
    [t, tooltipKey]
  );

  const sparkline = useMemo(() => getTimeBucketSums(jobs, '7d', () => 1), [jobs]);

  const chartData = useMemo(() => sparkline.map((v, i) => ({ i, processed: v })), [sparkline]);

  return (
    <Paper
      radius={0}
      p={0}
      bg="transparent"
      style={{ marginInline: 'calc(var(--mantine-spacing-md) * -1)', flexShrink: 0 }}
    >
      <Stack gap="xs">
        <AreaChart
          miw={0}
          w="100%"
          h={88}
          data={chartData}
          dataKey="i"
          curveType="monotone"
          withGradient
          withXAxis={false}
          withYAxis={false}
          withDots={false}
          gridAxis="none"
          series={[{ name: 'processed', color: sparklineColor }]}
          tooltipProps={{
            content: renderProcessedTooltip,
          }}
        />
      </Stack>
    </Paper>
  );
}
