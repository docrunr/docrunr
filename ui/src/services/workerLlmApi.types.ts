type LlmWorkerHealth = {
  status: string;
  rabbitmq: string;
  uptime_seconds: number;
};

type LlmWorkerStats = {
  processed: number;
  failed: number;
  avg_duration_seconds: number;
  last_job_at: string | null;
  recent_jobs_count: number;
};

type LlmWorkerCpu = {
  percent: number | null;
  history: number[];
};

export type LlmWorkerOverview = {
  health: LlmWorkerHealth;
  stats: LlmWorkerStats;
  cpu: LlmWorkerCpu;
};

type LlmJobStatus = 'processing' | 'ok' | 'error';

export type LlmJob = {
  job_id: string;
  status: LlmJobStatus | string;
  filename: string;
  source_path: string;
  chunks_path: string;
  llm_profile: string;
  provider: string;
  chunk_count: number;
  vector_count: number;
  duration_seconds: number;
  artifact_path: string | null;
  error: string | null;
  received_at?: string;
  finished_at?: string;
  updated_at?: string;
};

export type LlmJobsResponse = {
  items: LlmJob[];
  count: number;
  total: number;
  limit: number;
};
