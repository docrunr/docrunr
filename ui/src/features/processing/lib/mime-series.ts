import type { WorkerJob } from '../../../services/workerApi.types';
import type { OverviewTimeRange } from './time-buckets';
import { getTimeBucketLayout } from './time-buckets';
import { visitFinishedJobsInTimeBuckets } from './job-buckets';

/** Per-bucket MIME counts (lowercased keys; missing MIME → `unknown`), aligned with `getTimeBucketSums(..., () => 1)`. */
export function getMimeCountsPerTimeBucket(
  jobs: WorkerJob[],
  range: OverviewTimeRange
): Record<string, number>[] {
  const { bucketCount } = getTimeBucketLayout(range);
  const perBucket: Record<string, number>[] = Array.from({ length: bucketCount }, () => ({}));

  visitFinishedJobsInTimeBuckets(jobs, range, (job, idx) => {
    const mime = job.mime_type?.trim().toLowerCase() || 'unknown';
    const row = perBucket[idx];
    row[mime] = (row[mime] ?? 0) + 1;
  });

  return perBucket;
}
