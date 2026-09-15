const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const { mkdir, readFile } = require('node:fs/promises');
const path = require('node:path');
const crypto = require('node:crypto');
const { chromium } = require('playwright');

const root = path.resolve(__dirname, '..');
const origin = 'http://127.0.0.1:4173';
const output = path.join(root, 'test-results');
const server = spawn('python3', ['-m', 'http.server', '4173', '--bind', '127.0.0.1'], { cwd: root, stdio: 'ignore' });
let browser;

async function visibleImagesReady(page) {
  await page.waitForFunction(() => [...document.querySelectorAll('.tile img')].filter(img => {
    const rect = img.getBoundingClientRect();
    return rect.top < innerHeight && rect.bottom > 0;
  }).every(img => img.complete && img.naturalWidth > 0));
}

(async () => {
  await mkdir(output, { recursive: true });
  let ready = false;
  for (let attempt = 0; attempt < 50; attempt++) {
    try { ready = (await fetch(origin)).ok; } catch {}
    if (ready) break;
    await new Promise(resolve => setTimeout(resolve, 200));
  }
  assert(ready, 'Local gallery server did not start');
  browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, permissions: ['clipboard-read', 'clipboard-write'] });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(origin);
  await page.waitForSelector('.tile');
  assert.equal(await page.locator('.tile').count(), 60);
  assert.match(await page.locator('#stats').innerText(), /2,073/);
  assert.match(await page.locator('#stats').innerText(), /6,016/);
  await visibleImagesReady(page);
  await page.screenshot({ path: path.join(output, 'desktop.png') });
  await page.locator('#load-more').click();
  assert.equal(await page.locator('.tile').count(), 120);
  await page.locator('#search').fill('in3 betalen');
  assert.equal(await page.locator('.tile').count(), 1);
  await page.locator('.tile').click();
  assert.equal(await page.locator('#detail-path').inputValue(), 'payment-methods/in3.png');
  await page.waitForFunction(() => document.getElementById('detail-image').naturalWidth === 256);
  await page.locator('#copy-path').click();
  assert.equal(await page.evaluate(() => navigator.clipboard.readText()), 'payment-methods/in3.png');
  const downloadEvent = page.waitForEvent('download');
  await page.locator('#download-icon').click();
  const download = await downloadEvent;
  assert.equal(download.suggestedFilename(), 'in3.png');
  const bytes = await readFile(await download.path());
  const catalog = JSON.parse(await readFile(path.join(root, 'catalog/payment-methods.json')));
  assert.equal(crypto.createHash('sha256').update(bytes).digest('hex'), catalog.find(x => x.id === 'pmt_in3').sha256);
  await page.keyboard.press('Escape');
  assert.equal(await page.locator('#detail').evaluate(d => d.open), false);
  await page.locator('#search').fill('');
  await page.locator('[data-category="cards"]').click();
  await page.locator('#source-filter').selectOption('generated');
  assert.match(await page.locator('#result-count').innerText(), /^5,308 assets/);
  await page.locator('#source-filter').selectOption('all');
  assert.match(await page.locator('#result-count').innerText(), /^6,016 assets/);
  const ratio = await page.locator('.tile img').first().evaluate(img => { const b = img.getBoundingClientRect(); return b.width/b.height; });
  assert(Math.abs(ratio-406/256) < .02, 'Card previews must preserve their aspect ratio');
  await page.locator('[data-category="payment-methods"]').click();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.evaluate(() => scrollTo(0, 0));
  await visibleImagesReady(page);
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, 'Mobile must not overflow horizontally');
  await page.screenshot({ path: path.join(output, 'mobile.png') });
  await page.locator('[data-background="dark"]').click();
  assert.equal(await page.locator('html').getAttribute('data-preview'), 'dark');
  await page.locator('#search').fill('in3 betalen');
  await page.locator('.tile').click();
  await page.waitForFunction(() => document.getElementById('detail-image').naturalWidth === 256);
  await page.screenshot({ path: path.join(output, 'mobile-detail.png') });
  await page.keyboard.press('Escape');
  await page.locator('#search').fill('this-icon-does-not-exist-4837');
  assert.equal(await page.locator('#empty').isVisible(), true);
  await page.route('**/catalog/cards.json', route => route.fulfill({ status: 503, body: 'Unavailable' }));
  await page.reload();
  await page.waitForSelector('#error:not([hidden])');
  assert.match(await page.locator('#error').innerText(), /503/);
  assert.deepEqual(errors, []);
  console.log('Gallery passed: desktop/mobile layout, PNG previews, pagination, global search, source/category filters, card proportions, details, copy, download hash and error states.');
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
}).finally(async () => {
  await browser?.close();
  server.kill('SIGTERM');
});
