import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { registerSessionUnauthorizedHandler } from '../services/sessionInvalidate';
import { fetchAuthSession, loginWorkerUi, logoutWorkerUi } from '../services/workerApi';
import {
  WorkerAuthContext,
  type WorkerAuthContextValue,
  type WorkerAuthStatus,
} from './worker-auth-context';

export function WorkerAuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<WorkerAuthStatus>('loading');
  const [authEnabled, setAuthEnabled] = useState(false);
  const [authenticated, setAuthenticated] = useState(true);

  const refreshSession = useCallback(async () => {
    const s = await fetchAuthSession();
    setAuthEnabled(s.auth_enabled);
    setAuthenticated(s.authenticated);
  }, []);

  useEffect(() => {
    const onUnauthorized = () => {
      void (async () => {
        try {
          await refreshSession();
        } catch {
          setAuthEnabled(false);
          setAuthenticated(true);
        }
      })();
    };
    registerSessionUnauthorizedHandler(onUnauthorized);
    return () => registerSessionUnauthorizedHandler(null);
  }, [refreshSession]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        await refreshSession();
      } catch {
        if (!cancelled) {
          setAuthEnabled(false);
          setAuthenticated(true);
        }
      } finally {
        if (!cancelled) {
          setStatus('ready');
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [refreshSession]);

  const login = useCallback(
    async (password: string) => {
      await loginWorkerUi(password);
      await refreshSession();
    },
    [refreshSession]
  );

  const logout = useCallback(async () => {
    await logoutWorkerUi();
    await refreshSession();
  }, [refreshSession]);

  const canFetchProtected = !authEnabled || authenticated;

  const value = useMemo<WorkerAuthContextValue>(
    () => ({
      status,
      authEnabled,
      authenticated,
      canFetchProtected,
      refreshSession,
      login,
      logout,
    }),
    [authEnabled, authenticated, canFetchProtected, login, logout, refreshSession, status]
  );

  return <WorkerAuthContext.Provider value={value}>{children}</WorkerAuthContext.Provider>;
}
