import { useMemo, type CSSProperties } from 'react';
import { useTranslation } from 'react-i18next';
import { ActionIcon, Badge, Group, Loader, Text, Tooltip } from '@mantine/core';
import { type ColumnDef } from '@tanstack/react-table';
import { IconAlertCircle, IconJson, IconMarkdown } from '@tabler/icons-react';
import { FileTypeIcon } from '../../../components/icons/FileTypeIcon';
import type { WorkerJob } from '../../../services/workerApi.types';
import type { ArtifactViewerKind } from './ArtifactViewerModal';
import { getQueueRowActions, queueRowActionKey, type QueueRowAction } from './queueJobRowActions';
import { formatDurationSeconds } from '../../../utils/duration';
import { formatFileSize } from '../../../utils/file-size';
import { mimeTypeToIconExtension } from '../../../utils/mime-types';

type QueueJobsTableColumnMeta = {
  fixedWidthPx?: number;
  maxWidthPx?: number;
  clipOverflow?: boolean;
  centerContent?: boolean;
};

export function getColumnMeta(meta: unknown): QueueJobsTableColumnMeta | undefined {
  return meta && typeof meta === 'object' ? (meta as QueueJobsTableColumnMeta) : undefined;
}

export function fixedWidthStyle(px: number): CSSProperties {
  return {
    width: px,
    minWidth: px,
    maxWidth: px,
    boxSizing: 'border-box',
  };
}

function formatNumber(value: number): string {
  return value.toLocaleString();
}

function actionLabel(action: QueueRowAction, t: ReturnType<typeof useTranslation>['t']): string {
  switch (action.kind) {
    case 'markdown':
      return t('table.openMarkdown');
    case 'json':
      return t('table.openChunks');
    case 'error':
      return t('table.viewError');
  }
}

const rowActionIconProps = { size: 16, stroke: 1.8 } as const;

function JobRowActions({
  job,
  onOpenArtifact,
  onViewError,
}: {
  job: WorkerJob;
  onOpenArtifact: (kind: ArtifactViewerKind, path: string, job: WorkerJob) => void;
  onViewError: (job: WorkerJob) => void;
}) {
  const { t } = useTranslation();
  const actions = useMemo(() => getQueueRowActions(job), [job]);
  if (actions.length === 0) {
    return null;
  }
  return (
    <Group gap={2} wrap="nowrap" justify="center">
      {actions.map((action) => {
        const label = actionLabel(action, t);
        if (action.kind === 'error') {
          return (
            <Tooltip key={queueRowActionKey(action)} label={label}>
              <ActionIcon
                variant="subtle"
                color="gray"
                size="sm"
                aria-label={label}
                onClick={() => onViewError(job)}
              >
                <IconAlertCircle {...rowActionIconProps} />
              </ActionIcon>
            </Tooltip>
          );
        }
        const Icon = action.kind === 'markdown' ? IconMarkdown : IconJson;
        return (
          <Tooltip key={queueRowActionKey(action)} label={label}>
            <ActionIcon
              variant="subtle"
              color="gray"
              size="sm"
              aria-label={label}
              onClick={() => onOpenArtifact(action.kind, action.path, job)}
            >
              <Icon {...rowActionIconProps} />
            </ActionIcon>
          </Tooltip>
        );
      })}
    </Group>
  );
}

type BuildQueueJobsTableColumnsParams = {
  t: ReturnType<typeof useTranslation>['t'];
  formatFinishedAt: (value: string | undefined) => string;
  isTightTable: boolean;
  onOpenArtifact: (kind: ArtifactViewerKind, path: string, job: WorkerJob) => void;
  onViewError: (job: WorkerJob) => void;
};

