import { after, test } from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'vite';

const server = await createServer({ configFile: false, optimizeDeps: { noDiscovery: true, include: [] }, server: { middlewareMode: true }, appType: 'custom' });
after(() => server.close());
const { maskIdentifiers, containsIdentifier, verhoeffValid } =
  await server.ssrLoadModule('/../../packages/core/src/masking.ts');

// Expected outputs come from apps/api/src/memora/services/masking.py, so the two
// implementations are pinned to the same behaviour.
const parity = [
  ['Aadhaar 2345 6789 0124 issued', 'Aadhaar [AADHAAR_NUMBER] issued', 1],
  ['number 234567890124 here', 'number [AADHAAR_NUMBER] here', 1],
  ['dashed 2345-6789-0124', 'dashed [AADHAAR_NUMBER]', 1],
  ['receipt id 234567890125 keep', 'receipt id 234567890125 keep', 0],
  ['PAN ABCDE1234F and abcde1234f', 'PAN [PAN_NUMBER] and abcde1234f', 1],
  ['phone 9876543210 stays', 'phone 9876543210 stays', 0],
  ['both 234567890124 and ABCDE1234F', 'both [AADHAAR_NUMBER] and [PAN_NUMBER]', 2],
  ['glued 9234567890124', 'glued 9234567890124', 0],
  ['नाम यश ABCDE1234F पता पुणे', 'नाम यश [PAN_NUMBER] पता पुणे', 1],
];

for (const [input, output, count] of parity) {
  test(`matches the server: ${input}`, () => {
    assert.deepEqual(maskIdentifiers(input), { text: output, masked: count });
    assert.equal(containsIdentifier(maskIdentifiers(input).text), false);
  });
}

test('verhoeff accepts a valid number and rejects a one-digit change', () => {
  assert.equal(verhoeffValid('234567890124'), true);
  assert.equal(verhoeffValid('234567890125'), false);
  assert.equal(verhoeffValid('12ab'), false);
});
