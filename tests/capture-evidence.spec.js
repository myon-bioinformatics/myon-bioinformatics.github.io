const { test, expect } = require('@playwright/test');
const { promisify } = require('node:util');
const execFile = promisify(require('node:child_process').execFile);
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
test('capture CLI records all modes and tools with verifiable hashes', async ({ baseURL }, info) => {
  test.setTimeout(120000);
  const output = info.outputPath('evidence');
  await execFile(process.env.PYTHON || 'python3', ['scripts/capture_portfolio_evidence.py',
    '--base-url', baseURL, '-o', output], { timeout: 100000 });
  const meta = JSON.parse(fs.readFileSync(path.join(output, 'meta.json'), 'utf8'));
  expect(meta.captured_count).toBe(11);
  expect(meta.records.filter(r => r.name.startsWith('portfolio_')).map(r => r.mode).sort())
    .toEqual(['modern','github-like','xml-like','json','markdown'].sort());
  for (const record of meta.records) {
    expect(crypto.createHash('sha256').update(fs.readFileSync(path.join(output,record.file))).digest('hex'))
      .toBe(record.sha256);
  }
  await info.attach('montage', { path: path.join(output, meta.montage_file), contentType: 'image/png' });
});
