#!/usr/bin/env node

import { spawnSync } from 'node:child_process';

/**
 * Run the shared lint pipeline for Python + UI in a predictable order.
 * Keep commands split to reduce memory pressure and make failures obvious.
 */
const STEPS = [
  {
    name: 'ruff check',
    command: 'uv',
    args: [
      'run',
      'ruff',
      'check',
      '--fix',
      'core/src/',
      'worker/src/',
      'worker-llm/src/',
      'tests/',
    ],
  },
  {
    name: 'ruff format',
    command: 'uv',
    args: [
      'run',
      'ruff',
      'format',
      'core/src/',
      'worker/src/',
      'worker-llm/src/',
      'tests/',
    ],
  },
  {
    name: 'mypy core',
    command: 'uv',
    args: ['run', 'mypy', 'core/src/docrunr'],
    env: { MYPY_CACHE_DIR: '.mypy_cache/core' },
  },
  {
    name: 'mypy worker',
    command: 'uv',
    args: ['run', 'mypy', 'worker/src/docrunr_worker'],
    env: { MYPY_CACHE_DIR: '.mypy_cache/worker' },
  },
  {
    name: 'ui lint',
    command: 'pnpm',
    args: ['-C', 'ui', 'run', 'lint'],
  },
  {
    name: 'ui format',
    command: 'pnpm',
    args: ['-C', 'ui', 'run', 'format'],
  },
  {
    name: 'ui typecheck',
    command: 'pnpm',
    args: ['-C', 'ui', 'run', 'typecheck'],
  },
];

function runStep(step) {
  console.log(`\n[lint] ${step.name}`);
  const result = spawnSync(step.command, step.args, {
    stdio: 'inherit',
    env: {
      ...process.env,
      ...(step.env ?? {}),
    },
  });

  if (typeof result.status === 'number') {
    return result.status;
  }
  return 1;
}

for (const step of STEPS) {
  const code = runStep(step);
  if (code !== 0) {
    console.error(`\n[lint] failed at: ${step.name}`);
    process.exit(code);
  }
}

console.log('\n[lint] all checks passed');
