import type { AnyJob } from '../../../services/workerApi.types';
import type { OverviewTimeRange } from './time-buckets';
import { getTimeBucketLayout } from './time-buckets';
import { visitFinishedJobsInTimeBuckets } from './job-buckets';

export function getTimeBucketSums(
  jobs: AnyJob[],
  range: OverviewTimeRange,
  valueOf: (job: AnyJob) => number
): number[] {
  const { bucketCount } = getTimeBucketLayout(range);
  const buckets = new Array<number>(bucketCount).fill(0);

  visitFinishedJobsInTimeBuckets(jobs, range, (job, idx) => {
    buckets[idx] += valueOf(job);
  });

  return buckets;
}

export function getTimeBucketAverages(
  jobs: AnyJob[],
  range: OverviewTimeRange,
  valueOf: (job: AnyJob) => number
): number[] {
  const { bucketCount } = getTimeBucketLayout(range);
  const sums = new Array<number>(bucketCount).fill(0);
  const counts = new Array<number>(bucketCount).fill(0);

  visitFinishedJobsInTimeBuckets(jobs, range, (job, idx) => {
    const val = valueOf(job);
    if (!Number.isFinite(val)) return;
    sums[idx] += val;
    counts[idx] += 1;
  });

  return sums.map((s, i) => (counts[i] > 0 ? s / counts[i] : 0));
}
