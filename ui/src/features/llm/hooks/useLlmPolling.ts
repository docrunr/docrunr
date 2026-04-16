import { useCallback, useState } from 'react';
import { usePolling } from '../../../hooks/usePolling';
import { fetchLlmJobs, fetchLlmOverview } from '../../../services/workerLlmApi';
import type { LlmJobsResponse, LlmWorkerOverview } from '../../../services/workerLlmApi.types';

const emptyJobs: LlmJobsResponse = { items: [], count: 0, total: 0, limit: 500 };

export type LlmPollingState = {
  jobs: LlmJobsResponse;
  overview: LlmWorkerOverview | null;
  loading: boolean;
  error: string | null;
  rabbitmq: string | null;
  statusFilter: '' | 'ok' | 'error' | 'processing';
  setStatusFilter: (v: '' | 'ok' | 'error' | 'processing') => void;
  search: string;
  setSearch: (v: string) => void;
};

export function useLlmPolling(active: boolean): LlmPollingState {
  const [jobs, setJobs] = useState<LlmJobsResponse>(emptyJobs);
  const [overview, setOverview] = useState<LlmWorkerOverview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rabbitmq, setRabbitmq] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<'' | 'ok' | 'error' | 'processing'>('');
  const [search, setSearch] = useState('');

  const pollFn = useCallback(
    async (isMounted: () => boolean) => {
      try {
        setLoading(true);
        const [jobsOutcome, overviewOutcome] = await Promise.allSettled([
          fetchLlmJobs({ limit: 500, status: statusFilter, search }),
          fetchLlmOverview(),
        ]);
        if (!isMounted()) return;

        if (jobsOutcome.status === 'fulfilled') {
          setJobs(jobsOutcome.value);
          setError(null);
        } else {
          const reason = jobsOutcome.reason;
          setError(reason instanceof Error ? reason.message : 'Unknown request failure');
        }

        if (overviewOutcome.status === 'fulfilled') {
          setOverview(overviewOutcome.value);
          setRabbitmq(overviewOutcome.value.health.rabbitmq);
        }
      } finally {
        if (isMounted()) {
          setLoading(false);
        }
      }
    },
    [statusFilter, search]
  );

  usePolling(active, pollFn, [active, statusFilter, search]);

  return {
    jobs,
    overview,
    loading,
    error,
    rabbitmq,
    statusFilter,
    setStatusFilter,
    search,
    setSearch,
  };
}
