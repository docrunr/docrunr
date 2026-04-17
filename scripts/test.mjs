#!/usr/bin/env node
/**
 * Test entrypoints for DocRunr (unit, samples, integration). Invoked from VS Code tasks or CLI.
 *
 * Usage:
 *   node ./scripts/test.mjs unit [pytest -k filter]
 *   node ./scripts/test.mjs samples <includeGlob>
 *   node ./scripts/test.mjs integration <txt|minio|llm> [sampleSource] [sampleCount]
 *
 * Integration modes: ``txt`` runs ``tests/integration`` excluding ``llm_jobs`` (no ``llm_profile`` queue tests).
 * ``minio`` runs the full integration directory (TXT + LLM e2e). ``llm`` runs only ``test_llm_jobs_e2e.py``.
 */

import { spawnSync } from 'node:child_process';
import { access, readFile } from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(SCRIPT_DIR, '..');

async function loadDotEnv(filePath) {
  try {
    await access(filePath);
  } catch {
    return {};
  }

  const content = await readFile(filePath, 'utf8');
  /** @type {Record<string, string>} */
  const values = {};

  for (const rawLine of content.split(/\r?\n/u)) {
    const line = rawLine.trim();
    if (!line || line.startsWith('#')) {
      continue;
    }

    const idx = line.indexOf('=');
    if (idx <= 0) {
      continue;
    }

    const key = line.slice(0, idx).trim();
    let value = line.slice(idx + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    values[key] = value;
  }

  return values;
}

function printHelp() {
  console.log(`Usage:
  node ./scripts/test.mjs unit [filter]     filter is passed to pytest -k (default: run all)
  node ./scripts/test.mjs samples <include>
  node ./scripts/test.mjs integration <txt|minio|llm> [sampleSource] [sampleCount]
    txt: integration minus llm_jobs | minio: full integration | llm: LLM e2e only
`);
}

function runUv(args, env) {
  const r = spawnSync('uv', ['run', ...args], {
    cwd: REPO_ROOT,
    stdio: 'inherit',
    env: env ?? process.env,
  });
  if (r.status !== 0 && r.status != null) {
    process.exit(r.status);
  }
  if (r.error) {
    console.error(r.error);
    process.exit(1);
  }
}

async function cmdUnit(filter) {
  const pytestArgs = ['pytest', 'tests/core/', 'tests/worker/', 'tests/worker_llm/', '-v'];
  if (filter && filter !== '*') {
    pytestArgs.push('-k', filter);
  }
  runUv(pytestArgs);
}

function cmdSamples(include) {
  runUv([
    'docrunr',
    'tests/samples/',
    '--out',
    '.out',
    '--verbose',
    '--include',
    include || '*',
  ]);
}

/**
 * @param {'txt' | 'minio' | 'llm'} mode
 * @param {string} [sampleSource]
 * @param {string} [sampleCount]
 */
async function cmdIntegration(mode, sampleSource, sampleCount) {
  const dotenv = await loadDotEnv(path.join(REPO_ROOT, '.env'));
  /** @type {NodeJS.ProcessEnv} */
  const env = { ...dotenv, ...process.env };

  env.RABBITMQ_HOST = '127.0.0.1';

  const healthPort = env.HEALTH_PORT || '8080';
  env.DOCRUNR_HEALTH_URL = `http://127.0.0.1:${healthPort}/health`;

  if (mode === 'txt') {
    env.DOCRUNR_INTEGRATION_STORAGE = 'local';
  } else if (mode === 'minio') {
    env.DOCRUNR_INTEGRATION_STORAGE = 'minio';
    const minioPort = env.MINIO_PORT || '9000';
    env.DOCRUNR_INTEGRATION_MINIO_ENDPOINT = `127.0.0.1:${minioPort}`;
  } else if (mode === 'llm') {
    env.DOCRUNR_INTEGRATION_STORAGE = 'local';
    env.DOCRUNR_LLM_HEALTH_URL = 'http://127.0.0.1:8081/health';
    // Forward profile selection env var (populated from .env or caller's environment).
    // INTEGRATION_LLM_PROFILES — comma-separated allowlist; one item pins a single profile
    const pool = env.INTEGRATION_LLM_PROFILES?.trim();
    if (pool) {
      console.log(`[test:integration:llm] profile pool: ${pool} (random pick)`);
    } else {
      console.log('[test:integration:llm] profile pool: live LiteLLM /models list (random pick)');
    }
  } else {
    console.error(`Unknown integration mode: ${mode} (use txt, minio, or llm)`);
    process.exit(1);
  }

  if (sampleSource) {
    env.INTEGRATION_SAMPLE_SOURCE = sampleSource;
  }

  /** @type {string[]} */
  let pytestArgs;
  if (mode === 'llm') {
    pytestArgs = ['pytest', 'tests/integration/test_llm_jobs_e2e.py', '-v', '-s'];
  } else if (mode === 'txt') {
    pytestArgs = ['pytest', 'tests/integration', '-v', '-m', 'not llm_jobs'];
  } else {
    // minio — full integration suite (TXT paths + LLM e2e when worker-llm is up)
    pytestArgs = ['pytest', 'tests/integration', '-v'];
  }

  const n = sampleCount?.trim();
  if (n && n !== '0' && n !== '*') {
    pytestArgs.push(`--integration-sample-limit=${n}`);
  }

  runUv(pytestArgs, env);
}

async function main() {
  const [, , command, ...rest] = process.argv;

  if (command === 'help' || command === '-h' || command === '--help') {
    printHelp();
    process.exit(0);
  }

  if (!command) {
    printHelp();
    process.exit(1);
  }

  if (command === 'unit') {
    await cmdUnit(rest[0]);
    return;
  }

  if (command === 'samples') {
    cmdSamples(rest[0]);
    return;
  }

  if (command === 'integration') {
    const [mode, sampleSource = 'samples', sampleCount = '5'] = rest;
    if (!mode) {
      console.error('integration requires a mode: txt, minio, or llm');
      process.exit(1);
    }
    await cmdIntegration(
      /** @type {'txt' | 'minio' | 'llm'} */ (mode),
      sampleSource,
      sampleCount,
    );
    return;
  }

  printHelp();
  process.exit(1);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
