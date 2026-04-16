import {
  Component,
  type ErrorInfo,
  type ReactNode,
  type RefObject,
  useEffect,
  useRef,
  useState,
} from 'react';
import type { TFunction } from 'i18next';
import { useTranslation } from 'react-i18next';
import { Alert, Button, Group, Loader, Modal, Paper, Stack, Tabs, Text } from '@mantine/core';
import { IconDownload, IconInfoCircle } from '@tabler/icons-react';
import DOMPurify from 'dompurify';
import { Marked } from 'marked';
import Prism from 'prismjs';
import 'prismjs/components/prism-markup';
import 'prismjs/components/prism-bash';
import 'prismjs/components/prism-clike';
import 'prismjs/components/prism-css';
import 'prismjs/components/prism-javascript';
import 'prismjs/components/prism-json';
import 'prismjs/components/prism-markdown';
import 'prismjs/components/prism-python';
import 'prismjs/components/prism-typescript';
import 'prismjs/components/prism-yaml';
import type { WorkerMode } from '../../../services/workerApi.types';
import { artifactUrl } from '../../../services/artifact-urls';
import { workerFetch } from '../../../services/workerApi';
import styles from './ArtifactViewerModal.module.css';

/** Defer work until after paint so the modal shell and loader can update first. */
function scheduleYieldedTask(fn: () => void): void {
  requestAnimationFrame(() => {
    if (typeof requestIdleCallback === 'function') {
      requestIdleCallback(() => fn(), { timeout: 2000 });
    } else {
      setTimeout(fn, 0);
    }
  });
}

export type ArtifactViewerKind = 'markdown' | 'json';

type ArtifactViewerModalProps = {
  opened: boolean;
  onClose: () => void;
  kind: ArtifactViewerKind;
  path: string;
  filename: string;
  mode?: WorkerMode;
};

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function highlightFence(text: string, lang: string): string {
  const label = lang.trim().split(/\s/)[0]?.toLowerCase() ?? '';
  const grammar = label && Prism.languages[label] ? Prism.languages[label] : null;
  if (!grammar) {
    return `<pre><code>${escapeHtml(text)}</code></pre>`;
  }
  try {
    const inner = Prism.highlight(text, grammar, label);
    return `<pre class="language-${label}"><code class="language-${label}">${inner}</code></pre>`;
  } catch {
    return `<pre><code>${escapeHtml(text)}</code></pre>`;
  }
}

const artifactMarked = new Marked(
  { async: false, gfm: true },
  {
    renderer: {
      code({ text, lang }) {
        return highlightFence(text, lang ?? '');
      },
    },
  }
);

function sanitizeMarkdownHtml(html: string): string {
  return DOMPurify.sanitize(html);
}

function renderMarkdownPreview(markdown: string): string {
  const raw = artifactMarked.parse(markdown) as string;
  return sanitizeMarkdownHtml(raw);
}

type FetchPhase = 'idle' | 'loading' | 'success' | 'error';

/** Markdown Preview tab — not fetch phase. */
type MarkdownPreviewPhase = 'idle' | 'rendering' | 'ready' | 'error' | 'skipped';

/** JSON text is prepared off the commit path; UI shows a loader until `ready`. */
type JsonPreparePhase = 'idle' | 'preparing' | 'ready';

/** Above this size (UTF-16 code units ≈ bytes for ASCII JSON), skip pretty-printing and Prism. */
const LARGE_JSON_CHAR_THRESHOLD = 1024 * 1024;

/**
 * Raw tab: never run full-document `Prism.highlightElement` above this size.
 * Preview tab: skip `marked` (and fence Prism) entirely above this size.
 */
const LARGE_MARKDOWN_CHAR_THRESHOLD = 1024 * 1024;

/** Matches SPEC.md chunk objects in `<name>.json` artifacts. */
type ArtifactChunk = {
  chunk_index: number;
  text: string;
  section_path: string[];
  token_count: number;
  char_count: number;
};

type ArtifactEmbedding = {
  index: number;
  text: string;
  dimensions: number;
};

const CHUNK_EXCERPT_MAX_CHARS = 280;

function ExpandablePreBlock({
  expanded,
  excerpt,
  fullText,
  needsToggle,
  onToggle,
}: {
  expanded: boolean;
  excerpt: string;
  fullText: string;
  needsToggle: boolean;
  onToggle: () => void;
}) {
  const { t } = useTranslation();
  return (
    <>
      <div className={expanded ? styles.chunkTextFull : styles.chunkTextExcerpt}>
        <Text component="pre" size="sm" className={styles.chunkPre}>
          {expanded ? fullText : excerpt}
        </Text>
      </div>
      {needsToggle ? (
        <Button variant="subtle" size="xs" onClick={onToggle}>
          {expanded ? t('artifactViewer.chunkCollapse') : t('artifactViewer.chunkExpand')}
        </Button>
      ) : null}
    </>
  );
}

