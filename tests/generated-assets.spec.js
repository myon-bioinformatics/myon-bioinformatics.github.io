const { test, expect } = require('@playwright/test');
const crypto = require('node:crypto');
const lock = require('../web-ui-assets.lock.json');

test('generated build preserves public URLs and serves locked bytes', async ({ request }) => {
  // This contract is specifically for the generated-site CI configuration.
  test.skip(!process.env.GENERATED_ASSETS_TEST, 'run with playwright/generated.config.js');
  for (const [url, digest] of Object.entries(lock.outputs)) {
    const response = await request.get('/' + url);
    expect(response.status(), url).toBe(200);
    expect(crypto.createHash('sha256').update(await response.body()).digest('hex'), url).toBe(digest);
  }
  const response = await request.get('/tools/vendor/web-ui/generated.lock.json');
  expect(await response.json()).toEqual(lock);
});
