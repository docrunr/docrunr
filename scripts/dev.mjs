#!/usr/bin/env node

import { spawn } from 'node:child_process';
import { access, mkdir, readFile } from 'node:fs/promises';
import { hostname as osHostname } from 'node:os';
import path from 'node:path';
import process from 'node:process';
import { setTimeout as delay } from 'node:timers/promises';
import { fileURLToPath } from 'node:url';

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(SCRIPT_DIR, '..');
const WORKER_HEALTH_URL = 'http://127.0.0.1:8080/health';
const WORKER_LLM_HEALTH_URL = 'http://127.0.0.1:8081/health';
const LITELLM_HEALTH_URL = 'http://127.0.0.1:4000/health/liveliness';
const UI_HOST = '127.0.0.1';
const UI_PORT = 5173;
const UI_URL = `http://${UI_HOST}:${UI_PORT}`;

const LLM_MODE = !process.argv.includes('--no-llm');

/** @type {import('node:child_process').ChildProcess[]} */
const children = [];

process.on('SIGINT', () => shutdown(130));
process.on('SIGTERM', () => shutdown(143));

async function main() {
  if (process.argv.includes('--help') || process.argv.includes('-h')) {
    printHelp();
    process.exit(0);
  }

  await ensureRabbitmqHealthy();
  if (LLM_MODE) {
    await ensureLitellmHealthy();
  }

  const worker = startProcess('worker', 'uv', ['run', 'docrunr-worker'], {
    env: await buildWorkerEnv(),
  });

  const workerLlm = LLM_MODE
    ? startProcess('worker-llm', 'uv', ['run', 'docrunr-worker-llm'], {
        env: await buildWorkerLlmEnv(),
      })
    : null;

  try {
    const healthWaits = [waitForHttp(WORKER_HEALTH_URL, 90_000, 'worker API')];
    if (workerLlm) {
      healthWaits.push(waitForHttp(WORKER_LLM_HEALTH_URL, 90_000, 'worker-llm API'));
    }
    await Promise.all(healthWaits);
  } catch (error) {
    stopProcess(worker.child);
    if (workerLlm) stopProcess(workerLlm.child);
    throw error;
  }

  const ui = startProcess('ui', 'pnpm', [
    '-C',
    'ui',
    'run',
    'dev',
    '--host',
    UI_HOST,
    '--port',
    String(UI_PORT),
    '--strictPort',
  ]);

  try {
    await waitForHttp(UI_URL, 120_000, 'UI dev server');
  } catch (error) {
    stopProcess(ui.child);
    stopProcess(worker.child);
    if (workerLlm) stopProcess(workerLlm.child);
    throw error;
  }

  /** @type {Promise<{name: string, code: number}>[]} */
  const exits = [
    worker.exit.then((code) => ({ name: 'worker', code })),
    ui.exit.then((code) => ({ name: 'ui', code })),
  ];
  if (workerLlm) {
    exits.push(workerLlm.exit.then((code) => ({ name: 'worker-llm', code })));
  }

  const first = await Promise.race(exits);

  if (first.name !== 'worker') stopProcess(worker.child);
  if (first.name !== 'ui') stopProcess(ui.child);
  if (workerLlm && first.name !== 'worker-llm') stopProcess(workerLlm.child);

  process.exit(first.code);
}

function printHelp() {
  console.log('Usage: node ./scripts/dev.mjs [--no-llm]');
  console.log('Starts RabbitMQ, worker, worker-llm, LiteLLM, and UI.');
  console.log('Expects Ollama running on the host (brew services).');
  console.log();
  console.log('Options:');
  console.log('  --no-llm   Skip LiteLLM proxy and worker-llm.');
}

async function buildWorkerEnv() {
  const fromEnvFile = await loadDotEnv(path.join(REPO_ROOT, '.env'));
  const dataRoot = path.join(REPO_ROOT, '.data');

  await mkdir(path.join(dataRoot, 'input'), { recursive: true });
  await mkdir(path.join(dataRoot, 'output'), { recursive: true });
  await mkdir(path.join(dataRoot, replicaId()), { recursive: true });

  return {
    ...process.env,
    ...fromEnvFile,
    RABBITMQ_HOST: 'localhost',
    STORAGE_BASE_PATH: dataRoot,
    SQLITE_BASE_PATH: dataRoot,
  };
}

