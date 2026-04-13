import { ActionIcon, Group, Modal, Stack, Text } from '@mantine/core';
import { IconBrandGithub, IconBrandX } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { APP_VERSION } from '../../../app/version';
import { DocRunrLogo } from '../../../components/brand/DocRunrLogo';

const SOCIAL_ICON_PROPS = { size: 22, stroke: 1.5 } as const;

type AboutModalProps = {
  opened: boolean;
  onClose: () => void;
};

export function AboutModal({ opened, onClose }: AboutModalProps) {
  const { t } = useTranslation();

  return (
    <Modal opened={opened} onClose={onClose} size="md" transitionProps={{ duration: 0 }}>
      <Stack align="center" justify="center" gap="md" py="xs" px="md">
        <DocRunrLogo
          role="img"
          aria-label={t('about.logoAria')}
          style={{
            width: 56,
            height: 56,
            color: 'var(--mantine-color-gray-light-color)',
          }}
        />
        <Text c="dimmed" ta="center" size="sm" maw={280}>
          {t('about.description')}
        </Text>
        <Text c="dimmed" size="xs">
          {t('about.version', { version: APP_VERSION })}
        </Text>
        <Group gap="xs" justify="center">
          <ActionIcon
            component="a"
            href="https://github.com/docrunr/docrunr"
            target="_blank"
            rel="noopener noreferrer"
            variant="subtle"
            color="gray"
            size="lg"
            aria-label={t('about.githubLink')}
          >
            <IconBrandGithub {...SOCIAL_ICON_PROPS} />
          </ActionIcon>
          <ActionIcon
            component="a"
            href="https://x.com/docrunr"
            target="_blank"
            rel="noopener noreferrer"
            variant="subtle"
            color="gray"
            size="lg"
            aria-label={t('about.xLink')}
          >
            <IconBrandX {...SOCIAL_ICON_PROPS} />
          </ActionIcon>
        </Group>
      </Stack>
    </Modal>
  );
}