export function buildQueueJobsTableColumns({
  t,
  formatFinishedAt,
  isTightTable,
  onOpenArtifact,
  onViewError,
}: BuildQueueJobsTableColumnsParams): ColumnDef<WorkerJob>[] {
  return [
    {
      accessorKey: 'mime_type',
      header: '',
      enableSorting: false,
      meta: { fixedWidthPx: 48, centerContent: true } satisfies QueueJobsTableColumnMeta,
      cell: ({ row }) => {
        const mime = row.original.mime_type?.trim();
        const ext = mimeTypeToIconExtension(mime);
        const icon = (
          <span
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'var(--mantine-color-dimmed)',
            }}
          >
            <FileTypeIcon extension={ext} />
          </span>
        );
        return mime ? (
          <Tooltip label={mime} position="right" transitionProps={{ duration: 0 }}>
            {icon}
          </Tooltip>
        ) : (
          <Tooltip label={t('table.noMimeType')} position="right" transitionProps={{ duration: 0 }}>
            {icon}
          </Tooltip>
        );
      },
    },
    {
      id: 'sort_time',
      accessorFn: (row) => row.finished_at || row.received_at || '',
      header: t('table.finishedTime'),
      meta: { fixedWidthPx: 196 } satisfies QueueJobsTableColumnMeta,
      cell: ({ row }) => {
        const { status, finished_at, received_at } = row.original;
        const primary = status === 'processing' ? undefined : (finished_at ?? received_at);
        return (
          <Text
            size="sm"
            w="100%"
            style={
              isTightTable
                ? {
                    whiteSpace: 'normal',
                    wordBreak: 'break-word',
                    minWidth: 0,
                  }
                : {
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    minWidth: 0,
                  }
            }
          >
            {formatFinishedAt(primary)}
          </Text>
        );
      },
    },
    {
      accessorKey: 'status',
      header: t('table.status'),
      meta: {
        fixedWidthPx: 76,
        centerContent: true,
        clipOverflow: true,
      } satisfies QueueJobsTableColumnMeta,
      cell: ({ getValue }) => {
        const status = getValue<string>();
        if (status === 'processing') {
          return (
            <Tooltip label={t('table.processing')}>
              <Loader size="sm" aria-label={t('table.processing')} />
            </Tooltip>
          );
        }
        const color = status === 'ok' ? 'teal' : status === 'error' ? 'red' : 'gray';
        return (
          <Badge
            color={color}
            variant="light"
            size="sm"
            styles={{
              root: { maxWidth: '100%' },
              label: { overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
            }}
          >
            {status}
          </Badge>
        );
      },
    },
    {
      accessorKey: 'filename',
      header: t('table.filename'),
      cell: ({ getValue }) => (
        <Text size="sm" lineClamp={1} style={{ minWidth: 0 }}>
          {getValue<string>()}
        </Text>
      ),
    },
    {
      id: 'priority',
      accessorFn: (row) => row.priority ?? 0,
      header: () => (
        <Tooltip label={t('table.priority')} position="top" transitionProps={{ duration: 0 }}>
          <span>{t('table.priorityShort')}</span>
        </Tooltip>
      ),
      meta: { fixedWidthPx: 52, centerContent: true } satisfies QueueJobsTableColumnMeta,
      cell: ({ getValue }) => (
        <Text size="sm" style={{ whiteSpace: 'nowrap' }}>
          {formatNumber(getValue<number>())}
        </Text>
      ),
    },
    {
      id: 'size_bytes',
      accessorFn: (row) => row.size_bytes ?? 0,
      header: t('table.size'),
      meta: { fixedWidthPx: 96, centerContent: true } satisfies QueueJobsTableColumnMeta,
      cell: ({ row }) => (
        <Text
          size="sm"
          ta="center"
          w="100%"
          style={{
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            minWidth: 0,
          }}
        >
          {formatFileSize(row.original.size_bytes)}
        </Text>
      ),
    },
    {
      accessorKey: 'duration_seconds',
      header: t('table.duration'),
      meta: { fixedWidthPx: 84, centerContent: true } satisfies QueueJobsTableColumnMeta,
      cell: ({ getValue }) => (
        <Text
          size="sm"
          ta="center"
          w="100%"
          style={{
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            minWidth: 0,
          }}
        >
          {formatDurationSeconds(getValue<number>())}
        </Text>
      ),
    },
    {
      accessorKey: 'chunk_count',
      header: t('table.chunks'),
      meta: { fixedWidthPx: 64, centerContent: true } satisfies QueueJobsTableColumnMeta,
      cell: ({ getValue }) => (
        <Text
          size="sm"
          ta="center"
          w="100%"
          style={{
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            minWidth: 0,
          }}
        >
          {formatNumber(getValue<number>())}
        </Text>
      ),
    },
    {
      accessorKey: 'total_tokens',
      header: t('table.tokens'),
      meta: { fixedWidthPx: 92, centerContent: true } satisfies QueueJobsTableColumnMeta,
      cell: ({ getValue }) => (
        <Text
          size="sm"
          ta="center"
          w="100%"
          style={{
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            minWidth: 0,
          }}
        >
          {formatNumber(getValue<number>())}
        </Text>
      ),
    },
    {
      accessorKey: 'source_path',
      header: t('table.sourcePath'),
      cell: ({ getValue }) => (
        <Text size="sm" c="dimmed" lineClamp={1}>
          {getValue<string>()}
        </Text>
      ),
    },
    {
      id: 'actions',
      header: '',
      enableSorting: false,
      meta: { centerContent: true, fixedWidthPx: 76 } satisfies QueueJobsTableColumnMeta,
      cell: ({ row }) => (
        <JobRowActions
          job={row.original}
          onOpenArtifact={onOpenArtifact}
          onViewError={onViewError}
        />
      ),
    },
  ];
}
