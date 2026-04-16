#!/usr/bin/env node
/**
 * Docker compose / image builds for DocRunr. Invoked from VS Code tasks or CLI.
 *
 * Usage:
 *   node ./scripts/docker.mjs run [local|minio]
 *   node ./scripts/docker.mjs build [all|txt|llm]
 */

import { spawnSync } from 'node:child_process';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(SCRIPT_DIR, '..');

/** @param {'local' | 'minio'} profile */
function composeFileArgs(profile) {
  if (profile === 'minio') {
    return [
      '-f',
      'docker-compose.base.yml',
      '-f',
      'docker-compose.llm.yml',
      '-f',
      'docker-compose.ollama.yml',
      '-f',
      'docker-compose.minio.yml',
    ];
  }
  return [
    '-f',
    'docker-compose.base.yml',
    '-f',
    'docker-compose.local.yml',
    '-f',
    'docker-compose.llm.yml',
    '-f',
    'docker-compose.ollama.yml',
  ];
}

function runCompose(profile) {
  const files = composeFileArgs(profile);
  const up = spawnSync(
    'docker',
    ['compose', ...files, 'up', '-d', '--build', '--remove-orphans'],
    { cwd: REPO_ROOT, stdio: 'inherit' },
  );
  if (up.status !== 0 && up.status != null) {
    process.exit(up.status);
  }
  if (up.error) {
    console.error(up.error);
    process.exit(1);
  }
  const ps = spawnSync('docker', ['compose', ...files, 'ps'], {
    cwd: REPO_ROOT,
    stdio: 'inherit',
  });
  process.exit(ps.status ?? (ps.error ? 1 : 0));
}

/** @param {'all' | 'txt' | 'llm'} target */
function runBuild(target) {
  const steps =
    target === 'all'
      ? [
          { args: ['docker', 'build', '-t', 'docrunr:latest', '.'] },
          { args: ['docker', 'build', '-f', 'Dockerfile.llm', '-t', 'docrunr-llm:latest', '.'] },
        ]
      : target === 'llm'
        ? [{ args: ['docker', 'build', '-f', 'Dockerfile.llm', '-t', 'docrunr-llm:latest', '.'] }]
        : [{ args: ['docker', 'build', '-t', 'docrunr:latest', '.'] }];

  for (const { args } of steps) {
    const r = spawnSync(args[0], args.slice(1), {
      cwd: REPO_ROOT,
      stdio: 'inherit',
    });
    if (r.status !== 0 && r.status != null) {
      process.exit(r.status);
    }
    if (r.error) {
      console.error(r.error);
      process.exit(1);
    }
  }
}

function printHelp() {
  console.log(`Usage:
  node ./scripts/docker.mjs run [local|minio]   default: local
  node ./scripts/docker.mjs build [all|txt|llm]   default: all
`);
}

function main() {
  const [, , command, arg] = process.argv;

  if (command === 'help' || command === '-h' || command === '--help') {
    printHelp();
    process.exit(0);
  }

  if (!command) {
    printHelp();
    process.exit(1);
  }

  if (command === 'run') {
    const profile = arg === 'minio' ? 'minio' : 'local';
    if (arg && arg !== 'local' && arg !== 'minio') {
      console.error(`Unknown profile: ${arg} (use local or minio)`);
      process.exit(1);
    }
    runCompose(profile);
    return;
  }

  if (command === 'build') {
    const target = arg === 'txt' || arg === 'llm' ? arg : arg === 'all' || !arg ? 'all' : null;
    if (arg && !['all', 'txt', 'llm'].includes(arg)) {
      console.error(`Unknown build target: ${arg} (use all, txt, or llm)`);
      process.exit(1);
    }
    runBuild(target ?? 'all');
    return;
  }

  printHelp();
  process.exit(command ? 1 : 0);
}

main();
