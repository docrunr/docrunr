import { ActionIcon, Box, Group, Text, Tooltip } from '@mantine/core';
import { IconClock } from '@tabler/icons-react';
import type { TFunction } from 'i18next';
import { useTranslation } from 'react-i18next';

type ServerUptimeProps = {
  uptimeSeconds: number | null | undefined;
};

type UptimeUnit = 'day' | 'hour' | 'minute' | 'second';

function decomposeUptime(totalSeconds: number): { d: number; h: number; m: number; s: number } {
  const secs = Math.max(0, Math.floor(totalSeconds));
  let r = secs;
  const d = Math.floor(r / 86400);
  r -= d * 86400;
  const h = Math.floor(r / 3600);
  r -= h * 3600;
  const m = Math.floor(r / 60);
  const s = r - m * 60;
  return { d, h, m, s };
}

function formatHumanUptime(t: TFunction, totalSeconds: number): string {
  const { d, h, m, s } = decomposeUptime(totalSeconds);

  const rows: Array<{ unit: UptimeUnit; count: number }> = [];
  if (d > 0) rows.push({ unit: 'day', count: d });
  if (h > 0) rows.push({ unit: 'hour', count: h });
  if (m > 0) rows.push({ unit: 'minute', count: m });
  if (rows.length === 0) {
    rows.push({ unit: 'second', count: s });
  } else if (s > 0) {
    rows.push({ unit: 'second', count: s });
  }

  const keyPrefix = 'overview.serverUptime';
  const chunks = rows.map(({ unit, count }) =>
    t(`${keyPrefix}${unit.charAt(0).toUpperCase() + unit.slice(1)}`, { count })
  );

  return chunks.slice(0, 2).join(' ');
}

function formatUptimeSecondsPlain(value: number): string {
  return String(Math.max(0, Math.floor(value)));
}

export function ServerUptime({ uptimeSeconds }: ServerUptimeProps) {
  const { t } = useTranslation();

  if (uptimeSeconds == null || !Number.isFinite(uptimeSeconds)) {
    return null;
  }

  const secondsStr = formatUptimeSecondsPlain(uptimeSeconds);
  const human = formatHumanUptime(t, uptimeSeconds);

  return (
    <Box style={{ width: '100%', display: 'flex', justifyContent: 'center' }}>
      <Group gap={6} align="center" wrap="nowrap">
        <Tooltip
          label={t('overview.serverUptimeTooltip', {
            human,
            seconds: secondsStr,
          })}
          multiline
          maw={280}
          transitionProps={{ duration: 0 }}
        >
          <ActionIcon
            variant="subtle"
            color="gray"
            size="sm"
            radius="xl"
            aria-label={t('overview.serverUptimeLabel')}
          >
            <IconClock size={16} stroke={1.8} />
          </ActionIcon>
        </Tooltip>
        <Text size="sm" c="dimmed" lh={1.2}>
          {human}
        </Text>
      </Group>
    </Box>
  );
}
