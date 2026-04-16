import type { AnyJob, LlmJob, WorkerJob } from '../../../services/workerApi.types';

export type QueueRowAction =
  | { kind: 'markdown'; path: string }
  | { kind: 'json'; path: string }
  | { kind: 'error' };

function isWorkerJob(job: AnyJob): job is WorkerJob {
  return 'markdown_path' in job;
}

export function isLlmJob(job: AnyJob): job is LlmJob {
  return 'llm_profile' in job;
}

/**
 * Status-driven row actions: processing → none; ok → artifact paths only; error → view error only.
 */
export function getQueueRowActions(job: AnyJob): QueueRowAction[] {
  const { status } = job;
  if (status === 'processing') {
    return [];
  }
  if (status === 'error') {
    return [{ kind: 'error' }];
  }
  if (status === 'ok') {
    const actions: QueueRowAction[] = [];
    if (isWorkerJob(job)) {
      if (job.markdown_path) {
        actions.push({ kind: 'markdown', path: job.markdown_path });
      }
      if (job.chunks_path) {
        actions.push({ kind: 'json', path: job.chunks_path });
      }
    } else if (isLlmJob(job) && job.artifact_path) {
      actions.push({ kind: 'json', path: job.artifact_path });
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
