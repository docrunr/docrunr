import type { WorkerMode } from './workerApi.types';
import { workerApiUrl, llmApiUrl } from './workerApi';

export function artifactUrl(path: string, mode: WorkerMode = 'txt'): string {
  const urlFn = mode === 'llm' ? llmApiUrl : workerApiUrl;
  return urlFn('/artifact', { path });
}
