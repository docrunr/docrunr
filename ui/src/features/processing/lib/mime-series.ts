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

function accumulateKeyedCountsPerBucket(
  jobs: AnyJob[],
  range: OverviewTimeRange,
  keyForJob: (job: AnyJob) => string
): Record<string, number>[] {
  const { bucketCount } = getTimeBucketLayout(range);
  const perBucket: Record<string, number>[] = Array.from({ length: bucketCount }, () => ({}));

  visitFinishedJobsInTimeBuckets(jobs, range, (job, idx) => {
    const key = keyForJob(job);
    const row = perBucket[idx];
    row[key] = (row[key] ?? 0) + 1;
  });

  return perBucket;
}

/** Per-bucket MIME counts (lowercased keys; missing MIME → `unknown`), aligned with `getTimeBucketSums(..., () => 1)`. */
export function getMimeCountsPerTimeBucket(
  jobs: AnyJob[],
  range: OverviewTimeRange
): Record<string, number>[] {
  return accumulateKeyedCountsPerBucket(jobs, range, (job) =>
    isWorkerJob(job) ? (job.mime_type?.trim().toLowerCase() || 'unknown') : 'unknown'
  );
}

/** Per-bucket LLM profile counts, aligned with `getTimeBucketSums(..., () => 1)`. */
export function getProfileCountsPerTimeBucket(
  jobs: AnyJob[],
  range: OverviewTimeRange
): Record<string, number>[] {
  return accumulateKeyedCountsPerBucket(jobs, range, (job) =>
    isLlmJob(job) ? (job.llm_profile || 'unknown') : 'unknown'
  );
}
