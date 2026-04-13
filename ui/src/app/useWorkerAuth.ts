import { useContext } from 'react';
import { WorkerAuthContext, type WorkerAuthContextValue } from './worker-auth-context';

export function useWorkerAuth(): WorkerAuthContextValue {
  const ctx = useContext(WorkerAuthContext);
  if (!ctx) {
    throw new Error('useWorkerAuth must be used within WorkerAuthProvider');
  }
  return ctx;
}
