import type { WorkerJob } from '../../../services/workerApi.types';
import type { OverviewTimeRange } from './time-buckets';
import { getTimeBucketLayout } from './time-buckets';

/** Invokes `visit` for each finished job in the time bucket it falls into for `range`. */
export function visitFinishedJobsInTimeBuckets(
  jobs: WorkerJob[],
  range: OverviewTimeRange,
  visit: (job: WorkerJob, bucketIndex: number) => void
): void {
  const { bucketCount, bucketMs, firstBucketStart } = getTimeBucketLayout(range);
  for (const job of jobs) {
    if (!job.finished_at) continue;
    const finishedAt = new Date(job.finished_at);
    if (Number.isNaN(finishedAt.getTime())) continue;
    const offset = finishedAt.getTime() - firstBucketStart.getTime();
    if (offset < 0) continue;
    const idx = Math.floor(offset / bucketMs);
    if (idx >= bucketCount) continue;
    visit(job, idx);
  }
}
