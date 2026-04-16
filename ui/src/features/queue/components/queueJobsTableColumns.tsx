import { type CSSProperties } from 'react';
import type { TFunction } from 'i18next';
import { Badge, Loader, Text, Tooltip } from '@mantine/core';
import { type ColumnDef } from '@tanstack/react-table';
import { FileTypeIcon } from '../../../components/icons/FileTypeIcon';
import type { AnyJob, LlmJob, WorkerJob, WorkerMode } from '../../../services/workerApi.types';
import type { ArtifactViewerKind } from './ArtifactViewerModal';
import { QueueJobsTableRowActions } from './queueJobsTableRowActions';
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

function formatNumber(value: number | null | undefined): string {
  return value != null ? value.toLocaleString() : '—';
}

type BuildQueueJobsTableColumnsParams = {
  t: TFunction;
  formatFinishedAt: (value: string | undefined) => string;
  isTightTable: boolean;
  onOpenArtifact: (kind: ArtifactViewerKind, path: string, job: AnyJob) => void;
  onViewError: (job: AnyJob) => void;
  mode: WorkerMode;
};

function statusCell(getValue: () => unknown, t: TFunction) {
  const status = getValue() as string;
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
}

const CENTERED_NUMERIC_TEXT_STYLE: CSSProperties = {
  whiteSpace: 'nowrap',
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  minWidth: 0,
};

function finishedAtColumnDef(
  t: TFunction,
  formatFinishedAt: (value: string | undefined) => string,
  isTightTable: boolean
): ColumnDef<AnyJob> {
  return {
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
              ? { whiteSpace: 'normal', wordBreak: 'break-word', minWidth: 0 }
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
  };
}

function sharedStatusColumnDef(t: TFunction): ColumnDef<AnyJob> {
  return {
    accessorKey: 'status',
    header: t('table.status'),
    meta: { fixedWidthPx: 76, centerContent: true, clipOverflow: true } satisfies QueueJobsTableColumnMeta,
    cell: ({ getValue }) => statusCell(getValue, t),
  };
}

function sharedFilenameColumnDef(t: TFunction): ColumnDef<AnyJob> {
  return {
    accessorKey: 'filename',
    header: t('table.filename'),
    cell: ({ getValue }) => (
      <Text size="sm" lineClamp={1} style={{ minWidth: 0 }}>
        {getValue<string>()}
      </Text>
    ),
  };
}

function sharedDurationColumnDef(t: TFunction): ColumnDef<AnyJob> {
  return {
    accessorKey: 'duration_seconds',
    header: t('table.duration'),
    meta: { fixedWidthPx: 84, centerContent: true } satisfies QueueJobsTableColumnMeta,
    cell: ({ getValue }) => (
      <Text size="sm" ta="center" w="100%" style={CENTERED_NUMERIC_TEXT_STYLE}>
        {formatDurationSeconds(getValue<number>())}
      </Text>
    ),
  };
}

function sharedSourcePathColumnDef(t: TFunction): ColumnDef<AnyJob> {
  return {
    accessorKey: 'source_path',
    header: t('table.sourcePath'),
    cell: ({ getValue }) => (
      <Text size="sm" c="dimmed" lineClamp={1}>
        {getValue<string>()}
      </Text>
    ),
  };
}

function sharedActionsColumnDef(
  onOpenArtifact: BuildQueueJobsTableColumnsParams['onOpenArtifact'],
  onViewError: BuildQueueJobsTableColumnsParams['onViewError']
): ColumnDef<AnyJob> {
  return {
    id: 'actions',
    header: '',
    enableSorting: false,
    meta: { centerContent: true, fixedWidthPx: 76 } satisfies QueueJobsTableColumnMeta,
    cell: ({ row }) => (
      <QueueJobsTableRowActions job={row.original} onOpenArtifact={onOpenArtifact} onViewError={onViewError} />
    ),
  };
}