async function buildWorkerLlmEnv() {
  const fromEnvFile = await loadDotEnv(path.join(REPO_ROOT, '.env'));
  const dataRoot = path.join(REPO_ROOT, '.data');

  return {
    ...process.env,
    ...fromEnvFile,
    RABBITMQ_HOST: 'localhost',
    STORAGE_BASE_PATH: dataRoot,
    SQLITE_BASE_PATH: dataRoot,
    LITELLM_BASE_URL: 'http://localhost:4000',
    HEALTH_PORT: '8081',
  };
}

async function ensureRabbitmqHealthy() {
  await runChecked('docker', ['compose', 'up', '-d', 'rabbitmq'], 'start rabbitmq');

  const cid = (await captureChecked('docker', ['compose', 'ps', '-q', 'rabbitmq'], 'resolve rabbitmq container id')).trim();
  if (!cid) {
    throw new Error('RabbitMQ container id is empty');
  }

  const deadline = Date.now() + 90_000;
  while (Date.now() < deadline) {
    const inspection = await capture('docker', [
      'inspect',
      '-f',
      '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}',
      cid,
    ]);
    if (inspection.code !== 0) {
      await delay(1000);
      continue;
    }
    const status = inspection.stdout.trim();

    if (status === 'healthy') {
      await runChecked('docker', ['compose', 'ps', 'rabbitmq'], 'rabbitmq status');
      return;
    }

    await delay(1000);
  }

  throw new Error('rabbitmq not healthy after 90s');
}

async function ensureLitellmHealthy() {
  await runChecked('docker', ['compose', 'up', '-d', 'litellm'], 'start litellm');
  await waitForHttp(LITELLM_HEALTH_URL, 60_000, 'LiteLLM proxy');
}

function startProcess(name, command, args, options = {}) {
  const child = spawn(command, args, {
    cwd: REPO_ROOT,
    env: options.env ?? process.env,
    stdio: 'inherit',
  });

  children.push(child);

  child.on('error', (error) => {
    console.error(`[dev] failed to start ${name}: ${error.message}`);
  });

  const exit = new Promise((resolve) => {
    child.on('exit', (code, signal) => {
      resolve(typeof code === 'number' ? code : signal ? 1 : 0);
    });
  });

  return { child, exit };
}

async function runChecked(command, args, label) {
  const code = await run(command, args, { stdio: 'inherit' });
  if (code !== 0) {
    throw new Error(`Command failed (${label}): ${command} ${args.join(' ')}`);
  }
}

async function captureChecked(command, args, label) {
  const output = await capture(command, args);
  if (output.code !== 0) {
    throw new Error(`Command failed (${label}): ${command} ${args.join(' ')}`);
  }
  return output.stdout;
}

async function capture(command, args) {
  let stdout = '';
  const code = await run(command, args, {
    stdio: ['ignore', 'pipe', 'ignore'],
    onStdout: (chunk) => {
      stdout += chunk;
    },
  });
  return { code, stdout };
}

function run(command, args, options) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd: REPO_ROOT,
      env: process.env,
      stdio: options.stdio,
    });

    child.on('error', (error) => reject(error));

    if (options.stdio[1] === 'pipe' && child.stdout) {
      child.stdout.setEncoding('utf8');
      child.stdout.on('data', (chunk) => options.onStdout?.(chunk));
    }

    child.on('exit', (code, signal) => {
      resolve(typeof code === 'number' ? code : signal ? 1 : 0);
    });
  });
}

async function waitForHttp(url, timeoutMs, label) {
  const deadline = Date.now() + timeoutMs;

  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok) {
        return;
      }
    } catch {
      // retry
    }
    await delay(1000);
  }

  throw new Error(`${label} not ready at ${url} after ${timeoutMs / 1000}s`);
}

function replicaId() {
  const value = process.env.HOSTNAME?.trim() || process.env.COMPUTERNAME?.trim() || osHostname().trim();
  const cleaned = value.replaceAll('/', '_');
  return cleaned || 'local';
}

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
    if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1);
    }
    values[key] = value;
  }

  return values;
}

function stopProcess(child) {
  if (!child || child.killed) {
    return;
  }
  child.kill('SIGTERM');
}

function shutdown(code) {
  for (const child of children) {
    stopProcess(child);
  }
  process.exit(code);
}

main().catch((error) => {
  console.error(`[dev] ${error instanceof Error ? error.message : String(error)}`);
  shutdown(1);
});
