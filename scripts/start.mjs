// Run the two application processes under one factory-server service.
// Development in the managed workspace uses supervisor instead of this entrypoint.
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { existsSync } from 'node:fs';
const require = createRequire(import.meta.url);
const localPython = process.platform === 'win32' ? '.venv\\Scripts\\python.exe' : '.venv/bin/python';
if (existsSync('.env')) process.loadEnvFile('.env');
for (const key of ['MONGO_URL', 'DB_NAME', 'NEXT_PUBLIC_BASE_URL', 'JWT_SECRET', 'ADMIN_EMAIL', 'ADMIN_PASSWORD']) {
  if (!process.env[key]) throw new Error(`Missing required configuration: ${key}`);
}
if (!process.env.BACKEND_SOCKET && !process.env.BACKEND_URL) throw new Error('Missing required configuration: BACKEND_SOCKET or BACKEND_URL');
for (const file of ['.next/BUILD_ID', '.next/prerender-manifest.json', '.next/routes-manifest.json']) {
  if (!existsSync(file)) {
    throw new Error(`Missing Next.js production build file: ${file}. Run "yarn build" before "yarn start".`);
  }
}
const children = [];
let closing = false;
const shutdown = signal => {
  if (closing) return;
  closing = true;
  for (const child of children) child.kill(signal || 'SIGTERM');
  const timeout = setTimeout(() => { for (const child of children) child.kill('SIGKILL'); process.exit(1); }, 10000);
  timeout.unref();
};
const launch = (command, args) => {
  const child = spawn(command, args, { stdio: 'inherit', env: process.env });
  children.push(child);
  child.on('error', error => { console.error('Application process failed:', error.message); process.exitCode = 1; shutdown(); });
  child.on('exit', code => { if (!closing) { process.exitCode = code || 1; shutdown(); } });
};

const backendIsReachable = async () => {
  if (!process.env.BACKEND_URL) return false;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 1000);
  try {
    await fetch(process.env.BACKEND_URL, { signal: controller.signal });
    return true;
  } catch {
    return false;
  } finally {
    clearTimeout(timeout);
  }
};

if (process.env.BACKEND_SOCKET || !(await backendIsReachable())) {
  launch(process.env.PYTHON_EXECUTABLE || (existsSync(localPython) ? localPython : 'python3'), ['backend/run.py']);
} else {
  console.log(`Using existing backend at ${process.env.BACKEND_URL}`);
}
launch(process.execPath, [require.resolve('next/dist/bin/next'), 'start']);
for (const signal of ['SIGTERM', 'SIGINT']) process.on(signal, () => shutdown(signal));
