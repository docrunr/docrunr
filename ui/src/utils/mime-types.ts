/** Full MIME → short extension label (lowercase). */
const MIME_TO_EXT: Record<string, string> = {
  'application/pdf': 'pdf',
  'application/msword': 'doc',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'xlsx',
  'application/vnd.ms-excel': 'xls',
  'application/vnd.ms-excel.sheet.macroenabled.12': 'xlsm',
  'application/vnd.openxmlformats-officedocument.presentationml.presentation': 'pptx',
  'application/vnd.ms-powerpoint': 'ppt',
  'application/vnd.oasis.opendocument.text': 'odt',
  'application/vnd.oasis.opendocument.spreadsheet': 'ods',
  'application/vnd.oasis.opendocument.presentation': 'odp',
  'application/rtf': 'rtf',
  'text/plain': 'txt',
  'text/html': 'html',
  'text/csv': 'csv',
  'text/markdown': 'md',
  'text/xml': 'xml',
  'application/json': 'json',
  'application/xml': 'xml',
  'application/zip': 'zip',
  'application/gzip': 'gz',
  'application/x-tar': 'tar',
  'message/rfc822': 'eml',
  'application/vnd.ms-outlook': 'msg',
  'application/epub+zip': 'epub',
};

function extForKnownMime(table: Record<string, string>, mimeKey: string): string | undefined {
  return table[mimeKey];
}

function mimeToExtensionLabel(mime: string): string {
  if (mime === 'unknown') return '?';
  const k = mime.toLowerCase().trim();
  const direct = extForKnownMime(MIME_TO_EXT, k);
  if (direct) return direct;
  if (k.startsWith('image/')) {
    const sub = k.slice(6);
    if (sub === 'jpeg') return 'jpg';
    if (sub === 'svg+xml') return 'svg';
    return sub || 'img';
  }
  if (k.startsWith('video/')) return k.slice(6) || 'video';
  if (k.startsWith('audio/')) return k.slice(6) || 'audio';
  if (k.startsWith('text/')) return k.slice(5) || 'txt';
  return 'file';
}

/** Maps a job MIME string to the short extension label used by `FileTypeIcon` (same rules as overview tooltips). */
export function mimeTypeToIconExtension(mime: string | undefined | null): string {
  const t = mime?.trim();
  if (!t) return '?';
  return mimeToExtensionLabel(t);
}

/** Merge MIME keys that map to the same extension (e.g. xls + xlsx stay separate; duplicate full mimes aggregate). */
export function mergeMimeCountsByExtension(
  counts: Record<string, number>
): { ext: string; count: number }[] {
  const map = new Map<string, number>();
  for (const [mime, c] of Object.entries(counts)) {
    const ext = mimeToExtensionLabel(mime);
    map.set(ext, (map.get(ext) ?? 0) + c);
  }
  return [...map.entries()]
    .map(([ext, count]) => ({ ext, count }))
    .sort((a, b) => b.count - a.count);
}
