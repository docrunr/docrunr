import { Group, Paper, Stack, Text, ThemeIcon } from '@mantine/core';
import {
  IconCheck,
  IconCpu,
  IconDatabase,
  IconPlugConnected,
  IconX,
} from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import type { LlmWorkerOverview } from '../../../services/workerLlmApi.types';
import { formatDurationSeconds } from '../../../utils/duration';

function StatCard({
  label,
  value,
  icon,
  color = 'blue',
}: {
  label: string;
  value: string | number;
  icon: React.ReactNode;
  color?: string;
}) {
  return (
    <Paper shadow="xs" p="md" radius="md" withBorder style={{ flex: '1 1 180px', minWidth: 160 }}>
      <Group gap="sm" wrap="nowrap">
        <ThemeIcon size="lg" radius="md" variant="light" color={color}>
          {icon}
        </ThemeIcon>
        <Stack gap={2}>
          <Text size="xs" c="dimmed" tt="uppercase" fw={600}>
            {label}
          </Text>
          <Text size="lg" fw={700} lh={1.2}>
            {value}
          </Text>
        </Stack>
      </Group>
    </Paper>
  );
}

type LlmOverviewProps = {
  overview: LlmWorkerOverview | null;
  loading: boolean;
};

export function LlmOverview({ overview, loading }: LlmOverviewProps) {
  const { t } = useTranslation();

  if (!overview && loading) {
    return (
      <Text c="dimmed" ta="center">
        {t('llm.loadingOverview')}
      </Text>
    );
  }

  if (!overview) {
    return (
      <Text c="dimmed" ta="center">
        {t('llm.unavailable')}
      </Text>
    );
  }

  const { health, stats, cpu } = overview;
  const rabbitmqOk = health.rabbitmq === 'connected';
  const avgDuration = stats.avg_duration_seconds
    ? formatDurationSeconds(stats.avg_duration_seconds)
    : '—';
  const cpuPct = cpu.percent !== null ? `${cpu.percent}%` : '—';

  return (
    <Group gap="md" wrap="wrap">
      <StatCard
        label={t('llm.processed')}
        value={stats.processed.toLocaleString()}
        icon={<IconCheck size={18} />}
        color="teal"
      />
      <StatCard
        label={t('llm.failed')}
        value={stats.failed.toLocaleString()}
        icon={<IconX size={18} />}
        color="red"
      />
      <StatCard
        label={t('llm.avgDuration')}
        value={avgDuration}
        icon={<IconDatabase size={18} />}
        color="blue"
      />
      <StatCard
        label={t('llm.rabbitmq')}
        value={rabbitmqOk ? t('llm.connected') : t('llm.disconnected')}
        icon={<IconPlugConnected size={18} />}
        color={rabbitmqOk ? 'teal' : 'red'}
      />
      <StatCard
        label={t('llm.cpu')}
        value={cpuPct}
        icon={<IconCpu size={18} />}
        color="grape"
      />
    </Group>
  );
}
