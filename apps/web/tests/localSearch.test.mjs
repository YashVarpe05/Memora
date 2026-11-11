import { after, test } from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'vite';

const server = await createServer({ configFile: false, optimizeDeps: { noDiscovery: true, include: [] }, server: { middlewareMode: true }, appType: 'custom' });
after(() => server.close());
const { toSearchResponse } = await server.ssrLoadModule('/src/platform/localSearch.ts');

const hit = (over = {}) => ({ id: 7, uri: 'content://x/7', name: '2344646563rt.pdf', mime: 'application/pdf', size: 10,
  title: '2344646563rt', docType: 'aadhaar', snippet: 'आधार', page: 1, score: 1003.2, lexical: true, typeMatch: true, ...over });

test('no hits is a refusal, not an error', () => {
  const body = toSearchResponse([]);
  assert.equal(body.refused, true);
  assert.equal(body.results.length, 0);
  assert.equal(body.stage1_failed, false);
});

test('a hit keeps its meaningless filename, gets a readable label and a rank', () => {
  const [first, second] = toSearchResponse([hit(), hit({ id: 8, docType: null, typeMatch: false, mime: 'image/jpeg', name: 'a.jpg' })]).results;
  assert.equal(first.filename, '2344646563rt.pdf');
  assert.equal(first.document_label, 'Aadhaar card');
  assert.equal(first.source_type, 'pdf');
  assert.equal(first.rank, 1);
  assert.equal(first.memory_id, '7');
  assert.equal(second.source_type, 'image');
  assert.equal(second.document_label, null);
  assert.equal(second.rank, 2);
});

test('nothing on the phone is ever labelled closest in meaning', () => {
  assert.equal(toSearchResponse([hit({ lexical: false, typeMatch: true })]).results[0].uncertain, false);
});
