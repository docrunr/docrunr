import type { AnyJob, LlmJob, WorkerJob } from '../../../services/workerApi.types';
import type { OverviewTimeRange } from './time-buckets';
import { getTimeBucketLayout } from './time-buckets';
import { visitFinishedJobsInTimeBuckets } from './job-buckets';

function isWorkerJob(job: AnyJob): job is WorkerJob {
  return 'mime_type' in job || 'total_tokens' in job;
}

function isLlmJob(job: AnyJob): job is LlmJob {
  return 'llm_profile' in job;
}

/** Per-bucket MIME counts (lowercased keys; missing MIME → `unknown`), aligned with `getTimeBucketSums(..., () => 1)`. */
export function getMimeCountsPerTimeBucket(
  jobs: AnyJob[],
  range: OverviewTimeRange
): Record<string, number>[] {
  const { bucketCount } = getTimeBucketLayout(range);
  const perBucket: Record<string, number>[] = Array.from({ length: bucketCount }, () => ({}));

  visitFinishedJobsInTimeBuckets(jobs, range, (job, idx) => {
    const mime = isWorkerJob(job) ? (job.mime_type?.trim().toLowerCase() || 'unknown') : 'unknown';
    const row = perBucket[idx];
    row[mime] = (row[mime] ?? 0) + 1;
  });

  return perBucket;
}

/** Per-bucket LLM profile counts, aligned with `getTimeBucketSums(..., () => 1)`. */
export function getProfileCountsPerTimeBucket(
  jobs: AnyJob[],
  range: OverviewTimeRange
): Record<string, number>[] {
  const { bucketCount } = getTimeBucketLayout(range);
  const perBucket: Record<string, number>[] = Array.from({ length: bucketCount }, () => ({}));

  visitFinishedJobsInTimeBuckets(jobs, range, (job, idx) => {
    const profile = isLlmJob(job) ? (job.llm_profile || 'unknown') : 'unknown';
    const row = perBucket[idx];
    row[profile] = (row[profile] ?? 0) + 1;
  });

  return perBucket;
}
