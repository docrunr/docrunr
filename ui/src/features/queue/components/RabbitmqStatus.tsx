import { ActionIcon, Group, Text, Tooltip } from '@mantine/core';
import { IconPlugConnected, IconPlugConnectedX } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';

type RabbitmqStatusProps = {
  rabbitmq: string | null;
};

export function RabbitmqStatus({ rabbitmq }: RabbitmqStatusProps) {
  const { t } = useTranslation();

  if (rabbitmq == null) {
    return null;
  }

  const connected = rabbitmq === 'connected';
  const Icon = connected ? IconPlugConnected : IconPlugConnectedX;
  const color = connected ? 'teal' : 'red';
  const shortLabel = connected
    ? t('queue.rabbitmqShortConnected')
    : t('queue.rabbitmqShortDisconnected');
  const tooltipLabel = connected
    ? t('queue.rabbitmqTooltipConnected')
    : t('queue.rabbitmqTooltipDisconnected');

  return (
    <Group gap={6} align="center" wrap="nowrap" style={{ flexShrink: 0 }}>
      <Tooltip label={tooltipLabel} multiline maw={280} transitionProps={{ duration: 0 }}>
        <ActionIcon
          variant="subtle"
          color={color}
          size="sm"
          radius="xl"
          aria-label={t('queue.rabbitmqAria', { status: shortLabel })}
        >
          <Icon size={16} stroke={1.8} />
        </ActionIcon>
      </Tooltip>
      <Text size="sm" c="dimmed" lh={1.2} style={{ whiteSpace: 'nowrap' }}>
        {shortLabel}
      </Text>
    </Group>
  );
}
