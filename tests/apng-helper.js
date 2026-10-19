// @ts-check
const fs = require('fs');
const path = require('path');
const zlib = require('zlib');

function crc32(buf) {
  return zlib.crc32(buf);
}

function makeChunk(type, data) {
  const lenBuf = Buffer.alloc(4);
  lenBuf.writeUInt32BE(data.length, 0);

  const typeBuf = Buffer.from(type, 'ascii');
  const crcBuf = Buffer.alloc(4);

  const typeAndData = Buffer.concat([typeBuf, data]);
  crcBuf.writeUInt32BE(crc32(typeAndData) >>> 0, 0);

  return Buffer.concat([lenBuf, typeAndData, crcBuf]);
}

function parsePngChunks(buffer) {
  let offset = 8;
  const chunks = [];
  while (offset < buffer.length) {
    const len = buffer.readUInt32BE(offset);
    const type = buffer.toString('ascii', offset + 4, offset + 8);
    const data = buffer.subarray(offset + 8, offset + 8 + len);
    chunks.push({ type, data });
    offset += 12 + len;
  }
  return chunks;
}

function createApng(pngBuffers, outputPath, delayMs = 500, loops = 0) {
  if (!pngBuffers || pngBuffers.length === 0) return null;

  const parsedFrames = pngBuffers.map((buf) => parsePngChunks(buf));
  const firstIhdr = parsedFrames[0].find((c) => c.type === 'IHDR').data;
  const width = firstIhdr.readUInt32BE(0);
  const height = firstIhdr.readUInt32BE(4);

  const pngHeader = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
  const chunks = [pngHeader, makeChunk('IHDR', firstIhdr)];

  const actlData = Buffer.alloc(8);
  actlData.writeUInt32BE(parsedFrames.length, 0);
  actlData.writeUInt32BE(loops, 4);
  chunks.push(makeChunk('acTL', actlData));

  let seq = 0;
  parsedFrames.forEach((frame, frameIdx) => {
    const fctlData = Buffer.alloc(26);
    fctlData.writeUInt32BE(seq++, 0);
    fctlData.writeUInt32BE(width, 4);
    fctlData.writeUInt32BE(height, 8);
    fctlData.writeUInt32BE(0, 12);
    fctlData.writeUInt32BE(0, 16);
    fctlData.writeUInt16BE(delayMs, 20);
    fctlData.writeUInt16BE(1000, 22);
    fctlData.writeUInt8(0, 24);
    fctlData.writeUInt8(0, 25);
    chunks.push(makeChunk('fcTL', fctlData));

    const idatChunks = frame.filter((c) => c.type === 'IDAT');
    idatChunks.forEach((idat) => {
      if (frameIdx === 0) {
        chunks.push(makeChunk('IDAT', idat.data));
      } else {
        const seqBuf = Buffer.alloc(4);
        seqBuf.writeUInt32BE(seq++, 0);
        const fdatData = Buffer.concat([seqBuf, idat.data]);
        chunks.push(makeChunk('fdAT', fdatData));
      }
    });
  });

  chunks.push(makeChunk('IEND', Buffer.alloc(0)));
  const result = Buffer.concat(chunks);
  if (outputPath) {
    fs.mkdirSync(path.dirname(outputPath), { recursive: true });
    fs.writeFileSync(outputPath, result);
  }
  return result;
}

module.exports = { createApng };
