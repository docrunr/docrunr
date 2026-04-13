export type OverviewTimeRange = '1h' | '12h' | '1d' | '7d';

type TimeBucketLayout = {
  bucketCount: number;
  bucketMs: number;
  firstBucketStart: Date;
};

function getHourStart(value: Date): Date {
  const next = new Date(value);
  next.setMinutes(0, 0, 0);
  return next;
}

function getMinuteBucketStart(value: Date, intervalMinutes: number): Date {
  const next = new Date(value);
  const minutes = next.getMinutes();
  const roundedMinutes = Math.floor(minutes / intervalMinutes) * intervalMinutes;
  next.setMinutes(roundedMinutes, 0, 0);
  return next;
}

function getMultiHourStart(value: Date, intervalHours: number): Date {
  const next = new Date(value);
  const hours = next.getHours();
  const roundedHours = Math.floor(hours / intervalHours) * intervalHours;
  next.setHours(roundedHours, 0, 0, 0);
  return next;
}

function getDayStart(value: Date): Date {
  const next = new Date(value);
  next.setHours(0, 0, 0, 0);
  return next;
}

/** Bucket boundaries aligned with overview throughput sparklines (5m / 1h / 2h / 12h steps). */
export function getTimeBucketLayout(
  range: OverviewTimeRange,
  now: Date = new Date()
): TimeBucketLayout {
  const bucketCount = range === '7d' ? 14 : 12;
  let bucketMs: number;
  let firstBucketStart: Date;

  if (range === '1h') {
    bucketMs = 5 * 60 * 1000;
    const current = getMinuteBucketStart(now, 5);
    firstBucketStart = new Date(current.getTime() - (bucketCount - 1) * bucketMs);
  } else if (range === '12h') {
    bucketMs = 60 * 60 * 1000;
    const current = getHourStart(now);
    firstBucketStart = new Date(current.getTime() - (bucketCount - 1) * bucketMs);
  } else if (range === '1d') {
    bucketMs = 2 * 60 * 60 * 1000;
    const current = getMultiHourStart(now, 2);
    firstBucketStart = new Date(current.getTime() - (bucketCount - 1) * bucketMs);
  } else {
    bucketMs = 12 * 60 * 60 * 1000;
    const current = getDayStart(now);
    firstBucketStart = new Date(current.getTime() - (bucketCount - 1) * bucketMs);
  }

  return { bucketCount, bucketMs, firstBucketStart };
}
