import {
  ActionIcon,
  Alert,
  Box,
  Group,
  Menu,
  SegmentedControl,
  Stack,
  Text,
  TextInput,
  Tooltip,
} from '@mantine/core';
import {
  IconAlertTriangle,
  IconChevronDown,
  IconList,
  IconLoader2,
  IconLogout,
  IconMoon,
  IconSun,
  IconUpload,
} from '@tabler/icons-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { LangFlag } from '../components/flags/LangFlag';
import { LANG_STORAGE_KEY, SUPPORTED_LANGS, type UiLanguage } from '../i18n';
import { ProcessingOverview } from '../features/overview/components/ProcessingOverview';
import { QueueJobsTable } from '../features/queue/components/QueueJobsTable';
import { RabbitmqStatus } from '../features/queue/components/RabbitmqStatus';
import { QueueThroughputChart } from '../features/queue/components/QueueThroughputChart';
import { UploadModal } from '../features/uploads/components/UploadModal';
import type { WorkerJobsResponse } from '../services/workerApi.types';
import { SidebarToggleIcon } from './sidebar-toggle-icon';
import { useWorkerAuth } from './useWorkerAuth';

type AppMainToolbarProps = {
  sidebarOpened: boolean;
  onToggleSidebar: () => void;
  isDarkScheme: boolean;
  onToggleColorScheme: () => void;
};

export function AppMainToolbar({
  sidebarOpened,
  onToggleSidebar,
  isDarkScheme,
  onToggleColorScheme,
}: AppMainToolbarProps) {
  const { t, i18n } = useTranslation();
  const { canFetchProtected, authEnabled, authenticated, logout } = useWorkerAuth();
  const [uploadOpened, setUploadOpened] = useState(false);
  const sidebarLabel = sidebarOpened ? t('sidebar.hide') : t('sidebar.show');
  const themeLabel = isDarkScheme ? t('theme.switchToLight') : t('theme.switchToDark');
  const resolved = (i18n.resolvedLanguage ?? i18n.language).split('-')[0]?.toLowerCase() ?? 'en';
  const currentLang: UiLanguage = resolved === 'nl' ? 'nl' : 'en';
  const uploadBlocked = !canFetchProtected;

  const applyLanguage = (lang: UiLanguage) => {
    try {
      window.localStorage.setItem(LANG_STORAGE_KEY, lang);
    } catch {
      // ignore
    }
    void i18n.changeLanguage(lang);
  };

  return (
    <Group justify="space-between" align="center">
      <Tooltip label={sidebarLabel} position="right" transitionProps={{ duration: 0 }}>
        <ActionIcon
          visibleFrom="sm"
          variant="subtle"
          color="gray"
          size="lg"
          radius="md"
          aria-label={sidebarLabel}
          onClick={onToggleSidebar}
        >
          <SidebarToggleIcon opened={sidebarOpened} />
        </ActionIcon>
      </Tooltip>
      <Group gap={6} wrap="nowrap" align="center">
        <Tooltip
          label={uploadBlocked ? t('auth.uploadRequiresLogin') : t('upload.title')}
          position="left"
          transitionProps={{ duration: 0 }}
        >
          <ActionIcon
            variant="subtle"
            color="gray"
            size="lg"
            radius="md"
            aria-label={t('upload.title')}
            disabled={uploadBlocked}
            onClick={() => {
              if (!uploadBlocked) {
                setUploadOpened(true);
              }
            }}
          >
            <IconUpload size={18} stroke={1.8} />
          </ActionIcon>
        </Tooltip>
        <UploadModal opened={uploadOpened} onClose={() => setUploadOpened(false)} />
        {authEnabled && authenticated ? (
          <Tooltip label={t('auth.signOut')} position="left" transitionProps={{ duration: 0 }}>
            <ActionIcon
              variant="subtle"
              color="gray"
              size="lg"
              radius="md"
              aria-label={t('auth.signOut')}
              onClick={() => void logout()}
            >
              <IconLogout size={18} stroke={1.8} />
            </ActionIcon>
          </Tooltip>
        ) : null}
        <Menu position="bottom-start" transitionProps={{ duration: 0 }} withinPortal>
          <Menu.Target>
            <Tooltip
              label={t('language.ariaLabel')}
              position="left"
              transitionProps={{ duration: 0 }}
            >
              <ActionIcon
                variant="subtle"
                color="gray"
                size="lg"
                radius="md"
                aria-label={t('language.ariaLabel')}
                aria-haspopup="menu"
                styles={{
                  root: {
                    width: 'auto',
                    paddingInline: 12,
                  },
                }}
              >
                <Group gap={6} wrap="nowrap" align="center">
                  <LangFlag code={currentLang} height={14} />
                  <IconChevronDown size={12} stroke={1.6} color="var(--mantine-color-dimmed)" />
                </Group>
              </ActionIcon>
            </Tooltip>
          </Menu.Target>
          <Menu.Dropdown
            p="sm"
            styles={{
              dropdown: {
                minWidth: 180,
              },
            }}
          >
            {SUPPORTED_LANGS.map((code) => (
              <Menu.Item key={code} px="sm" py={8} onClick={() => applyLanguage(code)}>
                <Group gap="sm" wrap="nowrap" align="center">
                  <LangFlag code={code} height={14} />
                  <Text size="sm" lh={1.3} style={{ flex: 1 }}>
                    {t(`language.${code}`)}
                  </Text>
                </Group>
              </Menu.Item>
            ))}
          </Menu.Dropdown>
        </Menu>
        <Tooltip label={themeLabel} position="left" transitionProps={{ duration: 0 }}>
          <ActionIcon
            variant="subtle"
            color="gray"
            size="lg"
            radius="md"
            aria-label={themeLabel}
            onClick={onToggleColorScheme}
          >
            {isDarkScheme ? (
              <IconSun size={18} stroke={1.8} />
            ) : (
              <IconMoon size={18} stroke={1.8} />
            )}
          </ActionIcon>
        </Tooltip>
      </Group>
    </Group>
  );
}

