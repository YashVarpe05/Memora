import { after, test } from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'vite';

const server = await createServer({ configFile: false, optimizeDeps: { noDiscovery: true, include: [] }, server: { middlewareMode: true }, appType: 'custom' });
after(() => server.close());
const { enrollConfig, enrollDevice } = await server.ssrLoadModule('/src/platform/enroll.ts');

const reply = (status, body) => async () => new Response(JSON.stringify(body ?? {}), { status });
const config = { server: 'https://memora.example.com/api/', secret: 's3cret' };

test('config needs both a server and a secret', () => {
  assert.equal(enrollConfig({}), null);
  assert.equal(enrollConfig({ VITE_MEMORA_SERVER: 'https://x/api' }), null);
  assert.deepEqual(enrollConfig({ VITE_MEMORA_SERVER: ' https://x/api ', VITE_MEMORA_ENROLL_SECRET: ' k ' }), { server: 'https://x/api', secret: 'k' });
});

test('a good secret returns the token and the normalised base, and posts the secret in the body only', async () => {
  let seen;
  const result = await enrollDevice(config, async (url, init) => { seen = { url, init }; return new Response(JSON.stringify({ device_token: 'tok' }), { status: 200 }); });
  assert.deepEqual(result, { ok: true, url: 'https://memora.example.com/api', token: 'tok' });
  assert.equal(seen.url, 'https://memora.example.com/api/pair/enroll');
  assert.equal(seen.init.method, 'POST');
  assert.equal(JSON.parse(seen.init.body).secret, 's3cret');
  assert.ok(!seen.url.includes('s3cret'), 'the secret must never be in the URL');
});

test('each failure is classified, never thrown', async () => {
  assert.deepEqual(await enrollDevice(config, reply(401)), { ok: false, reason: 'rejected' });
  assert.deepEqual(await enrollDevice(config, reply(429)), { ok: false, reason: 'locked' });
  assert.deepEqual(await enrollDevice(config, reply(404)), { ok: false, reason: 'disabled' });
  assert.deepEqual(await enrollDevice(config, async () => { throw new TypeError('network'); }), { ok: false, reason: 'unreachable' });
  assert.deepEqual(await enrollDevice(config, reply(200, {})), { ok: false, reason: 'rejected' });
});

test('plain HTTP is refused except for localhost, and credentials or queries are refused', async () => {
  const never = async () => { throw new Error('must not call the network'); };
  for (const server of ['http://memora.example.com/api', 'https://u:p@memora.example.com/api', 'https://x/api?a=1', 'not a url']) {
    assert.deepEqual(await enrollDevice({ ...config, server }, never), { ok: false, reason: 'blocked' });
  }
  const local = await enrollDevice({ ...config, server: 'http://127.0.0.1:5175/api' }, reply(200, { device_token: 't' }));
  assert.equal(local.ok, true);
});
