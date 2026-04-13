/** Human-readable size: B below 1 KiB, KB below 1 MiB, then MB. */
export function formatFileSize(bytes: number | undefined): string {
  if (bytes === undefined || bytes === null || Number.isNaN(bytes)) {
    return '—';
  }
  if (bytes === 0) {
    return '0 B';
  }
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  const kb = bytes / 1024;
  if (kb < 1024) {
    return `${kb >= 10 ? kb.toFixed(0) : kb.toFixed(1)} KB`;
  }
  const mb = kb / 1024;
  return `${mb >= 10 ? mb.toFixed(1) : mb.toFixed(2)} MB`;
}