type ChunksTabState =
  | { kind: 'invalid' }
  | { kind: 'large' }
  | { kind: 'missing' }
  | { kind: 'empty' }
  | { kind: 'ready'; chunks: ArtifactChunk[] };

type VectorsTabState =
  | { kind: 'invalid' }
  | { kind: 'large' }
  | { kind: 'missing' }
  | { kind: 'empty' }
  | { kind: 'ready'; embeddings: ArtifactEmbedding[]; dimensions: number };

type JsonDisplayState = {
  text: string;
  invalid: boolean;
  /** When true, do not run Prism.highlightElement on the JSON block. */
  skipHighlight: boolean;
  /** Shown when the payload is large and left unformatted. */
  largeRaw: boolean;
  chunksState: ChunksTabState;
  vectorsState: VectorsTabState;
};

const EMPTY_JSON_DISPLAY: JsonDisplayState = {
  text: '',
  invalid: false,
  skipHighlight: true,
  largeRaw: false,
  chunksState: { kind: 'invalid' },
  vectorsState: { kind: 'invalid' },
};

function normalizeChunkItem(item: unknown, fallbackIndex: number): ArtifactChunk {
  const o =
    item !== null && typeof item === 'object' && !Array.isArray(item)
      ? (item as Record<string, unknown>)
      : {};
  const text = typeof o.text === 'string' ? o.text : '';
  const section_path = Array.isArray(o.section_path) ? o.section_path.map((x) => String(x)) : [];
  const chunk_index =
    typeof o.chunk_index === 'number' && Number.isFinite(o.chunk_index)
      ? o.chunk_index
      : fallbackIndex;
  const token_count =
    typeof o.token_count === 'number' && Number.isFinite(o.token_count) ? o.token_count : 0;
  const char_count =
    typeof o.char_count === 'number' && Number.isFinite(o.char_count) ? o.char_count : text.length;
  return { chunk_index, text, section_path, token_count, char_count };
}

function chunksStateFromParsedRoot(parsed: unknown): ChunksTabState {
  if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
    return { kind: 'missing' };
  }
  const root = parsed as Record<string, unknown>;
  if (!Object.prototype.hasOwnProperty.call(root, 'chunks')) {
    return { kind: 'missing' };
  }
  const rawChunks = root.chunks;
  if (!Array.isArray(rawChunks)) {
    return { kind: 'missing' };
  }
  if (rawChunks.length === 0) {
    return { kind: 'empty' };
  }
  const chunks = rawChunks.map((item, i) => normalizeChunkItem(item, i));
  return { kind: 'ready', chunks };
}

function vectorsStateFromParsedRoot(parsed: unknown): VectorsTabState {
  if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
    return { kind: 'missing' };
  }
  const root = parsed as Record<string, unknown>;
  if (!Object.prototype.hasOwnProperty.call(root, 'embeddings')) {
    return { kind: 'missing' };
  }
  const rawEmbeddings = root.embeddings;
  if (!Array.isArray(rawEmbeddings)) {
    return { kind: 'missing' };
  }
  if (rawEmbeddings.length === 0) {
    return { kind: 'empty' };
  }
  const dims =
    typeof root.dimensions === 'number' && Number.isFinite(root.dimensions)
      ? root.dimensions
      : 0;
  const embeddings: ArtifactEmbedding[] = rawEmbeddings.map((item, i) => {
    const o =
      item !== null && typeof item === 'object' && !Array.isArray(item)
        ? (item as Record<string, unknown>)
        : {};
    const index =
      typeof o.index === 'number' && Number.isFinite(o.index) ? o.index : i;
    const text = typeof o.text === 'string' ? o.text : '';
    const vec = Array.isArray(o.vector) ? o.vector.length : 0;
    return { index, text, dimensions: vec || dims };
  });
  return { kind: 'ready', embeddings, dimensions: dims };
}

function jsonChunksTabLabel(chunksState: ChunksTabState, t: TFunction): string {
  if (chunksState.kind === 'ready') {
    return t('artifactViewer.tabChunksWithCount', { count: chunksState.chunks.length });
  }
  if (chunksState.kind === 'empty') {
    return t('artifactViewer.tabChunksWithCount', { count: 0 });
  }
  return t('artifactViewer.tabChunks');
}

