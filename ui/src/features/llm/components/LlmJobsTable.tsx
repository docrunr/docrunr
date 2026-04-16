import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Badge,
  Code,
  Loader,
  Modal,
  NativeSelect,
  Pagination,
  ScrollArea,
  Stack,
  Table,
  Text,
  Tooltip,
  useComputedColorScheme,
  useMantineTheme,
} from '@mantine/core';
import {
  type PaginationState,
  SortingState,
  type VisibilityState,
  flexRender,
  getCoreRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
} from '@tanstack/react-table';
import type { LlmJob } from '../../../services/workerLlmApi.types';
import { formatDurationSeconds } from '../../../utils/duration';

const DEFAULT_PAGE_SIZE = 10;

function formatNumber(value: number): string {
  return value.toLocaleString();
}

function formatFinishedAt(value: string | undefined, locale: string, empty: string): string {
  if (!value) return empty;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  const datePart = new Intl.DateTimeFormat(locale, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  }).format(d);
  const timePart = new Intl.DateTimeFormat(locale, {
    hour: 'numeric',
    minute: '2-digit',
    second: '2-digit',
  }).format(d);
  return `${datePart} ${timePart}`;
}

function buildColumns(
  t: ReturnType<typeof useTranslation>['t'],
  fmtTime: (v: string | undefined) => string,
  onViewError: (job: LlmJob) => void
): ColumnDef<LlmJob>[] {
  return [
    {
      id: 'sort_time',
      accessorFn: (row) => row.finished_at || row.received_at || '',
      header: t('table.finishedTime'),
      cell: ({ row }) => {
        const { status, finished_at, received_at } = row.original;
        return (
          <Text size="sm" style={{ whiteSpace: 'nowrap' }}>
            {fmtTime(status === 'processing' ? undefined : (finished_at ?? received_at))}
          </Text>
        );
      },
    },
    {
      accessorKey: 'status',
      header: t('table.status'),
      cell: ({ getValue }) => {
        const status = getValue<string>();
        if (status === 'processing') {
          return <Loader size="sm" aria-label={t('table.processing')} />;
        }
        const color = status === 'ok' ? 'teal' : status === 'error' ? 'red' : 'gray';
        return (
          <Badge color={color} variant="light" size="sm">
            {status}
          </Badge>
        );
      },
    },
    {
      accessorKey: 'filename',
      header: t('table.filename'),
      cell: ({ getValue }) => (
        <Text size="sm" lineClamp={1}>
          {getValue<string>()}
        </Text>
      ),
    },
    {
      accessorKey: 'llm_profile',
      header: t('llm.profile'),
      cell: ({ getValue }) => (
        <Text size="sm" lineClamp={1}>
          {getValue<string>() || '—'}
        </Text>
      ),
    },
    {
      accessorKey: 'provider',
      header: t('llm.provider'),
      cell: ({ getValue }) => (
        <Text size="sm" lineClamp={1}>
          {getValue<string>() || '—'}
        </Text>
      ),
    },
    {
      accessorKey: 'chunk_count',
      header: t('table.chunks'),
      cell: ({ getValue }) => (
        <Text size="sm" ta="center">
          {formatNumber(getValue<number>())}
        </Text>
      ),
    },
    {
      accessorKey: 'vector_count',
      header: t('llm.vectors'),
      cell: ({ getValue }) => (
        <Text size="sm" ta="center">
          {formatNumber(getValue<number>())}
        </Text>
      ),
    },
    {
      accessorKey: 'duration_seconds',
      header: t('table.duration'),
      cell: ({ getValue }) => (
        <Text size="sm" ta="center">
          {formatDurationSeconds(getValue<number>())}
        </Text>
      ),
    },
    {
      id: 'actions',
      header: '',
      enableSorting: false,
      cell: ({ row }) => {
        const job = row.original;
        if (job.error) {
          return (
            <Tooltip label={t('llm.viewError')} position="left" transitionProps={{ duration: 0 }}>
              <Badge
                color="red"
                variant="light"
                size="sm"
                style={{ cursor: 'pointer' }}
                onClick={() => onViewError(job)}
              >
                {t('llm.error')}
              </Badge>
            </Tooltip>
          );
        }
        return null;
      },
    },
  ];
}

