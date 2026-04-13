import type { WorkerJob } from '../../../services/workerApi.types';

export type QueueRowAction =
  | { kind: 'markdown'; path: string }
  | { kind: 'json'; path: string }
  | { kind: 'error' };

/**
 * Status-driven row actions: processing → none; ok → artifact paths only; error → view error only.
 */
export function getQueueRowActions(job: WorkerJob): QueueRowAction[] {
  const { status } = job;
  if (status === 'processing') {
    return [];
  }
  if (status === 'error') {
    return [{ kind: 'error' }];
  }
  if (status === 'ok') {
    const actions: QueueRowAction[] = [];
    if (job.markdown_path) {
      actions.push({ kind: 'markdown', path: job.markdown_path });
    }
    if (job.chunks_path) {
      actions.push({ kind: 'json', path: job.chunks_path });
    }
    return actions;
  }
  return [];
}

export function queueRowActionKey(action: QueueRowAction): string {
  if (action.kind === 'error') {
    return 'error';
  }
  return `${action.kind}:${action.path}`;
}