function jsonVectorsTabLabel(vectorsState: VectorsTabState, t: TFunction): string {
  if (vectorsState.kind === 'ready') {
    return t('artifactViewer.tabVectorsWithCount', { count: vectorsState.embeddings.length });
  }
  if (vectorsState.kind === 'empty') {
    return t('artifactViewer.tabVectorsWithCount', { count: 0 });
  }
  return t('artifactViewer.tabVectors');
}

function artifactDownloadFilename(artifactPath: string, jobFilename: string): string {
  const segment = artifactPath
    .replace(/[/\\]+$/, '')
    .split(/[/\\]/)
    .pop();
  if (segment && segment.length > 0) {
    return segment;
  }
  return jobFilename;
}

function ArtifactDownloadButton({
  path: artifactPath,
  jobFilename,
}: {
  path: string;
  jobFilename: string;
}) {
  const { t } = useTranslation();
  const href = artifactUrl(artifactPath);
  const downloadName = artifactDownloadFilename(artifactPath, jobFilename);
  return (
    <Button
      component="a"
      href={href}
      download={downloadName}
      variant="light"
      color="gray"
      size="sm"
      leftSection={<IconDownload size={16} stroke={1.8} />}
    >
      {t('artifactViewer.download')}
    </Button>
  );
}

type ArtifactViewerErrorBoundaryProps = {
  children: ReactNode;
  fallback: ReactNode;
};

type ArtifactViewerErrorBoundaryState = { hasError: boolean };

class ArtifactViewerErrorBoundary extends Component<
  ArtifactViewerErrorBoundaryProps,
  ArtifactViewerErrorBoundaryState
> {
  state: ArtifactViewerErrorBoundaryState = { hasError: false };

  static getDerivedStateFromError(): ArtifactViewerErrorBoundaryState {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('ArtifactViewerModal render error', error, info.componentStack);
  }

  render(): ReactNode {
    if (this.state.hasError) {
      return this.props.fallback;
    }
    return this.props.children;
  }
}

function ChunkCard({ chunk }: { chunk: ArtifactChunk }) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const needsToggle = chunk.text.length > CHUNK_EXCERPT_MAX_CHARS;
  const excerpt = needsToggle ? `${chunk.text.slice(0, CHUNK_EXCERPT_MAX_CHARS)}…` : chunk.text;
  const sectionLabel =
    chunk.section_path.length > 0
      ? chunk.section_path.join(' › ')
      : t('artifactViewer.chunkSectionNone');

  return (
    <Paper className={styles.chunkCard} withBorder p="sm" radius="md">
      <Stack gap="xs">
        <Group justify="space-between" align="flex-start" wrap="wrap" gap="xs">
          <Text size="sm" fw={600}>
            {t('artifactViewer.chunkIndex', { index: chunk.chunk_index })}
          </Text>
          <Group gap="md" wrap="wrap">
            <Text size="xs" c="dimmed">
              {t('artifactViewer.chunkTokens', { count: chunk.token_count })}
            </Text>
            <Text size="xs" c="dimmed">
              {t('artifactViewer.chunkChars', { count: chunk.char_count })}
            </Text>
          </Group>
        </Group>
        <div>
          <Text size="xs" c="dimmed" mb={4}>
            {t('artifactViewer.chunkSectionLabel')}
          </Text>
          <Text size="sm" className={styles.chunkSectionPath}>
            {sectionLabel}
          </Text>
        </div>
        <ExpandablePreBlock
          expanded={expanded}
          excerpt={excerpt}
          fullText={chunk.text}
          needsToggle={needsToggle}
          onToggle={() => setExpanded((v) => !v)}
        />
      </Stack>
    </Paper>
  );
}

function VectorCard({ embedding }: { embedding: ArtifactEmbedding }) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const needsToggle = embedding.text.length > CHUNK_EXCERPT_MAX_CHARS;
  const excerpt = needsToggle ? `${embedding.text.slice(0, CHUNK_EXCERPT_MAX_CHARS)}…` : embedding.text;

  return (
    <Paper className={styles.chunkCard} withBorder p="sm" radius="md">
      <Stack gap="xs">
        <Group justify="space-between" align="flex-start" wrap="wrap" gap="xs">
          <Text size="sm" fw={600}>
            {t('artifactViewer.vectorIndex', { index: embedding.index })}
          </Text>
          <Text size="xs" c="dimmed">
            {t('artifactViewer.vectorDimensions', { count: embedding.dimensions })}
          </Text>
        </Group>
        {embedding.text ? (
          <ExpandablePreBlock
            expanded={expanded}
            excerpt={excerpt}
            fullText={embedding.text}
            needsToggle={needsToggle}
            onToggle={() => setExpanded((v) => !v)}
          />
        ) : null}
      </Stack>
    </Paper>
  );
}

