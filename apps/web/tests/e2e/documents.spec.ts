import path from 'node:path';
import { expect, test, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

async function connect(page: Page) {
  await page.addInitScript(() => {
    // Exercise the standard folder-input fallback using actual files from disk.
    Object.defineProperty(window, 'showDirectoryPicker', { value: undefined });
  });
  await page.goto('/');
  // Audit final colors, not a mid-transition frame while changing system theme.
  await page.addStyleTag({ content: '*, *::before, *::after { transition: none !important; animation: none !important; }' });
  await page.getByRole('button', { name: 'Connect to local development server' }).click();
  await expect(page.getByRole('heading', { name: 'Find the files on this device' })).toBeVisible();
}
async function search(page: Page, query: string) {
  const response = page.waitForResponse(r => r.url().endsWith('/search') && r.request().method() === 'POST');
  await page.getByRole('textbox', { name: 'Describe the document' }).fill(query);
  await page.getByRole('textbox', { name: 'Describe the document' }).press('Enter');
  const result = await response;
  expect(result.ok()).toBeTruthy();
  return result.json();
}
async function accessible(page: Page) {
  for (const colorScheme of ['light', 'dark'] as const) {
    await page.emulateMedia({ colorScheme });
    const { violations } = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
    expect(violations.map(v => ({ theme: colorScheme, id: v.id, nodes: v.nodes.map(n => n.target) }))).toEqual([]);
  }
  await page.emulateMedia({ colorScheme: 'light' });
}

test('folder → real OCR → search → relevant page, duplicates, isolation and deletion', async ({ page, browser }, info) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await connect(page);
  await accessible(page);
  const chooser = page.waitForEvent('filechooser');
  await page.getByRole('button', { name: 'Allow online indexing & choose folder' }).click();
  await (await chooser).setFiles(path.join(process.env.MEMORA_E2E_STATE!, 'fixtures'));
  await expect(page.getByText('3 completed', { exact: true })).toBeVisible({ timeout: 90_000 });
  await expect(page.getByText('unsupported.xyz: Unsupported format.', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Rescan', exact: true }).click();
  await expect(page.getByRole('status').filter({ hasText: 'checked' })).toContainText('3 unchanged');
  await page.getByRole('link', { name: 'Search completed documents now' }).click();

  const timings: number[] = [];
  let memoryId = '';
  for (const query of ['my Aadhaar', 'mera adhaar', 'my adhaaar card', 'मेरा आधार कार्ड', 'माझे आधार कार्ड']) {
    const start = performance.now();
    const result = await search(page, query);
    timings.push(performance.now() - start);
    expect(result.results[0].filename).toBe('2344646563rt.pdf');
    expect(result.results[0].page).toBe(2);
    expect(result.results.filter((r: { document_type: string }) => r.document_type === 'aadhaar')).toHaveLength(1);
    memoryId = result.results[0].memory_id;
  }
  // Upload the identical bytes after the original has completed: filesystem order
  // must not decide which original filename the rank-one assertion expects.
  const duplicate = await page.evaluate(async id => {
    const base = localStorage.getItem('memora.server_url');
    const headers = { Authorization: `Bearer ${localStorage.getItem('memora.device_token')}` };
    const original = await fetch(`${base}/memories/${id}/file`, { headers });
    const form = new FormData();
    form.append('file', await original.blob(), 'copy.pdf');
    form.append('device_path', 'snapshot/e2e-copy/copy.pdf');
    const response = await fetch(`${base}/index/jobs`, { method: 'POST', headers, body: form });
    if (!response.ok) throw new Error(`Duplicate upload failed: ${response.status}`);
    return response.json();
  }, memoryId);
  await expect.poll(() => page.evaluate(async id => {
    const response = await fetch(`${localStorage.getItem('memora.server_url')}/index/jobs/${id}`, {
      headers: { Authorization: `Bearer ${localStorage.getItem('memora.device_token')}` },
    });
    return (await response.json()).status;
  }, duplicate.id)).toBe('completed');
  const deduplicated = await search(page, 'my Aadhaar');
  expect(deduplicated.results.filter((r: { document_type: string }) => r.document_type === 'aadhaar')).toHaveLength(1);
  expect(deduplicated.results[0].memory_id).toBe(memoryId);
  await accessible(page);
  for (const [name, width, height] of [['phone', 375, 812], ['tablet', 768, 1024], ['laptop', 1366, 900]] as const) {
    await page.setViewportSize({ width, height });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
    await info.attach(`${name}-search`, { body: await page.screenshot(), contentType: 'image/png' });
  }
  await page.getByRole('button').filter({ hasText: '2344646563rt.pdf' }).click();
  await expect(page.getByRole('dialog').getByRole('img')).toBeVisible();
  await expect(page.getByRole('dialog')).toContainText('Page 2 / 2');
  await page.getByLabel('Zoom').focus();
  await page.keyboard.press('Tab');
  expect(await page.getByRole('dialog').evaluate(element => element.contains(document.activeElement))).toBeTruthy();
  await page.getByLabel('Zoom').selectOption('150');
  await page.getByRole('button', { name: 'Previous', exact: true }).click();
  await expect(page.getByRole('dialog')).toContainText('Page 1 / 2');
  await accessible(page);
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.getByRole('button').filter({ hasText: '2344646563rt.pdf' })).toBeFocused();
  const marksheet = await search(page, 'माझी गुणपत्रिका');
  expect(marksheet.results[0].filename).toBe('8349201.pdf');
  await search(page, 'my passport');
  await expect(page.getByText('No matching document found.', { exact: true })).toBeVisible();

  const second = await browser.newContext();
  try {
    const other = await second.newPage();
    await connect(other);
    await other.getByRole('link', { name: 'Find', exact: true }).last().click();
    const empty = await search(other, 'my Aadhaar');
    expect(empty.results).toHaveLength(0);
    await expect(other.getByText('No matching document found.', { exact: true })).toBeVisible();
    const denied = await other.evaluate(async id => {
      const response = await fetch(`${localStorage.getItem('memora.server_url')}/memories/${id}/file`, {
        headers: { Authorization: `Bearer ${localStorage.getItem('memora.device_token')}` },
      });
      return response.status;
    }, memoryId);
    expect(denied).toBe(404);
  } finally { await second.close(); }

  const deleted = await page.evaluate(async id => {
    const response = await fetch(`${localStorage.getItem('memora.server_url')}/memories/${id}`, {
      method: 'DELETE', headers: { Authorization: `Bearer ${localStorage.getItem('memora.device_token')}` },
    });
    return response.status;
  }, memoryId);
  expect(deleted).toBe(204);
  expect((await search(page, 'my Aadhaar')).results).toHaveLength(0);
  expect(errors).toEqual([]);
  await info.attach('synthetic-search-timings.json', {
    body: JSON.stringify({ note: process.env.MEMORA_E2E_LEXICAL === '1' ? 'Local synthetic corpus; real lexical-only retrieval, not hosted latency.' : 'Local synthetic corpus; deterministic embedding doubles, not production latency.', milliseconds: timings }),
    contentType: 'application/json',
  });
});

test('failed searches explain the error and recover on retry', async ({ page }) => {
  await connect(page);
  await page.getByRole('link', { name: 'Find', exact: true }).last().click();
  await page.route('**/search', route => route.fulfill({ status: 503, body: '{"detail":"Unavailable"}', contentType: 'application/json' }));
  await page.getByRole('textbox', { name: 'Describe the document' }).fill('my Aadhaar');
  await page.getByRole('textbox', { name: 'Describe the document' }).press('Enter');
  await expect(page.getByText('Search is unavailable.', { exact: true })).toBeVisible();
  await page.unroute('**/search');
  await search(page, 'my Aadhaar');
  await expect(page.getByText('No matching document found.', { exact: true })).toBeVisible();
});

test('restored browser without folder permission cannot claim a successful rescan', async ({ page }) => {
  await connect(page);
  // Consent is device-specific; simulate reload after a prior consent, without handles.
  await page.evaluate(() => {
    const url = localStorage.getItem('memora.server_url');
    const token = localStorage.getItem('memora.device_token');
    localStorage.setItem(`memora.online-consent:${url}:${token?.slice(0, 16)}`, 'yes');
  });
  await page.reload();
  await page.getByRole('button', { name: 'Rescan', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Choose the folder again');
});
