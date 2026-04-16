import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { useMediaQuery } from '@mantine/hooks';
import {
  NativeSelect,
  Pagination,
  Stack,
  useComputedColorScheme,
  useMantineTheme,
} from '@mantine/core';
import {
  type PaginationState,
  SortingState,
  type VisibilityState,
  getCoreRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
} from '@tanstack/react-table';
import type { AnyJob, WorkerMode } from '../../../services/workerApi.types';
import type { ArtifactViewerKind } from './ArtifactViewerModal';
import { buildQueueJobsTableColumns } from './queueJobsTableColumns';
import {
  QueueJobsTableDataSection,
  QueueJobsTableModals,
  QueueJobsTableToolbar,
} from './queueJobsTableViews';

const QUEUE_TABLE_PAGINATION_KEY = 'docrunr.queue.tablePagination';
const DEFAULT_PAGE_SIZE = 10;
const ALLOWED_PAGE_SIZES = new Set([10, 25, 50, 100]);

function readStoredPagination(): PaginationState {
  if (typeof sessionStorage === 'undefined') {
    return { pageIndex: 0, pageSize: DEFAULT_PAGE_SIZE };
  }
  try {
    const raw = sessionStorage.getItem(QUEUE_TABLE_PAGINATION_KEY);
    if (!raw) {
      return { pageIndex: 0, pageSize: DEFAULT_PAGE_SIZE };
    }
    const parsed = JSON.parse(raw) as { pageIndex?: unknown; pageSize?: unknown };
    const pageIndex =
      typeof parsed.pageIndex === 'number' &&
      Number.isInteger(parsed.pageIndex) &&
      parsed.pageIndex >= 0
        ? parsed.pageIndex
        : 0;
    const pageSize =
      typeof parsed.pageSize === 'number' && ALLOWED_PAGE_SIZES.has(parsed.pageSize)
        ? parsed.pageSize
        : DEFAULT_PAGE_SIZE;
    return { pageIndex, pageSize };
  } catch {
    return { pageIndex: 0, pageSize: DEFAULT_PAGE_SIZE };
  }
}

function writeStoredPagination(pagination: PaginationState): void {
  try {
    sessionStorage.setItem(QUEUE_TABLE_PAGINATION_KEY, JSON.stringify(pagination));
  } catch {
    // ignore quota / private mode
  }
}

type QueueJobsTableProps = {
  jobs: AnyJob[];
  mode: WorkerMode;
  isLoading: boolean;
  toolbarStart?: ReactNode;
  afterTable?: ReactNode;
  error?: ReactNode;
};

function formatJobFinishedAt(
  value: string | undefined,
  locale: string,
  emptyLabel: string
): string {
  if (!value) {
    return emptyLabel;
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  const datePart = new Intl.DateTimeFormat(locale, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  }).format(parsed);
  const timePart = new Intl.DateTimeFormat(locale, {
    hour: 'numeric',
    minute: '2-digit',
    second: '2-digit',
  }).format(parsed);
  return `${datePart} ${timePart}`;
}

