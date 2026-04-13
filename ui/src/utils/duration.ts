/** Human-readable duration: sec below 1 min, min below 1 hr, then hr. */
export function formatDurationSeconds(seconds: number | undefined): string {
  if (seconds === undefined || seconds === null || Number.isNaN(seconds)) {
    return '—';
  }
  if (seconds === 0) {
    return '0 sec';
  }
  if (seconds < 60) {
    return `${seconds >= 10 ? seconds.toFixed(0) : seconds.toFixed(1)} sec`;
  }
  const min = seconds / 60;
  if (min < 60) {
    return `${min >= 10 ? min.toFixed(0) : min.toFixed(1)} min`;
  }
  const hr = min / 60;
  return `${hr >= 10 ? hr.toFixed(1) : hr.toFixed(2)} hr`;
}