type QueueViewProps = {
  jobs: WorkerJobsResponse;
  queueLoading: boolean;
  queueError: string | null;
  queueRabbitmq: string | null;
  queueSearch: string;
  onQueueSearchChange: (value: string) => void;
  queueStatusFilter: '' | 'ok' | 'error' | 'processing';
  onQueueStatusFilterChange: (value: '' | 'ok' | 'error' | 'processing') => void;
};

function QueueView({
  jobs,
  queueLoading,
  queueError,
  queueRabbitmq,
  queueSearch,
  onQueueSearchChange,
  queueStatusFilter,
  onQueueStatusFilterChange,
}: QueueViewProps) {
  const { t } = useTranslation();
  return (
    <Stack gap="md" style={{ flex: 1, minHeight: 0 }}>
      <Box
        style={{
          flex: 1,
          minHeight: 0,
          minWidth: 0,
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        <QueueJobsTable
          jobs={jobs.items}
          isLoading={queueLoading && jobs.items.length === 0}
          error={
            queueError ? (
              <Alert color="red" title={t('queue.refreshFailed')}>
                {queueError}
              </Alert>
            ) : undefined
          }
          toolbarStart={
            <Group gap="sm" wrap="nowrap" align="center" style={{ width: '100%', minWidth: 0 }}>
              <TextInput
                aria-label={t('queue.searchPlaceholder')}
                placeholder={t('queue.searchPlaceholder')}
                value={queueSearch}
                onChange={(event) => onQueueSearchChange(event.currentTarget.value)}
                size="xs"
                style={{ flex: '1 1 200px', minWidth: 0, maxWidth: 280 }}
              />
              <Group gap="xs" wrap="nowrap" align="center">
                <SegmentedControl
                  aria-label="Filter by status"
                  size="xs"
                  data={[
                    {
                      value: '',
                      label: (
                        <Tooltip
                          label={t('queue.filterAll')}
                          position="bottom"
                          transitionProps={{ duration: 0 }}
                        >
                          <IconList size={16} stroke={1.8} style={{ display: 'block' }} />
                        </Tooltip>
                      ),
                    },
                    {
                      value: 'processing',
                      label: (
                        <Tooltip
                          label={t('queue.filterProcessing')}
                          position="bottom"
                          transitionProps={{ duration: 0 }}
                        >
                          <IconLoader2 size={16} stroke={1.8} style={{ display: 'block' }} />
                        </Tooltip>
                      ),
                    },
                    {
                      value: 'error',
                      label: (
                        <Tooltip
                          label={t('queue.filterErrors')}
                          position="bottom"
                          transitionProps={{ duration: 0 }}
                        >
                          <IconAlertTriangle size={16} stroke={1.8} style={{ display: 'block' }} />
                        </Tooltip>
                      ),
                    },
                  ]}
                  value={queueStatusFilter}
                  onChange={(value) =>
                    onQueueStatusFilterChange(value as '' | 'ok' | 'error' | 'processing')
                  }
                />
                <Text size="xs" c="dimmed" style={{ whiteSpace: 'nowrap' }}>
                  {queueLoading && jobs.items.length === 0
                    ? '…'
                    : t('queue.jobCount', { count: jobs.total })}
                </Text>
              </Group>
            </Group>
          }
          afterTable={
            <Box style={{ width: '100%', display: 'flex', justifyContent: 'center' }}>
              <RabbitmqStatus rabbitmq={queueRabbitmq} />
            </Box>
          }
        />
      </Box>
      <QueueThroughputChart jobs={jobs.items} />
    </Stack>
  );
}

function OverviewView() {
  return <ProcessingOverview />;
}

export type AppSectionId = 'overview' | 'queue';

type AppSectionContentProps = {
  activeSection: AppSectionId;
  jobs: WorkerJobsResponse;
  queueLoading: boolean;
  queueError: string | null;
  queueRabbitmq: string | null;
  queueSearch: string;
  onQueueSearchChange: (value: string) => void;
  queueStatusFilter: '' | 'ok' | 'error' | 'processing';
  onQueueStatusFilterChange: (value: '' | 'ok' | 'error' | 'processing') => void;
};

export function AppSectionContent({
  activeSection,
  jobs,
  queueLoading,
  queueError,
  queueRabbitmq,
  queueSearch,
  onQueueSearchChange,
  queueStatusFilter,
  onQueueStatusFilterChange,
}: AppSectionContentProps) {
  if (activeSection === 'queue') {
    return (
      <QueueView
        jobs={jobs}
        queueLoading={queueLoading}
        queueError={queueError}
        queueRabbitmq={queueRabbitmq}
        queueSearch={queueSearch}
        onQueueSearchChange={onQueueSearchChange}
        queueStatusFilter={queueStatusFilter}
        onQueueStatusFilterChange={onQueueStatusFilterChange}
      />
    );
  }
  return <OverviewView />;
}
