#!/usr/bin/env node
/**
 * Docker compose / image builds for DocRunr. Invoked from VS Code tasks or CLI.
 *
 * Usage:
 *   node ./scripts/docker.mjs run [local|s3]
 *   node ./scripts/docker.mjs build [all|txt|llm|api]
 */

import { spawnSync } from 'node:child_process';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';
import { freeListenPorts } from './free-listen-ports.mjs';

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(SCRIPT_DIR, '..');
const COMPOSE_HOST_PORTS = [8080, 8081, 8082, 4000];
const S3_HOST_PORTS = [8333, 9333];

/** @param {'local' | 's3'} profile */
function composeFileArgs(profile) {
  if (profile === 's3') {
    return [
      '-f',
      'docker-compose.base.yml',
      '-f',
      'docker-compose.llm.yml',
      '-f',
      'docker-compose.api.yml',
      '-f',
      'docker-compose.ollama.yml',
      '-f',
      'docker-compose.seaweedfs.yml',
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
    'docker-compose.api.yml',
    '-f',
    'docker-compose.ollama.yml',
  ];
}

async function runCompose(profile) {
  const ports = profile === 's3' ? [...COMPOSE_HOST_PORTS, ...S3_HOST_PORTS] : COMPOSE_HOST_PORTS;
  await freeListenPorts(ports, { logPrefix: 'docker', skipDockerListeners: true });

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

/** @param {'all' | 'txt' | 'llm' | 'api'} target */
function runBuild(target) {
  const steps =
    target === 'all'
      ? [
          { args: ['docker', 'build', '-t', 'docrunr:latest', '.'] },
          { args: ['docker', 'build', '-f', 'Dockerfile.llm', '-t', 'docrunr-llm:latest', '.'] },
          { args: ['docker', 'build', '-f', 'Dockerfile.api', '-t', 'docrunr-api:latest', '.'] },
        ]
      : target === 'llm'
        ? [{ args: ['docker', 'build', '-f', 'Dockerfile.llm', '-t', 'docrunr-llm:latest', '.'] }]
        : target === 'api'
          ? [{ args: ['docker', 'build', '-f', 'Dockerfile.api', '-t', 'docrunr-api:latest', '.'] }]
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
  node ./scripts/docker.mjs run [local|s3]   default: local
  node ./scripts/docker.mjs build [all|txt|llm|api]   default: all
`);
}

async function main() {
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
    const profile = arg === 's3' ? 's3' : 'local';
    if (arg && arg !== 'local' && arg !== 's3') {
      console.error(`Unknown profile: ${arg} (use local or s3)`);
      process.exit(1);
    }
    await runCompose(profile);
    return;
  }

  if (command === 'build') {
    const target = ['txt', 'llm', 'api'].includes(arg) ? arg : arg === 'all' || !arg ? 'all' : null;
    if (arg && !['all', 'txt', 'llm', 'api'].includes(arg)) {
      console.error(`Unknown build target: ${arg} (use all, txt, llm, or api)`);
      process.exit(1);
    }
    runBuild(target ?? 'all');
    return;
  }

  printHelp();
  process.exit(command ? 1 : 0);
}

main().catch((error) => {
  console.error(`[docker] ${error instanceof Error ? error.message : String(error)}`);
  process.exit(1);
});
