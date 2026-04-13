/// <reference types="vitest/config" />

import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/**
 * Release builds can override the committed app version via VITE_APP_VERSION.
 * Otherwise use the checked-in UI package version that the release script updates.
 */
function resolveAppVersion(): string {
  const fromEnv = process.env.VITE_APP_VERSION?.trim();
  if (fromEnv) {
    return fromEnv.startsWith('v') ? fromEnv.slice(1) : fromEnv;
  }

  try {
    const packageJson = JSON.parse(
      readFileSync(path.resolve(__dirname, 'package.json'), 'utf8')
    ) as { version?: string };
    return packageJson.version?.trim() || '0.0.0';
  } catch {
    return '0.0.0';
  }
}

const appVersion = resolveAppVersion();

export default defineConfig({
  define: {
    'import.meta.env.VITE_APP_VERSION': JSON.stringify(appVersion),
  },
  plugins: [react()],
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/health': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/stats': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
    },
  },
});
