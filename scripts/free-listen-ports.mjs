import { spawn, spawnSync } from 'node:child_process';
import process from 'node:process';
import { setTimeout as delay } from 'node:timers/promises';

/**
 * @param {number[]} ports
 * @param {{ logPrefix?: string, skipDockerListeners?: boolean }} [options]
 */
export async function freeListenPorts(ports, options = {}) {
  const logPrefix = options.logPrefix ?? 'dev';
  const skipDockerListeners = options.skipDockerListeners === true;
  for (const port of ports) {
    await freeListenPort(port, { logPrefix, skipDockerListeners });
  }
}

/**
 * @param {number} port
 * @param {{ logPrefix: string, skipDockerListeners: boolean }} options
 */
async function freeListenPort(port, options) {
  const pids = await listListenPids(port, options.skipDockerListeners, options.logPrefix);
  if (pids.length === 0) {
    return;
  }

  console.log(`[${options.logPrefix}] freeing port ${port} (pid ${pids.join(', ')})`);
  for (const pid of pids) {
    killPid(pid, 'SIGTERM');
  }

  const deadline = Date.now() + 4000;
  while (Date.now() < deadline) {
    const remaining = await listListenPids(port, options.skipDockerListeners, options.logPrefix);
    if (remaining.length === 0) {
      return;
    }
    await delay(150);
  }

  const leftover = await listListenPids(port, options.skipDockerListeners, options.logPrefix);
  for (const pid of leftover) {
    killPid(pid, 'SIGKILL');
  }

  const stillHeld = await listListenPids(port, options.skipDockerListeners, options.logPrefix);
  if (stillHeld.length > 0) {
    throw new Error(`port ${port} still in use by pid ${stillHeld.join(', ')}`);
  }
}

function killPid(pid, signal) {
  if (pid === process.pid) {
    return;
  }
  try {
    process.kill(pid, signal);
  } catch (error) {
    if (error && typeof error === 'object' && 'code' in error && error.code === 'ESRCH') {
      return;
    }
    throw error;
  }
}

/**
 * @param {number} port
 * @param {boolean} skipDockerListeners
 */
async function listListenPids(port, skipDockerListeners, logPrefix) {
  let stdout = '';
  let code = 1;
  try {
    const result = await capture('lsof', ['-nP', `-iTCP:${port}`, '-sTCP:LISTEN', '-t']);
    stdout = result.stdout;
    code = result.code;
  } catch (error) {
    if (error && typeof error === 'object' && 'code' in error && error.code === 'ENOENT') {
      console.warn(`[${logPrefix}] lsof not found; cannot free occupied ports automatically`);
      return [];
    }
    throw error;
  }

  if (code !== 0 || !stdout.trim()) {
    return [];
  }

  const pids = [
    ...new Set(
      stdout
        .split(/\s+/u)
        .map((value) => Number.parseInt(value, 10))
        .filter((pid) => Number.isInteger(pid) && pid > 0 && pid !== process.pid),
    ),
  ];

  if (!skipDockerListeners) {
    return pids;
  }

  return pids.filter((pid) => !isDockerListener(pid));
}

function isDockerListener(pid) {
  const result = spawnSync('ps', ['-p', String(pid), '-o', 'comm='], {
    encoding: 'utf8',
  });
  const comm = (result.stdout || '').trim().toLowerCase();
  return comm.includes('docker');
}

function capture(command, args) {
  return new Promise((resolve, reject) => {
    let stdout = '';
    const child = spawn(command, args, {
      stdio: ['ignore', 'pipe', 'ignore'],
    });
    child.on('error', (error) => reject(error));
    if (child.stdout) {
      child.stdout.setEncoding('utf8');
      child.stdout.on('data', (chunk) => {
        stdout += chunk;
      });
    }
    child.on('exit', (code, signal) => {
      resolve({ code: typeof code === 'number' ? code : signal ? 1 : 0, stdout });
    });
  });
}
