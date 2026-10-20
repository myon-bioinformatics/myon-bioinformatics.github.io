// Browser screenshots exercise the production stdlib encoder, not a duplicate implementation.
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
function createApng(pngBuffers, outputPath, delayMs = 500, loops = 0) {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'portfolio-apng-'));
  try {
    const frames = pngBuffers.map((buffer, i) => {
      const file = path.join(temp, `${i}.png`);
      fs.writeFileSync(file, buffer);
      return file;
    });
    const output = outputPath || path.join(temp, 'animation.png');
    fs.mkdirSync(path.dirname(output), { recursive: true });
    execFileSync(process.env.PYTHON || 'python3', ['-S', path.resolve(__dirname, '../scripts/generate_apng.py'),
      ...frames, '-o', output, '-d', String(delayMs), '-l', String(loops)], { timeout: 30000 });
    return fs.readFileSync(output);
  } finally {
    fs.rmSync(temp, { recursive: true, force: true });
  }
}
module.exports = { createApng };