function ModalLoadingRow({ label }: { label: string }) {
  return (
    <Group justify="center" py="xl" style={{ flex: 1, width: '100%' }}>
      <Loader size="sm" aria-label={label} />
      <Text size="sm" c="dimmed">
        {label}
      </Text>
    </Group>
  );
}

type ArtifactMarkdownBodyProps = {
  t: TFunction;
  markdownTab: string;
  setMarkdownTab: (next: string) => void;
  markdownPreviewPhase: MarkdownPreviewPhase;
  content: string;
  markdownPreviewHtml: string;
  previewHostRef: RefObject<HTMLDivElement | null>;
  rawMarkdownRef: RefObject<HTMLElement | null>;
};

function artifactViewerMarkdownBody({
  t,
  markdownTab,
  setMarkdownTab,
  markdownPreviewPhase,
  content,
  markdownPreviewHtml,
  previewHostRef,
  rawMarkdownRef,
}: ArtifactMarkdownBodyProps): ReactNode {
  return (
    <Stack gap="md" className={styles.body}>
      <Tabs value={markdownTab} onChange={(v) => setMarkdownTab(v ?? 'preview')}>
        <Tabs.List className={styles.tabsList}>
          <Tabs.Tab value="preview">{t('artifactViewer.tabPreview')}</Tabs.Tab>
          <Tabs.Tab value="raw">{t('artifactViewer.tabRaw')}</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="preview" pt="sm">
          {markdownPreviewPhase === 'skipped' ? (
            <Alert variant="light" color="gray" icon={<IconInfoCircle size={18} stroke={1.8} />}>
              {t('artifactViewer.largeMarkdownPreview')}
            </Alert>
          ) : (
            <div className={styles.scrollSurface}>
              {markdownPreviewPhase === 'rendering' ? (
                <Group justify="center" py="xl" style={{ minHeight: 200, width: '100%' }}>
                  <Loader size="sm" aria-label={t('artifactViewer.previewRendering')} />
                  <Text size="sm" c="dimmed">
                    {t('artifactViewer.previewRendering')}
                  </Text>
                </Group>
              ) : null}
              {markdownPreviewPhase === 'error' ? (
                <div className={styles.centered}>
                  <Text size="sm" c="dimmed" ta="center">
                    {t('artifactViewer.previewError')}
                  </Text>
                </div>
              ) : null}
              <div
                ref={previewHostRef}
                className={styles.prose}
                hidden={markdownPreviewPhase !== 'ready' || markdownPreviewHtml.length === 0}
              />
            </div>
          )}
        </Tabs.Panel>
        <Tabs.Panel value="raw" pt="sm">
          <Stack gap="xs">
            {content.length > LARGE_MARKDOWN_CHAR_THRESHOLD ? (
              <Alert variant="light" color="gray" icon={<IconInfoCircle size={18} stroke={1.8} />}>
                {t('artifactViewer.largeMarkdownRaw')}
              </Alert>
            ) : null}
            <div className={styles.scrollSurface}>
              <pre className={styles.codeBlock}>
                <code ref={rawMarkdownRef} />
              </pre>
            </div>
          </Stack>
        </Tabs.Panel>
      </Tabs>
    </Stack>
  );
}

function artifactViewerJsonCardsPanelInner(
  t: TFunction,
  isLlm: boolean,
  chunksState: ChunksTabState,
  vectorsState: VectorsTabState
): ReactNode {
  if (isLlm) {
    if (vectorsState.kind === 'invalid') return null;
    if (vectorsState.kind === 'large') {
      return (
        <Alert variant="light" color="gray" icon={<IconInfoCircle size={18} stroke={1.8} />}>
          {t('artifactViewer.vectorsUnavailableLarge')}
        </Alert>
      );
    }
    if (vectorsState.kind === 'missing') {
      return (
        <div className={styles.centered}>
          <Text size="sm" c="dimmed" ta="center">
            {t('artifactViewer.vectorsMissing')}
          </Text>
        </div>
      );
    }
    if (vectorsState.kind === 'empty') {
      return (
        <div className={styles.centered}>
          <Text size="sm" c="dimmed" ta="center">
            {t('artifactViewer.vectorsEmpty')}
          </Text>
        </div>
      );
    }
    if (vectorsState.kind === 'ready') {
      return (
        <div className={styles.chunkListScroll}>
          {vectorsState.embeddings.map((emb, i) => (
            <VectorCard key={`${emb.index}-${i}`} embedding={emb} />
          ))}
        </div>
      );
    }
    return null;
  }

  if (chunksState.kind === 'invalid') return null;
  if (chunksState.kind === 'large') {
    return (
      <Alert variant="light" color="gray" icon={<IconInfoCircle size={18} stroke={1.8} />}>
        {t('artifactViewer.chunksUnavailableLarge')}
      </Alert>
    );
  }
  if (chunksState.kind === 'missing') {
    return (
      <div className={styles.centered}>
        <Text size="sm" c="dimmed" ta="center">
          {t('artifactViewer.chunksMissing')}
        </Text>
      </div>
    );
  }
  if (chunksState.kind === 'empty') {
    return (
      <div className={styles.centered}>
        <Text size="sm" c="dimmed" ta="center">
          {t('artifactViewer.chunksEmpty')}
        </Text>
      </div>
    );
  }
  if (chunksState.kind === 'ready') {
    return (
      <div className={styles.chunkListScroll}>
        {chunksState.chunks.map((chunk, i) => (
          <ChunkCard key={`${chunk.chunk_index}-${i}`} chunk={chunk} />
        ))}
      </div>
    );
  }
  return null;
}

