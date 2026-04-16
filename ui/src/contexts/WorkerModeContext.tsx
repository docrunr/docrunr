import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';

export type WorkerMode = 'txt' | 'llm';

type WorkerModeContextValue = {
  mode: WorkerMode;
  setMode: (mode: WorkerMode) => void;
  isToggleable: boolean;
};

const STORAGE_KEY = 'docrunr.workerMode';

function readEnvMode(): WorkerMode | null {
  const raw =
    typeof import.meta !== 'undefined'
      ? (import.meta.env?.VITE_WORKER_MODE as string | undefined)
      : undefined;
  if (raw === 'llm') return 'llm';
  if (raw === 'txt') return 'txt';
  return null;
}

function readStoredMode(): WorkerMode {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw === 'llm') return 'llm';
  } catch {
    // ignore
  }
  return 'txt';
}

function writeStoredMode(mode: WorkerMode): void {
  try {
    localStorage.setItem(STORAGE_KEY, mode);
  } catch {
    // ignore
  }
}

const WorkerModeContext = createContext<WorkerModeContextValue>({
  mode: 'txt',
  setMode: () => {},
  isToggleable: false,
});

export function WorkerModeProvider({ children }: { children: ReactNode }) {
  const envMode = useMemo(readEnvMode, []);
  const isToggleable = envMode === null;
  const [localMode, setLocalMode] = useState<WorkerMode>(isToggleable ? readStoredMode : 'txt');

  const mode = envMode ?? localMode;

  const setMode = useCallback(
    (next: WorkerMode) => {
      if (!isToggleable) return;
      setLocalMode(next);
      writeStoredMode(next);
    },
    [isToggleable]
  );

  const value = useMemo<WorkerModeContextValue>(
    () => ({ mode, setMode, isToggleable }),
    [mode, setMode, isToggleable]
  );

  return <WorkerModeContext.Provider value={value}>{children}</WorkerModeContext.Provider>;
}

export function useWorkerMode(): WorkerModeContextValue {
  return useContext(WorkerModeContext);
}
