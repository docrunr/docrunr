import { beforeEach, describe, expect, it, vi } from 'vitest';
import { registerSessionUnauthorizedHandler } from './sessionInvalidate';
import {
  fetchAuthSession,
  fetchJobs,
  loginWorkerUi,
  uploadDocuments,
  workerApiUrl,
  workerFetch,
} from './workerApi';

function registerSpyAndStub401Json(spy: ReturnType<typeof vi.fn>) {
  registerSessionUnauthorizedHandler(spy);
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({}),
    })
  );
}

describe('workerApi', () => {
  beforeEach(() => {
    registerSessionUnauthorizedHandler(null);
    vi.stubGlobal('window', {
      location: { origin: 'http://127.0.0.1:8080' },
    } as Window & typeof globalThis);
  });

  it('workerApiUrl builds same-origin API paths', () => {
    expect(workerApiUrl('/auth/session')).toBe('http://127.0.0.1:8080/api/auth/session');
  });

  it('fetchAuthSession uses credentials include', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ auth_enabled: false, authenticated: true }),
    });
    vi.stubGlobal('fetch', fetchMock);

    await fetchAuthSession();

    expect(fetchMock).toHaveBeenCalledWith(
      'http://127.0.0.1:8080/api/auth/session',
      expect.objectContaining({ credentials: 'include' })
    );
  });

  it('fetchAuthSession does not notify on 401 (avoid feedback loop)', async () => {
    const spy = vi.fn();
    registerSpyAndStub401Json(spy);

    await expect(fetchAuthSession()).rejects.toThrow();

    expect(spy).not.toHaveBeenCalled();
  });

  it('fetchJobs notifies session handler on 401', async () => {
    const spy = vi.fn();
    registerSpyAndStub401Json(spy);

    await expect(fetchJobs({})).rejects.toThrow();

    expect(spy).toHaveBeenCalledTimes(1);
  });

  it('workerFetch notifies session handler on 401', async () => {
    const spy = vi.fn();
    registerSessionUnauthorizedHandler(spy);
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        text: async () => '',
      })
    );

    const res = await workerFetch('http://127.0.0.1:8080/api/artifact?path=x');

    expect(res.status).toBe(401);
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it('loginWorkerUi 401 does not notify session handler', async () => {
    const spy = vi.fn();
    registerSessionUnauthorizedHandler(spy);
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        json: async () => ({ error: 'invalid_password' }),
      })
    );

    await expect(loginWorkerUi('wrong')).rejects.toThrow();

    expect(spy).not.toHaveBeenCalled();
  });

  it('uploadDocuments notifies session handler on 401', async () => {
    const spy = vi.fn();
    registerSessionUnauthorizedHandler(spy);
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        json: async () => ({ items: [], error: 'unauthorized' }),
      })
    );

    const file = new File(['%PDF'], 'a.pdf', { type: 'application/pdf' });
    await expect(uploadDocuments([file])).rejects.toThrow();

    expect(spy).toHaveBeenCalledTimes(1);
  });

  it('loginWorkerUi posts JSON with credentials include', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true }),
    });
    vi.stubGlobal('fetch', fetchMock);

    await loginWorkerUi('secret');

    expect(fetchMock).toHaveBeenCalledWith(
      'http://127.0.0.1:8080/api/auth/login',
      expect.objectContaining({
        method: 'POST',
        credentials: 'include',
        headers: expect.objectContaining({
          'Content-Type': 'application/json',
        }),
        body: JSON.stringify({ password: 'secret' }),
      })
    );
  });
});