type ArtifactJsonBodyProps = {
  t: TFunction;
  mode: WorkerMode;
  jsonTab: string;
  setJsonTab: (next: string) => void;
  jsonDisplay: JsonDisplayState;
  jsonCodeRef: RefObject<HTMLElement | null>;
};

function artifactViewerJsonBody({
  t,
  mode,
  jsonTab,
  setJsonTab,
  jsonDisplay,
  jsonCodeRef,
}: ArtifactJsonBodyProps): ReactNode {
  const isLlm = mode === 'llm';
  const chunksState = jsonDisplay.chunksState;
  const vectorsState = jsonDisplay.vectorsState;
  const cardTabValue = isLlm ? 'vectors' : 'chunks';
  const cardsPanelInner = artifactViewerJsonCardsPanelInner(t, isLlm, chunksState, vectorsState);
  const showCardTab = isLlm
    ? !jsonDisplay.invalid && vectorsState.kind !== 'invalid'
    : !jsonDisplay.invalid;
  const cardTabLabel = isLlm
    ? jsonVectorsTabLabel(vectorsState, t)
    : jsonChunksTabLabel(chunksState, t);

  return (
    <Stack gap="md" className={styles.body}>
      <Tabs value={jsonTab} onChange={(v) => setJsonTab(v ?? cardTabValue)}>
        <Tabs.List className={styles.tabsList}>
          {showCardTab ? <Tabs.Tab value={cardTabValue}>{cardTabLabel}</Tabs.Tab> : null}
          <Tabs.Tab value="raw">{t('artifactViewer.tabRaw')}</Tabs.Tab>
        </Tabs.List>
        {showCardTab ? (
          <Tabs.Panel value={cardTabValue} pt="sm">
            {cardsPanelInner}
          </Tabs.Panel>
        ) : null}
        <Tabs.Panel value="raw" pt="sm">
          <Stack gap="xs">
            {jsonDisplay.largeRaw ? (
              <Alert variant="light" color="gray" icon={<IconInfoCircle size={18} stroke={1.8} />}>
                {t('artifactViewer.largeJsonRaw')}
              </Alert>
            ) : null}
            {jsonDisplay.invalid ? (
              <Text size="sm" c="dimmed" className={styles.invalidJsonNote}>
                {t('artifactViewer.invalidJsonNote')}
              </Text>
            ) : null}
            <div className={styles.scrollSurface}>
              <pre className={styles.codeBlock}>
                <code ref={jsonCodeRef} />
              </pre>
            </div>
          </Stack>
        </Tabs.Panel>
      </Tabs>
    </Stack>
  );
}

type ArtifactModalBodyProps = {
  t: TFunction;
  opened: boolean;
  path: string;
  phase: FetchPhase;
  fetchError: string | null;
  kind: ArtifactViewerKind;
  mode: WorkerMode;
  content: string;
  isEmptySuccess: boolean;
  markdownTab: string;
  setMarkdownTab: (next: string) => void;
  markdownPreviewPhase: MarkdownPreviewPhase;
  markdownPreviewHtml: string;
  previewHostRef: RefObject<HTMLDivElement | null>;
  rawMarkdownRef: RefObject<HTMLElement | null>;
  jsonPreparePhase: JsonPreparePhase;
  jsonTab: string;
  setJsonTab: (next: string) => void;
  jsonDisplay: JsonDisplayState;
  jsonCodeRef: RefObject<HTMLElement | null>;
};

