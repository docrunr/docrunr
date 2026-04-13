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

export type WorkerOverview = {
  health: WorkerHealth;
  stats: WorkerStats;
  cpu: WorkerCpu;
};

/** Worker / SQLite lifecycle: in-flight vs terminal outcomes */
type WorkerJobStatus = 'processing' | 'ok' | 'error';

export type WorkerJob = {
  job_id: string;
  status: WorkerJobStatus | string;
  filename: string;
  source_path: string;
  markdown_path: string | null;
  chunks_path: string | null;
  total_tokens: number;
  chunk_count: number;
  duration_seconds: number;
  error: string | null;
  /** When the worker accepted the message from the queue */
  received_at?: string;
  finished_at?: string;
  updated_at?: string;
  /** IANA media type when known (from conversion pipeline) */
  mime_type?: string;
  /** Source file size in bytes */
  size_bytes?: number;
  /** Extraction job priority 0–255 (RabbitMQ native priority) */
  priority?: number;
};

export type WorkerJobsResponse = {
  items: WorkerJob[];
  count: number;
  total: number;
  limit: number;
};

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
