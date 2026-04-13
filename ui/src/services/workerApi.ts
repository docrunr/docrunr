import type {
  UploadDocumentsResponse,
  WorkerAuthSession,
  WorkerJobsResponse,
  WorkerOverview,
} from './workerApi.types';
import { notifySessionUnauthorized } from './sessionInvalidate';

const sameOriginJsonInit: RequestInit = {
  credentials: 'include',
  headers: { Accept: 'application/json' },
};

export function workerApiUrl(
  path: string,
  params?: Record<string, string | number | undefined>
): string {
  const url = new URL(`/api${path}`, window.location.origin);
  if (!params) {
    return url.toString();
  }
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== '') {
      url.searchParams.set(key, String(value));
    }
  });
  return url.toString();
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

export function fetchOverview(): Promise<WorkerOverview> {
  return getJson<WorkerOverview>(workerApiUrl('/overview'));
}

export function fetchJobs(params: {
  limit?: number;
  status?: 'ok' | 'error' | 'processing' | '';
  search?: string;
}): Promise<WorkerJobsResponse> {
  return getJson<WorkerJobsResponse>(
    workerApiUrl('/jobs', {
      limit: params.limit,
      status: params.status,
      search: params.search,
    })
  );
}

export async function uploadDocuments(files: File[]): Promise<UploadDocumentsResponse> {
  const formData = new FormData();
  files.forEach((file) => {
    formData.append('files', file);
  });
  const response = await fetch(workerApiUrl('/uploads'), {
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
