import type { LlmJobsResponse, LlmWorkerOverview } from './workerLlmApi.types';

/**
 * worker-llm API access.  In dev mode, Vite proxies ``/llm-api/*`` to the
 * LLM worker on port 8081 (see vite.config.ts).  In Docker each container
 * has its own port; set ``VITE_LLM_API_BASE`` to the worker-llm origin
 * (e.g. ``http://worker-llm:8081``) at build time.
 */
function llmApiUrl(path: string, params?: Record<string, string | number | undefined>): string {
  const externalBase = import.meta.env?.VITE_LLM_API_BASE as string | undefined;
  const url = externalBase
    ? new URL(`/api${path}`, externalBase)
    : new URL(`/llm-api${path}`, window.location.origin);
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== '') {
        url.searchParams.set(key, String(value));
      }
    });
  }
  return url.toString();
}

const jsonInit: RequestInit = {
  credentials: 'include',
  headers: { Accept: 'application/json' },
};

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url, jsonInit);
  if (!response.ok) {
    throw new Error(`LLM API request failed (${response.status})`);
  }
  return (await response.json()) as T;
}

export function fetchLlmOverview(): Promise<LlmWorkerOverview> {
  return getJson<LlmWorkerOverview>(llmApiUrl('/overview'));
}

export function fetchLlmJobs(params: {
  limit?: number;
  status?: 'ok' | 'error' | 'processing' | '';
  search?: string;
}): Promise<LlmJobsResponse> {
  return getJson<LlmJobsResponse>(
    llmApiUrl('/jobs', {
      limit: params.limit,
      status: params.status,
      search: params.search,
    })
  );
}

export function llmArtifactUrl(path: string): string {
  return llmApiUrl('/artifact', { path });
}
