import type {
  AnyJobsResponse,
  LlmProfileOption,
  LlmProfilesResponse,
  UploadDocumentsResponse,
  WorkerAuthSession,
  WorkerMode,
  WorkerOverview,
} from './workerApi.types';
import { notifySessionUnauthorized } from './sessionInvalidate';

const sameOriginJsonInit: RequestInit = {
  credentials: 'include',
  headers: { Accept: 'application/json' },
};

/**
 * Build a URL for the given worker mode.
 *
 * In dev mode (no VITE_WORKER_MODE), LLM calls go through the Vite
 * ``/llm-api`` proxy → port 8081.  In Docker each image serves ``/api``
 * directly on its own origin.
 */
function modeApiUrl(
  path: string,
  mode: WorkerMode,
  params?: Record<string, string | number | undefined>
): string {
  const prefix = mode === 'llm' && !import.meta.env.VITE_WORKER_MODE ? '/llm-api' : '/api';
  const url = new URL(`${prefix}${path}`, window.location.origin);
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== '') {
        url.searchParams.set(key, String(value));
      }
    });
  }
  return url.toString();
}

export function workerApiUrl(
  path: string,
  params?: Record<string, string | number | undefined>
): string {
  return modeApiUrl(path, 'txt', params);
}

export function llmApiUrl(
  path: string,
  params?: Record<string, string | number | undefined>
): string {
  return modeApiUrl(path, 'llm', params);
}

/** Same-origin fetch with session cookies (artifacts, custom calls). */
export async function workerFetch(input: string, init: RequestInit = {}): Promise<Response> {
  const response = await fetch(input, {
    credentials: 'include',
    ...init,
    headers: {
      ...((init.headers as Record<string, string> | undefined) ?? {}),
    },
  });
  if (response.status === 401) {
    notifySessionUnauthorized();
  }
  return response;
}

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url, sameOriginJsonInit);
  if (response.status === 401) {
    notifySessionUnauthorized();
  }
  if (!response.ok) {
    throw new Error(`Request failed (${response.status})`);
  }
  return (await response.json()) as T;
}

/**
 * Session probe — must not call ``notifySessionUnauthorized`` on 401 to avoid feedback loops.
 */
export async function fetchAuthSession(): Promise<WorkerAuthSession> {
  const response = await fetch(workerApiUrl('/auth/session'), sameOriginJsonInit);
  if (!response.ok) {
    throw new Error(`Request failed (${response.status})`);
  }
  return (await response.json()) as WorkerAuthSession;
}

export async function loginWorkerUi(password: string): Promise<void> {
  const response = await fetch(workerApiUrl('/auth/login'), {
    method: 'POST',
    credentials: 'include',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ password }),
  });
  let body: { ok?: boolean; error?: string } = {};
  try {
    body = (await response.json()) as { ok?: boolean; error?: string };
  } catch {
    // ignore
  }
  if (!response.ok) {
    const code =
      typeof body.error === 'string' && body.error ? body.error : `http_${response.status}`;
    throw new Error(code);
  }
}

export async function logoutWorkerUi(): Promise<void> {
  await fetch(workerApiUrl('/auth/logout'), {
    method: 'POST',
    credentials: 'include',
    headers: { Accept: 'application/json' },
  });
}

export function fetchOverview(mode: WorkerMode = 'txt'): Promise<WorkerOverview> {
  return getJson<WorkerOverview>(modeApiUrl('/overview', mode));
}

export function fetchJobs(
  params: {
    limit?: number;
    status?: 'ok' | 'error' | 'processing' | '';
    search?: string;
  },
  mode: WorkerMode = 'txt'
): Promise<AnyJobsResponse> {
  return getJson<AnyJobsResponse>(
    modeApiUrl('/jobs', mode, {
      limit: params.limit,
      status: params.status,
      search: params.search,
    })
  );
}

export async function fetchLlmProfiles(): Promise<LlmProfileOption[]> {
  const response = await getJson<LlmProfilesResponse>(llmApiUrl('/llm-profiles'));
  return response.items;
}

export async function uploadDocuments(
  files: File[],
  options?: { llmProfile?: string }
): Promise<UploadDocumentsResponse> {
  const formData = new FormData();
  files.forEach((file) => {
    formData.append('files', file);
  });
  const params: Record<string, string> = {};
  if (options?.llmProfile) {
    params.llm_profile = options.llmProfile;
  }
  const qs = new URLSearchParams(params).toString();
  const url = workerApiUrl('/uploads') + (qs ? `?${qs}` : '');
  const response = await fetch(url, {
    method: 'POST',
    credentials: 'include',
    body: formData,
  });
  if (response.status === 401) {
    notifySessionUnauthorized();
  }
  const data = (await response.json()) as UploadDocumentsResponse;
  if (!response.ok) {
    const message =
      typeof data.error === 'string' && data.error
        ? data.error
        : `Upload failed (${response.status})`;
    throw new Error(message);
  }
  return data;
}
