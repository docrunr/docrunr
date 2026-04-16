export type WorkerMode = 'txt' | 'llm';

type WorkerHealth = {
  status: string;
  rabbitmq: string;
  uptime_seconds: number;
};

type WorkerStats = {
  processed: number;
  failed: number;
  avg_duration_seconds: number;
  last_job_at: string | null;
  recent_jobs_count: number;
};

type WorkerCpu = {
  /** Latest host CPU utilization (0–100), or null if unavailable */
  percent: number | null;
  /** Recent samples (newest last), same unit as percent */
  history: number[];
};

/** Shared overview shape — both workers return the same structure. */
export type WorkerOverview = {
  health: WorkerHealth;
  stats: WorkerStats;
  cpu: WorkerCpu;
};

type JobStatus = 'processing' | 'ok' | 'error';

export type WorkerJob = {
  job_id: string;
  status: JobStatus | string;
  filename: string;
  source_path: string;
  markdown_path: string | null;
  chunks_path: string | null;
  total_tokens: number;
  chunk_count: number;
  duration_seconds: number;
  error: string | null;
  received_at?: string;
  finished_at?: string;
  updated_at?: string;
  mime_type?: string;
  size_bytes?: number;
  priority?: number;
};

export type LlmJob = {
  job_id: string;
  status: JobStatus | string;
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

export type AnyJob = WorkerJob | LlmJob;

type WorkerJobsResponse = {
  items: WorkerJob[];
  count: number;
  total: number;
  limit: number;
};

type LlmJobsResponse = {
  items: LlmJob[];
  count: number;
  total: number;
  limit: number;
};

export type AnyJobsResponse = WorkerJobsResponse | LlmJobsResponse;

/** POST /api/uploads — per-file enqueue outcome */
type UploadQueuedItem = {
  job_id: string;
  filename: string;
  source_path: string;
  status: 'queued';
  priority: number;
};

type UploadErrorItem = {
  filename: string;
  status: 'error';
  error: string;
};

type UploadResponseItem = UploadQueuedItem | UploadErrorItem;

export type UploadDocumentsResponse = {
  items: UploadResponseItem[];
  error?: string;
};

/** GET /api/auth/session */
export type WorkerAuthSession = {
  auth_enabled: boolean;
  authenticated: boolean;
};
