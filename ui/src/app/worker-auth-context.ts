import { createContext } from 'react';

export type WorkerAuthStatus = 'loading' | 'ready';

export type WorkerAuthContextValue = {
  status: WorkerAuthStatus;
  authEnabled: boolean;
  authenticated: boolean;
  /** When false, skip jobs / artifacts / uploads until the user signs in. */
  canFetchProtected: boolean;
  refreshSession: () => Promise<void>;
  login: (password: string) => Promise<void>;
  logout: () => Promise<void>;
};

export const WorkerAuthContext = createContext<WorkerAuthContextValue | null>(null);
