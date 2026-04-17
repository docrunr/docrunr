import { type ReactNode } from 'react';
import { Group, Loader, Modal, Paper, ScrollArea, Stack, Table, Text } from '@mantine/core';
import {
  type Header,
  type Row,
  type Table as TanStackTable,
  flexRender,
} from '@tanstack/react-table';
import { IconArrowsSort, IconChevronDown, IconChevronUp } from '@tabler/icons-react';
import type { AnyJob, WorkerMode } from '../../../services/workerApi.types';
import { ArtifactViewerModal, type ArtifactViewerKind } from './ArtifactViewerModal';
import { fixedWidthStyle, getColumnMeta } from './queueJobsTableColumns';

function headerAriaSort(
  sorted: ReturnType<Header<AnyJob, unknown>['column']['getIsSorted']>,
  canSort: boolean
): 'ascending' | 'descending' | 'none' | undefined {
  if (sorted === 'asc') return 'ascending';
  if (sorted === 'desc') return 'descending';
  if (canSort) return 'none';
  return undefined;
}

function ColumnSortIcon({
  state,
}: {
  state: ReturnType<Header<AnyJob, unknown>['column']['getIsSorted']>;
}) {
  if (state === 'desc') {
    return <IconChevronDown size={14} stroke={1.8} />;
  }
  if (state === 'asc') {
    return <IconChevronUp size={14} stroke={1.8} />;
  }
  return <IconArrowsSort size={14} stroke={1.8} />;
}

function QueueJobsTableHeaderCell({ header }: { header: Header<AnyJob, unknown> }) {
  const canSort = header.column.getCanSort();
  const sorted = header.column.getIsSorted();
  const colMeta = getColumnMeta(header.column.columnDef.meta);
  const fixedPx = colMeta?.fixedWidthPx;
  const maxW = colMeta?.maxWidthPx;
  const sortIconStyle = {
    display: 'inline-flex' as const,
    alignItems: 'center' as const,
    flexShrink: 0,
    color: 'var(--mantine-color-dimmed)',
    opacity: sorted ? 1 : 0.45,
  };

  const centered = Boolean(colMeta?.centerContent);

  return (
    <Table.Th
      onClick={header.column.getToggleSortingHandler()}
      style={{
        cursor: canSort ? 'pointer' : 'default',
        ...(fixedPx != null ? fixedWidthStyle(fixedPx) : {}),
        ...(maxW != null ? { maxWidth: maxW, minWidth: 0, overflow: 'hidden' } : {}),
        ...(colMeta?.clipOverflow ? { minWidth: 0, overflow: 'hidden' } : {}),
        ...(centered ? { textAlign: 'center' as const } : {}),
      }}
      aria-label={header.column.id === 'actions' ? 'Actions' : undefined}
      aria-sort={headerAriaSort(sorted, canSort)}
    >
      {header.isPlaceholder ? null : (
        <div
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
            flexWrap: 'nowrap',
            verticalAlign: 'middle',
          }}
        >
          {flexRender(header.column.columnDef.header, header.getContext())}
          {canSort ? (
            <span style={sortIconStyle} aria-hidden>
              <ColumnSortIcon state={sorted} />
            </span>
          ) : null}
        </div>
      )}
    </Table.Th>
  );
}

type QueueJobsTableModalsProps = {
  artifactModal: { kind: ArtifactViewerKind; path: string; filename: string } | null;
  onCloseArtifact: () => void;
  errorModalJob: AnyJob | null;
  onCloseError: () => void;
  t: (key: string, options?: Record<string, string>) => string;
  mode: WorkerMode;
};

export function QueueJobsTableModals({
  artifactModal,
  onCloseArtifact,
  errorModalJob,
  onCloseError,
  t,
  mode,
}: QueueJobsTableModalsProps) {
  return (
    <>
      <ArtifactViewerModal
        opened={artifactModal !== null}
        onClose={onCloseArtifact}
        kind={artifactModal?.kind ?? 'markdown'}
        path={artifactModal?.path ?? ''}
        filename={artifactModal?.filename ?? ''}
        mode={mode}
      />

      <Modal
        opened={errorModalJob !== null}
        onClose={onCloseError}
        title={
          errorModalJob ? t('table.errorTitle', { filename: errorModalJob.filename }) : undefined
        }
        size="lg"
      >
        {errorModalJob?.error?.trim() ? (
          <Text
            size="sm"
            component="pre"
            style={{
              margin: 0,
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
              fontFamily: 'var(--mantine-font-family-monospace)',
            }}
          >
            {errorModalJob.error}
          </Text>
        ) : (
          <Text size="sm" c="dimmed">
            {t('table.errorEmpty')}
          </Text>
        )}
      </Modal>
    </>
  );
}

