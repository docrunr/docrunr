import { createContext } from 'react';

import type { WorkerMode } from '../services/workerApi.types';

export type WorkerModeContextValue = {
  mode: WorkerMode;
  setMode: (mode: WorkerMode) => void;
  isToggleable: boolean;
};

export const WorkerModeContext = createContext<WorkerModeContextValue>({
  mode: 'txt',
  setMode: () => {},
  isToggleable: false,
});
