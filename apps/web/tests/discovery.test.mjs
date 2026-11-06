import { after, test } from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'vite';

const server = await createServer({ configFile: false, optimizeDeps: { noDiscovery: true, include: [] }, server: { middlewareMode: true }, appType: 'custom' });
after(() => server.close());
const { BrowserFileDiscovery } = await server.ssrLoadModule('/src/platform/discovery.browser.ts');

function folder(id, permission = 'granted', files = ['document.txt']) {
  return { id, handle: {
    queryPermission: async () => permission,
    async *values() {
      for (const name of files) yield { kind: 'file', name,
        getFile: async () => new File([id], name, { type: 'text/plain' }) };
    },
  } };
}
function discovery(folders) {
  return new BrowserFileDiscovery({ readState: async () => folders, writeState: async () => {} });
}
async function collect(scanner) {
  const files = [];
  for await (const file of scanner.scan()) files.push(file);
  return files;
}
test('restores all permitted roots and reads files from each', async () => {
  const scanner = discovery([folder('one'), folder('revoked', 'prompt'), folder('two')]);
  assert.equal(await scanner.restore(), true);
  assert.deepEqual(scanner.pathPrefixes, ['browser/one/', 'browser/two/']);
  assert.deepEqual((await collect(scanner)).map(f => f.path),
    ['browser/one/document.txt', 'browser/two/document.txt']);
  assert.equal(new TextDecoder().decode(await scanner.read('browser/two/document.txt')), 'two');
});
test('missing permission throws instead of producing a successful empty scan', async () => {
  const scanner = discovery([folder('revoked', 'prompt')]);
  assert.equal(await scanner.restore(), false);
  await assert.rejects(() => collect(scanner), /Choose the folder again/);
});
test('an accessible empty folder can reconcile deleted files', async () => {
  const scanner = discovery([folder('empty', 'granted', [])]);
  assert.equal(await scanner.restore(), true);
  assert.deepEqual(await collect(scanner), []);
  assert.deepEqual(scanner.pathPrefixes, ['browser/empty/']);
});
test('enumeration yields incrementally and can stop before reading remaining files', async () => {
  let reads = 0;
  const root = folder('large');
  root.handle.values = async function* () {
    for (let i = 0; i < 1000; i++) yield { kind: 'file', name: `${i}.txt`,
      getFile: async () => { reads++; return new File(['text'], `${i}.txt`); } };
  };
  const scanner = discovery([root]);
  await scanner.restore();
  for await (const file of scanner.scan()) { assert.equal(file.name, '0.txt'); break; }
  assert.equal(reads, 1);
});