export function QueueJobsTable({
  jobs,
  mode,
  isLoading,
  toolbarStart,
  afterTable,
  error,
}: QueueJobsTableProps) {
  const { t, i18n } = useTranslation();
  const dateLocale = i18n.resolvedLanguage ?? i18n.language;

  const formatFinishedAt = useCallback(
    (value: string | undefined) => formatJobFinishedAt(value, dateLocale, t('table.timeEmpty')),
    [dateLocale, t]
  );
  const theme = useMantineTheme();
  const colorScheme = useComputedColorScheme('light');
  const tableBorderColor = colorScheme === 'dark' ? theme.colors.dark[4] : theme.colors.gray[3];

  const [sorting, setSorting] = useState<SortingState>([{ id: 'sort_time', desc: true }]);
  const [pagination, setPagination] = useState<PaginationState>(readStoredPagination);
  const [errorModalJob, setErrorModalJob] = useState<AnyJob | null>(null);
  const [artifactModal, setArtifactModal] = useState<{
    kind: ArtifactViewerKind;
    path: string;
    filename: string;
  } | null>(null);

  const isMd = useMediaQuery('(min-width: 500px)') ?? true;
  const isLg = useMediaQuery('(min-width: 700px)') ?? true;
  const isXl = useMediaQuery('(min-width: 900px)') ?? true;
  const isWide = useMediaQuery('(min-width: 1200px)') ?? true;
  const isTightTable = useMediaQuery('(max-width: 899px)') ?? false;

  const columnVisibility = useMemo((): VisibilityState => {
    if (mode === 'llm') {
      return {
        filename: isMd,
        llm_profile: isMd,
        provider: isLg,
        vector_count: isXl,
        source_path: isWide,
      } satisfies VisibilityState;
    }
    return {
      filename: isMd,
      size_bytes: isMd,
      priority: isMd,
      duration_seconds: isLg,
      chunk_count: isLg,
      total_tokens: isXl,
      source_path: isWide,
    } satisfies VisibilityState;
  }, [mode, isMd, isLg, isXl, isWide]);

  useEffect(() => {
    writeStoredPagination(pagination);
  }, [pagination]);

  const pageCountForClamp = Math.max(1, Math.ceil(jobs.length / pagination.pageSize));

  useEffect(() => {
    if (isLoading && jobs.length === 0) {
      return;
    }
    setPagination((prev) => {
      const maxIndex = pageCountForClamp - 1;
      if (prev.pageIndex <= maxIndex) {
        return prev;
      }
      return { ...prev, pageIndex: maxIndex };
    });
  }, [pageCountForClamp, isLoading, jobs.length]);

  const columns = useMemo(
    () =>
      buildQueueJobsTableColumns({
        t,
        formatFinishedAt,
        isTightTable,
        onOpenArtifact: (kind, path, j) => setArtifactModal({ kind, path, filename: j.filename }),
        onViewError: setErrorModalJob,
        mode,
      }),
    [t, formatFinishedAt, isTightTable, mode]
  );

  const table = useReactTable({
    data: jobs,
    columns,
    autoResetPageIndex: false,
    state: { sorting, pagination, columnVisibility },
    onSortingChange: setSorting,
    onPaginationChange: (updater) => {
      setPagination((prev) => (typeof updater === 'function' ? updater(prev) : updater));
    },
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
  });

  const pageCount = table.getPageCount() || 1;
  const pageIndex = table.getState().pagination.pageIndex;

  const pageSizeSelect = (
    <NativeSelect
      aria-label={t('table.rowsPerPage')}
      value={String(table.getState().pagination.pageSize)}
      data={['10', '25', '50', '100']}
      onChange={(event) => table.setPageSize(Number(event.currentTarget.value))}
      w={76}
      size="xs"
      style={{ flexShrink: 0 }}
    />
  );

  const pageNavigation = (
    <Pagination
      value={pageIndex + 1}
      onChange={(page) => table.setPageIndex(page - 1)}
      total={pageCount}
      withControls
      siblings={1}
      boundaries={1}
      size="sm"
    />
  );

  return (
    <Stack gap="md" style={{ flex: 1, minHeight: 0, minWidth: 0, width: '100%' }}>
      <QueueJobsTableModals
        artifactModal={artifactModal}
        onCloseArtifact={() => setArtifactModal(null)}
        errorModalJob={errorModalJob}
        onCloseError={() => setErrorModalJob(null)}
        t={t}
        mode={mode}
      />

      <QueueJobsTableToolbar
        isLoading={isLoading}
        pageSizeSelect={pageSizeSelect}
        pageNavigation={pageNavigation}
        toolbarStart={toolbarStart}
      />

      {error}

      <QueueJobsTableDataSection
        isLoading={isLoading}
        afterTable={afterTable}
        t={t}
        table={table}
        columnCount={columns.length}
        isTightTable={isTightTable}
        tableBorderColor={tableBorderColor}
      />
    </Stack>
  );
}