function buildTxtColumns({
  t,
  formatFinishedAt,
  isTightTable,
  onOpenArtifact,
  onViewError,
}: Omit<BuildQueueJobsTableColumnsParams, 'mode'>): ColumnDef<WorkerJob>[] {
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
    finishedAtColumnDef(t, formatFinishedAt, isTightTable) as ColumnDef<WorkerJob>,
    sharedStatusColumnDef(t) as ColumnDef<WorkerJob>,
    sharedFilenameColumnDef(t) as ColumnDef<WorkerJob>,
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
        <Text size="sm" ta="center" w="100%" style={CENTERED_NUMERIC_TEXT_STYLE}>
          {formatFileSize(row.original.size_bytes)}
        </Text>
      ),
    },
    sharedDurationColumnDef(t) as ColumnDef<WorkerJob>,
    {
      accessorKey: 'chunk_count',
      header: t('table.chunks'),
      meta: { fixedWidthPx: 64, centerContent: true } satisfies QueueJobsTableColumnMeta,
      cell: ({ getValue }) => (
        <Text size="sm" ta="center" w="100%" style={CENTERED_NUMERIC_TEXT_STYLE}>
          {formatNumber(getValue<number>())}
        </Text>
      ),
    },
    {
      accessorKey: 'total_tokens',
      header: t('table.tokens'),
      meta: { fixedWidthPx: 92, centerContent: true } satisfies QueueJobsTableColumnMeta,
      cell: ({ getValue }) => (
        <Text size="sm" ta="center" w="100%" style={CENTERED_NUMERIC_TEXT_STYLE}>
          {formatNumber(getValue<number>())}
        </Text>
      ),
    },
    sharedSourcePathColumnDef(t) as ColumnDef<WorkerJob>,
    sharedActionsColumnDef(onOpenArtifact, onViewError) as ColumnDef<WorkerJob>,
  ];
}

function buildLlmColumns({
  t,
  formatFinishedAt,
  isTightTable,
  onOpenArtifact,
  onViewError,
}: Pick<BuildQueueJobsTableColumnsParams, 't' | 'formatFinishedAt' | 'isTightTable' | 'onOpenArtifact' | 'onViewError'>): ColumnDef<LlmJob>[] {
  return [
    finishedAtColumnDef(t, formatFinishedAt, isTightTable) as ColumnDef<LlmJob>,
    sharedStatusColumnDef(t) as ColumnDef<LlmJob>,
    sharedFilenameColumnDef(t) as ColumnDef<LlmJob>,
    {
      accessorKey: 'llm_profile',
      header: t('table.llmProfile'),
      meta: { fixedWidthPx: 140 } satisfies QueueJobsTableColumnMeta,
      cell: ({ getValue }) => (
        <Text size="sm" lineClamp={1} style={{ minWidth: 0 }}>
          {getValue<string>()}
        </Text>
      ),
    },
    {
      accessorKey: 'provider',
      header: t('table.provider'),
      meta: { fixedWidthPx: 120 } satisfies QueueJobsTableColumnMeta,
      cell: ({ getValue }) => (
        <Text size="sm" lineClamp={1} style={{ minWidth: 0 }}>
          {getValue<string>()}
        </Text>
      ),
    },
    {
      accessorKey: 'vector_count',
      header: t('table.vectors'),
      meta: { fixedWidthPx: 72, centerContent: true } satisfies QueueJobsTableColumnMeta,
      cell: ({ getValue }) => (
        <Text size="sm" ta="center" w="100%" style={CENTERED_NUMERIC_TEXT_STYLE}>
          {formatNumber(getValue<number>())}
        </Text>
      ),
    },
    sharedDurationColumnDef(t) as ColumnDef<LlmJob>,
    sharedSourcePathColumnDef(t) as ColumnDef<LlmJob>,
    sharedActionsColumnDef(onOpenArtifact, onViewError) as ColumnDef<LlmJob>,
  ];
}

export function buildQueueJobsTableColumns(
  params: BuildQueueJobsTableColumnsParams
): ColumnDef<AnyJob>[] {
  if (params.mode === 'llm') {
    return buildLlmColumns(params) as ColumnDef<AnyJob>[];
  }
  return buildTxtColumns(params) as ColumnDef<AnyJob>[];
}
