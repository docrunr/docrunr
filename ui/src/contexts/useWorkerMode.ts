import { useContext } from 'react';

import { WorkerModeContext } from './WorkerModeContextState';

export function useWorkerMode() {
  return useContext(WorkerModeContext);
}
