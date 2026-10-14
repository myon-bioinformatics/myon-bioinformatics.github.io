/* Consumer wrapper: the imported URL/HTML helpers retain their source identity. */
(function(win) {
  'use strict';
  function mount() {
    const root = win.document.querySelector('[data-testid="pages-pixiv-app"]');
    if (!root || root.dataset.portfolioPixivMounted) return;
    root.dataset.portfolioPixivMounted = 'true';
    const upstream = win.mcpToolcallLabPagesPixiv, markup = win.portfolioPixivMarkup;
    const get = name => root.querySelector('[data-testid="pages-pixiv-' + name + '"]');
    const output = get('extract'), error = get('error'), status = get('status');
    const control = win.webUiControls.bindSelect(root.querySelector('#pages-pixiv-heading'), output);
    function fail(message) {
      control.clear(); output.hidden = true; status.textContent = '';
      error.textContent = message; error.hidden = false;
    }
    for (const [name, build] of [['open-article', upstream.buildArticleUrl], ['open-history', upstream.buildHistoryUrl]]) {
      get(name).addEventListener('click', () => {
        const url = build(get('title').value);
        if (!url) { fail(upstream.MISSING_TITLE); return; }
        win.webUiNavigation.openExternalURL(url, win);
      });
    }
    get('source-form').addEventListener('submit', event => {
      event.preventDefault();
      const source = get('source-text').value;
      if (source.length > markup.MAX_SOURCE_LENGTH) { fail(upstream.SOURCE_TOO_LARGE); return; }
      if (!source.trim()) { fail(upstream.MISSING_SOURCE); return; }
      let title = get('title').value.trim(), revision = '';
      const url = get('source-url').value.trim();
      if (url) {
        const parsed = upstream.parseSourceUrl(url);
        if (!parsed.ok) { fail(parsed.error); return; }
        title = parsed.title; revision = parsed.revisionId;
      }
      // A leading document/block tag takes the existing saved-HTML path. Inline
      // HTML-looking prose in a source article must not discard its headings.
      let result;
      if (/^\s*<(?:!doctype\b|html\b|body\b|h[1-6]\b|div\b|p\b|section\b)/i.test(source)) {
        const html = upstream.extractSource({title, sourceText: source});
        if (!html.ok) { fail(html.error); return; }
        result = {...html, sections: []};
      } else result = markup.extractSource(source, title);
      const parts = ['Title: ' + result.title];
      if (result.reading) parts.push('Reading: ' + result.reading);
      if (revision) parts.push('Revision: ' + revision);
      if (result.overview) parts.push('', 'Overview:', result.overview);
      if (result.headings && result.headings.length) {
        parts.push('', 'Headings:');
        result.headings.forEach(item => parts.push('  '.repeat(item.level - 1) + '- ' + item.heading));
      }
      parts.push('', 'Body:', result.body);
      const full = parts.join('\n');
      control.update(result.sections, full, '(全文)');
      error.textContent = ''; error.hidden = true; output.hidden = false;
      status.textContent = '抽出しました。見出しを選ぶと本文を切り替えます。';
    });
  }
  if (win.document.readyState === 'loading') win.document.addEventListener('DOMContentLoaded', mount);
  else mount();
})(globalThis);
