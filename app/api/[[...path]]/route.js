import { request as httpRequest } from 'node:http';
import { Readable } from 'node:stream';
import { NextResponse } from 'next/server';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
const MAX_BODY = 2_000_000;
const blocked = new Set(['connection', 'keep-alive', 'transfer-encoding', 'upgrade', 'proxy-authenticate', 'proxy-authorization', 'te', 'trailer']);

async function handle(request) {
  const parts = [];
  let size = 0;
  if (request.body) {
    const reader = request.body.getReader();
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > MAX_BODY) { await reader.cancel(); return NextResponse.json({ detail: 'Request exceeds the 2 MB limit.' }, { status: 413 }); }
      parts.push(Buffer.from(value));
    }
  }
  const headers = {};
  // Never forward client-provided proxy/trust headers to the private backend.
  for (const key of ['cookie', 'content-type', 'origin', 'x-csrf-token', 'accept', 'user-agent']) {
    const value = request.headers.get(key);
    if (value) headers[key] = value;
  }
  headers['content-length'] = String(size);
  const socketPath = process.env.BACKEND_SOCKET;
  const backendUrl = process.env.BACKEND_URL;
  if (!socketPath && !backendUrl) return NextResponse.json({ detail: 'Backend connection is not configured.' }, { status: 503 });
  try {
    return await new Promise((resolve, reject) => {
      const target = backendUrl ? new URL(`${request.nextUrl.pathname}${request.nextUrl.search}`, backendUrl) : null;
      const options = target
        ? { hostname: target.hostname, port: target.port || 80, path: `${target.pathname}${target.search}`, method: request.method, headers, timeout: 60000 }
        : { socketPath, path: `${request.nextUrl.pathname}${request.nextUrl.search}`, method: request.method, headers, timeout: 60000 };
      const upstream = httpRequest(options, response => {
        const outHeaders = new Headers();
        for (const [name, values] of Object.entries(response.headers)) {
          if (blocked.has(name) || values === undefined) continue;
          for (const value of Array.isArray(values) ? values : [values]) outHeaders.append(name, value);
        }
        outHeaders.set('Cache-Control', 'private, no-store');
        resolve(new Response(request.method === 'HEAD' || [204, 304].includes(response.statusCode) ? null : Readable.toWeb(response), { status: response.statusCode, headers: outHeaders }));
      });
      upstream.on('timeout', () => upstream.destroy(new Error('Backend timeout')));
      upstream.on('error', reject);
      const abort = () => upstream.destroy();
      request.signal.addEventListener('abort', abort, { once: true });
      upstream.on('close', () => request.signal.removeEventListener('abort', abort));
      upstream.end(Buffer.concat(parts));
    });
  } catch (error) {
    console.error('Private backend unavailable:', error.code || error.message);
    return NextResponse.json({ detail: 'The workspace is temporarily unavailable. Please try again.' }, { status: 503 });
  }
}
export const GET = handle;
export const POST = handle;
export const PUT = handle;
export const PATCH = handle;
export const DELETE = handle;
export const HEAD = handle;
export const OPTIONS = handle;