type QueueJobsTableToolbarProps = {
  isLoading: boolean;
  pageSizeSelect: ReactNode;
  pageNavigation: ReactNode;
  toolbarStart?: ReactNode;
};

export function QueueJobsTableToolbar({
  isLoading,
  pageSizeSelect,
  pageNavigation,
  toolbarStart,
}: QueueJobsTableToolbarProps) {
  return (
    <Group justify="space-between" align="center" wrap="wrap" gap="sm">
      <Group gap="sm" wrap="wrap" align="center" style={{ flex: '1 1 auto', minWidth: 0 }}>
        {!isLoading && pageSizeSelect}
        {toolbarStart ? <div style={{ flex: 1, minWidth: 0 }}>{toolbarStart}</div> : null}
      </Group>
      {!isLoading && pageNavigation}
    </Group>
  );
}

type QueueJobsTableDataSectionProps = {
  isLoading: boolean;
  afterTable?: ReactNode;
  t: (key: string) => string;
  table: TanStackTable<AnyJob>;
  columnCount: number;
  isTightTable: boolean;
  tableBorderColor: string;
};

function QueueJobsTableBodyRow({ row }: { row: Row<AnyJob> }) {
  return (
    <Table.Tr>
      {row.getVisibleCells().map((cell) => {
        const cellMeta = getColumnMeta(cell.column.columnDef.meta);
        const fixedPx = cellMeta?.fixedWidthPx;
        const maxW = cellMeta?.maxWidthPx;
        const centered = cellMeta?.centerContent;
        const rendered = flexRender(cell.column.columnDef.cell, cell.getContext());
        return (
          <Table.Td
            key={cell.id}
            style={{
              ...(fixedPx != null ? fixedWidthStyle(fixedPx) : {}),
              ...(maxW != null ? { maxWidth: maxW, minWidth: 0, overflow: 'hidden' } : {}),
              ...(cellMeta?.clipOverflow ? { minWidth: 0, overflow: 'hidden' } : {}),
            }}
          >
            {centered ? (
              <Group
                justify="center"
                w="100%"
                wrap="nowrap"
                style={{ minWidth: 0, maxWidth: '100%' }}
              >
                {rendered}
              </Group>
            ) : (
              rendered
            )}
          </Table.Td>
        );
      })}
    </Table.Tr>
  );
}

export function QueueJobsTableDataSection({
  isLoading,
  afterTable,
  t,
  table,
  columnCount,
  isTightTable,
  tableBorderColor,
}: QueueJobsTableDataSectionProps) {
  const rows = table.getRowModel().rows;

  return (
    <Stack gap="xs" style={{ flex: 1, minHeight: 0, minWidth: 0, width: '100%' }}>
      {isLoading ? (
        <Group justify="center" py="xl" style={{ flex: 1 }}>
          <Loader size="sm" />
          <Text size="sm" c="dimmed">
            {t('queue.loading')}
          </Text>
        </Group>
      ) : (
        <Paper
          withBorder
          radius="md"
          px="xs"
          py="xs"
          style={{
            overflow: 'hidden',
            width: '100%',
            minWidth: 0,
          }}
        >
          <ScrollArea
            style={{ width: '100%', minWidth: 0 }}
            styles={{ viewport: { maxWidth: '100%' } }}
          >
            <Table
              striped
              highlightOnHover
              withRowBorders={false}
              horizontalSpacing="sm"
              verticalSpacing="sm"
              styles={{
                table: {
                  width: '100%',
                  tableLayout: isTightTable ? 'auto' : 'fixed',
                },
                th: {
                  borderTop: 'none',
                  borderLeft: 'none',
                  borderRight: 'none',
                  borderBottom: `1px solid ${tableBorderColor}`,
                },
                td: {
                  border: 'none',
                },
              }}
            >
              <Table.Thead>
                {table.getHeaderGroups().map((headerGroup) => (
                  <Table.Tr key={headerGroup.id}>
                    {headerGroup.headers.map((header) => (
                      <QueueJobsTableHeaderCell key={header.id} header={header} />
                    ))}
                  </Table.Tr>
                ))}
              </Table.Thead>
              <Table.Tbody>
                {rows.map((row) => (
                  <QueueJobsTableBodyRow key={row.id} row={row} />
                ))}
                {rows.length === 0 && (
                  <Table.Tr>
                    <Table.Td colSpan={columnCount}>
                      <Text size="sm" c="dimmed" ta="center" py="md">
                        {t('queue.noJobs')}
                      </Text>
                    </Table.Td>
                  </Table.Tr>
                )}
              </Table.Tbody>
            </Table>
          </ScrollArea>
        </Paper>
      )}
      {afterTable}
    </Stack>
  );
}