type LlmJobsTableProps = {
  jobs: LlmJob[];
  isLoading: boolean;
};

export function LlmJobsTable({ jobs, isLoading }: LlmJobsTableProps) {
  const { t, i18n } = useTranslation();
  const dateLocale = i18n.resolvedLanguage ?? i18n.language;
  const theme = useMantineTheme();
  const colorScheme = useComputedColorScheme('light');
  const borderColor = colorScheme === 'dark' ? theme.colors.dark[4] : theme.colors.gray[3];

  const [sorting, setSorting] = useState<SortingState>([{ id: 'sort_time', desc: true }]);
  const [pagination, setPagination] = useState<PaginationState>({
    pageIndex: 0,
    pageSize: DEFAULT_PAGE_SIZE,
  });
  const [errorModalJob, setErrorModalJob] = useState<LlmJob | null>(null);

  const fmtTime = useCallback(
    (v: string | undefined) => formatFinishedAt(v, dateLocale, t('table.timeEmpty')),
    [dateLocale, t]
  );

  const columnVisibility: VisibilityState = useMemo(() => ({}), []);

  const columns = useMemo(() => buildColumns(t, fmtTime, setErrorModalJob), [t, fmtTime]);

  const table = useReactTable({
    data: jobs,
    columns,
    autoResetPageIndex: false,
    state: { sorting, pagination, columnVisibility },
    onSortingChange: setSorting,
    onPaginationChange: setPagination,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
  });

  const pageCount = table.getPageCount() || 1;

  useEffect(() => {
    setPagination((prev) => {
      const maxIndex = pageCount - 1;
      return prev.pageIndex > maxIndex ? { ...prev, pageIndex: maxIndex } : prev;
    });
  }, [pageCount]);

  if (isLoading && jobs.length === 0) {
    return <Loader size="sm" />;
  }

  return (
    <Stack gap="sm" style={{ flex: 1 }}>
      <Modal
        opened={errorModalJob !== null}
        onClose={() => setErrorModalJob(null)}
        title={t('llm.errorDetail')}
        size="lg"
      >
        {errorModalJob && (
          <ScrollArea>
            <Code block>{errorModalJob.error}</Code>
          </ScrollArea>
        )}
      </Modal>

      <ScrollArea>
        <Table
          highlightOnHover
          striped
          withTableBorder
          withColumnBorders
          style={{ borderColor }}
        >
          <Table.Thead>
            {table.getHeaderGroups().map((hg) => (
              <Table.Tr key={hg.id}>
                {hg.headers.map((header) => (
                  <Table.Th
                    key={header.id}
                    onClick={header.column.getToggleSortingHandler()}
                    style={{ cursor: header.column.getCanSort() ? 'pointer' : undefined }}
                  >
                    {header.isPlaceholder
                      ? null
                      : flexRender(header.column.columnDef.header, header.getContext())}
                  </Table.Th>
                ))}
              </Table.Tr>
            ))}
          </Table.Thead>
          <Table.Tbody>
            {table.getRowModel().rows.length === 0 ? (
              <Table.Tr>
                <Table.Td colSpan={columns.length} ta="center" py="xl">
                  <Text c="dimmed">{t('llm.noJobs')}</Text>
                </Table.Td>
              </Table.Tr>
            ) : (
              table.getRowModel().rows.map((row) => (
                <Table.Tr key={row.id}>
                  {row.getVisibleCells().map((cell) => (
                    <Table.Td key={cell.id}>
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </Table.Td>
                  ))}
                </Table.Tr>
              ))
            )}
          </Table.Tbody>
        </Table>
      </ScrollArea>

      <Stack gap="xs" align="center">
        <Pagination
          value={table.getState().pagination.pageIndex + 1}
          onChange={(page) => table.setPageIndex(page - 1)}
          total={pageCount}
          withControls
          size="sm"
        />
        <NativeSelect
          aria-label={t('table.rowsPerPage')}
          value={String(table.getState().pagination.pageSize)}
          data={['10', '25', '50', '100']}
          onChange={(e) => table.setPageSize(Number(e.currentTarget.value))}
          w={76}
          size="xs"
        />
      </Stack>
    </Stack>
  );
}
