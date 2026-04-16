/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_APP_VERSION: string;
  readonly VITE_WORKER_MODE?: 'txt' | 'llm';
  readonly VITE_LLM_API_BASE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
