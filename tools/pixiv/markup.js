/* Pixiv-only adapter; mirror scripts/pixiv_markup.py using shared fixtures. */
(function(root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.portfolioPixivMarkup = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function() {
  'use strict';
  const MAX_SOURCE_LENGTH = 200000;
  function lines(text) { return text.replace(/\r\n|\r|\u2028|\u2029/g, '\n'); }
  function inline(text) {
    function prose(part) {
      return part.replace(/NEXT▶︎(?=\[\[)/g, 'NEXT ▶︎ ').replace(/\[\[([^\[\]>]+)(?:>([^\[\]]+))?\]\]/g, (_, label, target) => {
        label = label.trim();
        target = (target || label).trim().replace(/\(/g, '%28').replace(/\)/g, '%29').replace(/ /g, '%20');
        return '[' + label + '](' + target + ')';
      }).replace(/!\[pixiv image (\d+)\]\(pixivimage:\1(?: "[A-Za-z0-9]+")?\)/g, '[pixiv image $1](https://www.pixiv.net/artworks/$1)')
        .replace(/\[pixivimage:(\d+)(?::[A-Za-z0-9]+)?\]/g, '[pixiv image $1](https://www.pixiv.net/artworks/$1)')
        .replace(/\[youtube:([A-Za-z0-9_-]{11})\]/g, '[YouTube](https://www.youtube.com/watch?v=$1)');
    }
    const parts = text.split(/(`+)(.*?)\1/g);
    let out = prose(parts[0]);
    for (let i = 1; i < parts.length; i += 3) out += parts[i] + parts[i + 1] + parts[i] + prose(parts[i + 2]);
    return out;
  }
  function pixivToMarkdown(source) {
    if (source.length > MAX_SOURCE_LENGTH) throw new Error('Pixiv source exceeds 200000 characters');
    const input = lines(source).replace(/\0/g, '\ufffd').split('\n'), out = [];
    let fence = null;
    for (let i = 0; i < input.length;) {
      let line = input[i];
      const marker = /^ {0,3}(`{3,}|~{3,})(.*)$/.exec(line);
      if (fence) {
        out.push(line);
        if (marker && marker[1][0] === fence[0] && marker[1].length >= fence.length && !marker[2].trim()) fence = null;
        i++; continue;
      }
      if (marker && !(marker[1][0] === '`' && marker[2].includes('`'))) {
        fence = marker[1]; out.push(line); i++; continue;
      }
      if (line.startsWith('|') && line.endsWith('|')) {
        let j = i;
        const rows = [];
        while (j < input.length && input[j].startsWith('|') && input[j].endsWith('|')) rows.push(input[j++].slice(1, -1).split(/(?<!\\)\|/));
        if (rows.some(row => row.some(cell => cell.trimStart().startsWith('^')))) {
          const width = rows.reduce((width, row) => Math.max(width, row.length), 0);
          if (out.length && out[out.length - 1].trim()) out.push('');
          out.push('|' + Array(width).fill(' ').join('|') + '|', '|' + Array(width).fill(' --- ').join('|') + '|');
          for (const row of rows) {
            const cells = row.map(cell => { cell = cell.trim(); return cell.startsWith('^') ? '**' + inline(cell.slice(1)) + '**' : inline(cell); });
            out.push('| ' + cells.concat(Array(width - cells.length).fill('')).join(' | ') + ' |');
          }
          out.push(''); i = j; continue;
        }
      }
      const heading = /^(\*{1,6})([^*\s].*?)\s*$/.exec(line);
      if (heading && !heading[2].includes(heading[1])) {
        if (out.length && out[out.length - 1].trim()) out.push('');
        out.push('#'.repeat(heading[1].length) + ' ' + inline(heading[2]), '');
      } else {
        line = line.replace(/^(-{1,6})(?=[^\s-])/, (_, prefix) => '  '.repeat(prefix.length - 1) + '- ');
        out.push(inline(line));
      }
      i++;
    }
    return out.join('\n');
  }
  function extractSource(source, title = '') {
    if (source.length > MAX_SOURCE_LENGTH) throw new Error('Pixiv source exceeds 200000 characters');
    source = lines(source);
    const envelope = /^Title: ([^\n]+)\n[\s\S]*?\nBody:\n/.exec(source);
    if (envelope) { title = title.trim() || envelope[1].trim(); source = source.slice(envelope[0].length); }
    const body = pixivToMarkdown(source), input = body.split('\n'), found = [];
    let fence = null;
    input.forEach((line, index) => {
      const marker = /^ {0,3}(`{3,}|~{3,})(.*)$/.exec(line);
      if (fence) {
        if (marker && marker[1][0] === fence[0] && marker[1].length >= fence.length && !marker[2].trim()) fence = null;
        return;
      }
      if (marker && !(marker[1][0] === '`' && marker[2].includes('`'))) { fence = marker[1]; return; }
      const heading = /^(#{1,6})[ \t]+(.+?)(?:[ \t]+#+)?[ \t]*$/.exec(line);
      if (heading) found.push({line: index, level: heading[1].length, heading: heading[2]});
    });
    const ends = found.map(() => input.length), stack = [];
    found.forEach((item, index) => {
      while (stack.length && found[stack[stack.length - 1]].level >= item.level) ends[stack.pop()] = item.line;
      stack.push(index);
    });
    const fallback = found.length ? found[0].heading : (input.find(line => line.trim()) || '').trim();
    return {title: title.trim() || fallback, body, headings: found.map(({level, heading}) => ({level, heading})),
      sections: found.map((item, index) => {
        return {value: String(index), label: '#'.repeat(item.level) + ' ' + item.heading,
          body: input.slice(item.line + 1, ends[index]).join('\n').trim()};
      })};
  }
  return {pixivToMarkdown, extractSource, MAX_SOURCE_LENGTH};
});
