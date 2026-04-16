import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { ActionIcon, Group, Tooltip } from '@mantine/core';
import { IconAlertCircle, IconJson, IconMarkdown } from '@tabler/icons-react';
import type { AnyJob } from '../../../services/workerApi.types';
import type { ArtifactViewerKind } from './ArtifactViewerModal';
import { getQueueRowActions, isLlmJob, queueRowActionKey, type QueueRowAction } from './queueJobRowActions';

const rowActionIconProps = { size: 16, stroke: 1.8 } as const;

function actionLabel(action: QueueRowAction, t: ReturnType<typeof useTranslation>['t'], llm: boolean): string {
  switch (action.kind) {
    case 'markdown':
      return t('table.openMarkdown');
    case 'json':
      return llm ? t('table.openVectors') : t('table.openChunks');
    case 'error':
      return t('table.viewError');
  }
}

export function QueueJobsTableRowActions({
  job,
  onOpenArtifact,
  onViewError,
}: {
  job: AnyJob;
  onOpenArtifact: (kind: ArtifactViewerKind, path: string, job: AnyJob) => void;
  onViewError: (job: AnyJob) => void;
}) {
  const { t } = useTranslation();
  const llm = isLlmJob(job);
  const actions = useMemo(() => getQueueRowActions(job), [job]);
  if (actions.length === 0) {
    return null;
  }
  return (
    <Group gap={2} wrap="nowrap" justify="center">
      {actions.map((action) => {
        const label = actionLabel(action, t, llm);
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