function artifactViewerModalBody(p: ArtifactModalBodyProps): ReactNode {
  if (!p.opened || !p.path) {
    return null;
  }
  if (p.phase === 'loading') {
    return <ModalLoadingRow label={p.t('artifactViewer.loading')} />;
  }
  if (p.phase === 'error') {
    return (
      <Paper className={styles.body} p="md" withBorder radius="sm">
        <Text size="sm" c="red">
          {p.t('artifactViewer.loadError', { message: p.fetchError ?? '—' })}
        </Text>
      </Paper>
    );
  }
  if (p.isEmptySuccess) {
    return (
      <div className={styles.centered}>
        <Text size="sm" c="dimmed" ta="center">
          {p.t('artifactViewer.empty')}
        </Text>
      </div>
    );
  }
  if (p.kind === 'markdown') {
    return artifactViewerMarkdownBody({
      t: p.t,
      markdownTab: p.markdownTab,
      setMarkdownTab: p.setMarkdownTab,
      markdownPreviewPhase: p.markdownPreviewPhase,
      content: p.content,
      markdownPreviewHtml: p.markdownPreviewHtml,
      previewHostRef: p.previewHostRef,
      rawMarkdownRef: p.rawMarkdownRef,
    });
  }
  if (p.jsonPreparePhase === 'preparing') {
    return <ModalLoadingRow label={p.t('artifactViewer.preparing')} />;
  }
  return artifactViewerJsonBody({
    t: p.t,
    mode: p.mode,
    jsonTab: p.jsonTab,
    setJsonTab: p.setJsonTab,
    jsonDisplay: p.jsonDisplay,
    jsonCodeRef: p.jsonCodeRef,
  });
}

