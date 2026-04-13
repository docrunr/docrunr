import type { TablerIcon } from '@tabler/icons-react';
import {
  IconBraces,
  IconFile,
  IconFileCode,
  IconFileDescription,
  IconFileText,
  IconFileTypeDocx,
  IconFileTypeHtml,
  IconFileTypeJs,
  IconFileTypePdf,
  IconFileTypePpt,
  IconFileTypeTs,
  IconFileZip,
  IconJson,
  IconMarkdown,
  IconMusic,
  IconPhoto,
  IconTable,
  IconVideo,
} from '@tabler/icons-react';

const STROKE = 1.65;

const CODE_LIKE_EXTS = [
  'css',
  'scss',
  'py',
  'rs',
  'go',
  'rb',
  'php',
  'sh',
  'sql',
  'c',
  'h',
  'cpp',
  'java',
  'kt',
  'swift',
] as const;
const IMAGE_EXTS = ['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'bmp', 'ico', 'img'] as const;
const VIDEO_EXTS = ['mp4', 'webm', 'mov', 'avi', 'mkv', 'video'] as const;
const AUDIO_EXTS = ['mp3', 'wav', 'ogg', 'flac', 'm4a', 'audio'] as const;

function fillExtIcons(
  m: Record<string, TablerIcon>,
  exts: readonly string[],
  icon: TablerIcon
): void {
  for (const k of exts) m[k] = icon;
}

function buildExtensionIconMap(): Record<string, TablerIcon> {
  const m: Record<string, TablerIcon> = {
    '?': IconFileDescription,
    unknown: IconFileDescription,
    pdf: IconFileTypePdf,
    doc: IconFileTypeDocx,
    docx: IconFileTypeDocx,
    odt: IconFileTypeDocx,
    rtf: IconFileTypeDocx,
    ppt: IconFileTypePpt,
    pptx: IconFileTypePpt,
    odp: IconFileTypePpt,
    xls: IconTable,
    xlsx: IconTable,
    xlsm: IconTable,
    ods: IconTable,
    csv: IconTable,
    html: IconFileTypeHtml,
    htm: IconFileTypeHtml,
    md: IconMarkdown,
    txt: IconFileText,
    json: IconJson,
    xml: IconBraces,
    yaml: IconBraces,
    yml: IconBraces,
    zip: IconFileZip,
    gz: IconFileZip,
    tar: IconFileZip,
    js: IconFileTypeJs,
    mjs: IconFileTypeJs,
    cjs: IconFileTypeJs,
    ts: IconFileTypeTs,
    tsx: IconFileTypeTs,
    eml: IconFileText,
    msg: IconFileText,
    epub: IconFileDescription,
  };
  fillExtIcons(m, CODE_LIKE_EXTS, IconFileCode);
  fillExtIcons(m, IMAGE_EXTS, IconPhoto);
  fillExtIcons(m, VIDEO_EXTS, IconVideo);
  fillExtIcons(m, AUDIO_EXTS, IconMusic);
  return m;
}

const EXTENSION_TO_ICON = buildExtensionIconMap();

function pickIconForExtension(ext: string, map: Record<string, TablerIcon>): TablerIcon {
  return map[ext.toLowerCase()] ?? IconFile;
}

type FileTypeIconProps = {
  /** Short extension, e.g. pdf, docx */
  extension: string;
  size?: number;
};

export function FileTypeIcon({ extension, size = 15 }: FileTypeIconProps) {
  const Icon = pickIconForExtension(extension, EXTENSION_TO_ICON);
  return <Icon size={size} stroke={STROKE} aria-hidden />;
}