export function ArtifactViewerModal({
  opened,
  onClose,
  kind,
  path,
  filename,
  mode = 'txt',
}: ArtifactViewerModalProps) {
  const { t } = useTranslation();
  const [phase, setPhase] = useState<FetchPhase>('idle');
  const [content, setContent] = useState('');
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [markdownTab, setMarkdownTab] = useState('preview');
  const defaultCardTab = mode === 'llm' ? 'vectors' : 'chunks';
  const [jsonTab, setJsonTab] = useState(defaultCardTab);
  const [markdownPreviewPhase, setMarkdownPreviewPhase] = useState<MarkdownPreviewPhase>('idle');
  const [markdownPreviewHtml, setMarkdownPreviewHtml] = useState('');
  const [jsonDisplay, setJsonDisplay] = useState<JsonDisplayState>(EMPTY_JSON_DISPLAY);
  const [jsonPreparePhase, setJsonPreparePhase] = useState<JsonPreparePhase>('idle');

  const previewHostRef = useRef<HTMLDivElement>(null);
  const rawMarkdownRef = useRef<HTMLElement>(null);
  const jsonCodeRef = useRef<HTMLElement>(null);
  const markdownPreviewTokenRef = useRef(0);
  const rawMarkdownHighlightTokenRef = useRef(0);
  const jsonDisplayTokenRef = useRef(0);
  const openedRef = useRef(opened);
  const pathRef = useRef(path);
  const markdownTabRef = useRef(markdownTab);
  openedRef.current = opened;
  pathRef.current = path;
  markdownTabRef.current = markdownTab;

  useEffect(() => {
    if (opened) {
      return;
    }
    markdownPreviewTokenRef.current += 1;
    rawMarkdownHighlightTokenRef.current += 1;
    jsonDisplayTokenRef.current += 1;
    setMarkdownPreviewPhase('idle');
    setMarkdownPreviewHtml('');
    setPhase('idle');
    setContent('');
    setFetchError(null);
    setMarkdownTab('preview');
    setJsonTab(defaultCardTab);
    setJsonDisplay(EMPTY_JSON_DISPLAY);
    setJsonPreparePhase('idle');
    const host = previewHostRef.current;
    if (host) {
      host.innerHTML = '';
    }
  }, [opened, defaultCardTab]);

  useEffect(() => {
    if (!opened || !path) {
      return;
    }
    markdownPreviewTokenRef.current += 1;
    rawMarkdownHighlightTokenRef.current += 1;
    jsonDisplayTokenRef.current += 1;
    setPhase('loading');
    setContent('');
    setFetchError(null);
    setMarkdownPreviewPhase('idle');
    setMarkdownPreviewHtml('');
    setJsonDisplay(EMPTY_JSON_DISPLAY);
    setJsonPreparePhase('idle');
    setMarkdownTab('preview');
    setJsonTab(defaultCardTab);
    const host = previewHostRef.current;
    if (host) {
      host.innerHTML = '';
    }
  }, [opened, path]);

  useEffect(() => {
    if (!opened || !path) {
      return;
    }

    const ac = new AbortController();

    const url = artifactUrl(path, mode);
    workerFetch(url, { signal: ac.signal })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(String(response.status));
        }
        return response.text();
      })
      .then((text) => {
        setContent(text);
        setPhase('success');
      })
      .catch((err: unknown) => {
        if (ac.signal.aborted) {
          return;
        }
        const message = err instanceof Error ? err.message : String(err);
        setFetchError(message);
        setPhase('error');
      });

    return () => ac.abort();
  }, [opened, path]);

  useEffect(() => {
    if (
      !opened ||
      kind !== 'markdown' ||
      phase !== 'success' ||
      markdownTab !== 'preview' ||
      !content.trim()
    ) {
      markdownPreviewTokenRef.current += 1;
      setMarkdownPreviewPhase('idle');
      setMarkdownPreviewHtml('');
      return;
    }

    const pathAtStart = path;
    if (content.length > LARGE_MARKDOWN_CHAR_THRESHOLD) {
      setMarkdownPreviewPhase('skipped');
      setMarkdownPreviewHtml('');
      return () => {
        markdownPreviewTokenRef.current += 1;
      };
    }

    const token = ++markdownPreviewTokenRef.current;
    setMarkdownPreviewPhase('rendering');
    setMarkdownPreviewHtml('');

    scheduleYieldedTask(() => {
      if (!openedRef.current || pathRef.current !== pathAtStart) {
        return;
      }
      if (token !== markdownPreviewTokenRef.current) {
        return;
      }
      if (markdownTabRef.current !== 'preview') {
        return;
      }
      try {
        const html = renderMarkdownPreview(content);
        if (!openedRef.current || pathRef.current !== pathAtStart) {
          return;
        }
        if (token !== markdownPreviewTokenRef.current) {
          return;
        }
        if (markdownTabRef.current !== 'preview') {
          return;
        }
        setMarkdownPreviewHtml(html);
        setMarkdownPreviewPhase('ready');
      } catch {
        if (!openedRef.current || pathRef.current !== pathAtStart) {
          return;
        }
        if (token !== markdownPreviewTokenRef.current) {
          return;
        }
        setMarkdownPreviewPhase('error');
      }
    });

    return () => {
      markdownPreviewTokenRef.current += 1;
    };
  }, [opened, kind, phase, content, markdownTab, path]);

  useEffect(() => {
    const host = previewHostRef.current;
    if (!host || !opened || kind !== 'markdown' || markdownTab !== 'preview') {
      return;
    }
    if (!openedRef.current || pathRef.current !== path) {
      return;
    }
    if (markdownPreviewPhase === 'ready' && markdownPreviewHtml) {
      host.innerHTML = markdownPreviewHtml;
      return;
    }
    host.innerHTML = '';
  }, [opened, kind, path, markdownTab, markdownPreviewPhase, markdownPreviewHtml]);

  useEffect(() => {
    if (!opened || kind !== 'json' || phase !== 'success') {
      jsonDisplayTokenRef.current += 1;
      setJsonDisplay(EMPTY_JSON_DISPLAY);
      setJsonPreparePhase('idle');
      return;
    }
    if (!content.trim()) {
      jsonDisplayTokenRef.current += 1;
      setJsonDisplay(EMPTY_JSON_DISPLAY);
      setJsonPreparePhase('idle');
      return;
    }

    const pathAtStart = path;
    const token = ++jsonDisplayTokenRef.current;

    if (content.length > LARGE_JSON_CHAR_THRESHOLD) {
      setJsonDisplay({
        text: content,
        invalid: false,
        skipHighlight: true,
        largeRaw: true,
        chunksState: { kind: 'large' },
        vectorsState: { kind: 'large' },
      });
      setJsonPreparePhase('ready');
      return () => {
        jsonDisplayTokenRef.current += 1;
      };
    }

    setJsonPreparePhase('preparing');
    setJsonDisplay(EMPTY_JSON_DISPLAY);

    const snapshotContent = content;
    scheduleYieldedTask(() => {
      if (!openedRef.current || pathRef.current !== pathAtStart) {
        return;
      }
      if (token !== jsonDisplayTokenRef.current) {
        return;
      }
      try {
        const parsed: unknown = JSON.parse(snapshotContent);
        const text = JSON.stringify(parsed, null, 2);
        if (!openedRef.current || pathRef.current !== pathAtStart) {
          return;
        }
        if (token !== jsonDisplayTokenRef.current) {
          return;
        }
        const chunksState = chunksStateFromParsedRoot(parsed);
        const vectorsState = vectorsStateFromParsedRoot(parsed);
        setJsonDisplay({
          text,
          invalid: false,
          skipHighlight: false,
          largeRaw: false,
          chunksState,
          vectorsState,
        });
      } catch {
        if (!openedRef.current || pathRef.current !== pathAtStart) {
          return;
        }
        if (token !== jsonDisplayTokenRef.current) {
          return;
        }
        setJsonDisplay({
          text: snapshotContent,
          invalid: true,
          skipHighlight: false,
          largeRaw: false,
          chunksState: { kind: 'invalid' },
          vectorsState: { kind: 'invalid' },
        });
        setJsonTab('raw');
      }
      if (!openedRef.current || pathRef.current !== pathAtStart) {
        return;
      }
      if (token !== jsonDisplayTokenRef.current) {
        return;
      }
      setJsonPreparePhase('ready');
    });

    return () => {
      jsonDisplayTokenRef.current += 1;
    };
  }, [opened, kind, phase, content, path]);

  useEffect(() => {
    if (!opened || kind !== 'markdown' || phase !== 'success' || markdownTab !== 'raw') {
      return;
    }
    const el = rawMarkdownRef.current;
    if (!el) {
      return;
    }

    const pathAtStart = path;
    const snapshot = rawMarkdownHighlightTokenRef.current;
    el.textContent = content;

    const large = content.length > LARGE_MARKDOWN_CHAR_THRESHOLD;
    if (large) {
      el.removeAttribute('class');
      return () => {
        rawMarkdownHighlightTokenRef.current += 1;
      };
    }

    el.className = 'language-markdown';
    const raf = requestAnimationFrame(() => {
      if (!openedRef.current || pathRef.current !== pathAtStart) {
        return;
      }
      if (rawMarkdownHighlightTokenRef.current !== snapshot) {
        return;
      }
      if (!el.isConnected) {
        return;
      }
      try {
        Prism.highlightElement(el);
      } catch {
        el.textContent = content;
        el.removeAttribute('class');
      }
    });

    return () => {
      cancelAnimationFrame(raf);
      rawMarkdownHighlightTokenRef.current += 1;
    };
  }, [opened, kind, phase, content, markdownTab, path]);

  useEffect(() => {
    if (
      !opened ||
      kind !== 'json' ||
      phase !== 'success' ||
      jsonPreparePhase !== 'ready' ||
      !jsonDisplay.text ||
      jsonTab !== 'raw'
    ) {
      return;
    }
    const el = jsonCodeRef.current;
    if (!el) {
      return;
    }

    const pathAtStart = path;
    const highlightToken = jsonDisplayTokenRef.current;

    if (jsonDisplay.skipHighlight) {
      el.textContent = jsonDisplay.text;
      el.removeAttribute('class');
      return;
    }

    el.textContent = jsonDisplay.text;
    el.className = 'language-json';
    const raf = requestAnimationFrame(() => {
      if (!openedRef.current || pathRef.current !== pathAtStart) {
        return;
      }
      if (highlightToken !== jsonDisplayTokenRef.current) {
        return;
      }
      if (!el.isConnected) {
        return;
      }
      try {
        Prism.highlightElement(el);
      } catch {
        el.textContent = jsonDisplay.text;
        el.removeAttribute('class');
      }
    });
    return () => cancelAnimationFrame(raf);
  }, [opened, kind, phase, jsonPreparePhase, jsonDisplay, path, jsonTab]);

  useEffect(() => {
    if (kind !== 'json' || !jsonDisplay.invalid) {
      return;
    }
    if (jsonTab === 'chunks' || jsonTab === 'vectors') {
      setJsonTab('raw');
    }
  }, [kind, jsonDisplay.invalid, jsonTab]);

  const title =
    kind === 'markdown'
      ? t('artifactViewer.titleMarkdown', { filename })
      : mode === 'llm'
        ? t('artifactViewer.titleVectors', { filename })
        : t('artifactViewer.titleJson', { filename });

  const isEmptySuccess = opened && phase === 'success' && !content.trim();

  const body = artifactViewerModalBody({
    t,
    opened,
    path,
    phase,
    fetchError,
    kind,
    mode,
    content,
    isEmptySuccess,
    markdownTab,
    setMarkdownTab,
    markdownPreviewPhase,
    markdownPreviewHtml,
    previewHostRef,
    rawMarkdownRef,
    jsonPreparePhase,
    jsonTab,
    setJsonTab,
    jsonDisplay,
    jsonCodeRef,
  });

  const errorFallback = (
    <Paper className={styles.body} p="md" withBorder radius="sm">
      <Text size="sm" c="red">
        {t('artifactViewer.renderError')}
      </Text>
    </Paper>
  );

  return (
    <Modal opened={opened} onClose={onClose} title={title} size="xl">
      <Stack gap="md" className={styles.shell}>
        {opened && path ? <ArtifactDownloadButton path={path} jobFilename={filename} /> : null}
        <ArtifactViewerErrorBoundary key={`${opened}-${path}-${kind}`} fallback={errorFallback}>
          {body}
        </ArtifactViewerErrorBoundary>
      </Stack>
    </Modal>
  );
}
