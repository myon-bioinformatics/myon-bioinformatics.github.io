(function () {
  'use strict';

  const API_ENDPOINT = 'https://snapshot.search.nicovideo.jp/api/v2/snapshot/video/contents/search';

  function formatNumber(num) {
    if (num == null) return '0';
    return Number(num).toLocaleString();
  }

  function formatDuration(sec) {
    if (sec == null) return '0:00';
    const m = Math.floor(sec / 60);
    const s = Math.floor(sec % 60);
    return `${m}:${s < 10 ? '0' : ''}${s}`;
  }

  async function searchNiconico(query, sort = '-viewCounter', signal) {
    const params = new URLSearchParams({
      q: query,
      targets: 'title,description',
      fields: 'contentId,title,description,viewCounter,likeCounter,lengthSeconds,thumbnailUrl,startTime',
      _sort: sort,
      _limit: '10',
      _context: 'myon-portfolio-lab',
    });

    const url = `${API_ENDPOINT}?${params.toString()}`;
    const res = await fetch(url, { signal });
    if (!res.ok) {
      throw new Error(`Niconico API error: ${res.status}`);
    }
    let data;
    try {
      data = await res.json();
    } catch (error) {
      if (signal?.aborted) throw error;
      throw new Error('Invalid Niconico API response: expected JSON.');
    }
    signal?.throwIfAborted();
    if (data?.meta?.status !== 200 || !Array.isArray(data.data)
        || !Number.isSafeInteger(data.meta.totalCount) || data.meta.totalCount < 0
        || !data.data.every(video => video && typeof video.contentId === 'string'
          && /^(?:[a-z]{2})?\d+$/.test(video.contentId)
          && (video.title == null || typeof video.title === 'string')
          && (video.description == null || typeof video.description === 'string'))) {
      throw new Error('Invalid Niconico API response');
    }
    data.data = data.data.slice(0, 10);
    return data;
  }

  function renderResults(container, data) {
    container.replaceChildren();

    if (!data || !data.data || data.data.length === 0) {
      const msg = document.createElement('p');
      msg.className = 'ui-muted';
      msg.textContent = 'No videos found matching your query.';
      container.appendChild(msg);
      return;
    }

    const grid = document.createElement('div');
    grid.className = 'niconico-grid';
    grid.style.display = 'grid';
    grid.style.gridTemplateColumns = 'repeat(auto-fill, minmax(280px, 1fr))';
    grid.style.gap = '12px';
    grid.style.marginTop = '1rem';

    data.data.forEach((video) => {
      const card = document.createElement('div');
      card.className = 'ui-card niconico-card';

      const link = document.createElement('a');
      link.href = `https://www.nicovideo.jp/watch/${encodeURIComponent(video.contentId)}`;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      link.style.fontWeight = 'bold';
      link.textContent = video.title || video.contentId;

      const meta = document.createElement('p');
      meta.className = 'ui-muted';
      meta.style.fontSize = '0.85rem';
      meta.style.margin = '4px 0';
      meta.textContent = `👁 ${formatNumber(video.viewCounter)} views · ❤️ ${formatNumber(video.likeCounter)} · ⏱ ${formatDuration(video.lengthSeconds)}`;

      const desc = document.createElement('p');
      desc.style.fontSize = '0.85rem';
      desc.style.lineHeight = '1.4';
      desc.style.margin = '6px 0 0 0';
      const cleanDesc = (video.description || '').replace(/<[^>]*>/g, '');
      desc.textContent = cleanDesc.length > 100 ? cleanDesc.slice(0, 100) + '…' : cleanDesc;

      card.appendChild(link);
      card.appendChild(meta);
      card.appendChild(desc);
      grid.appendChild(card);
    });

    container.appendChild(grid);
  }

  function initNiconicoApp() {
    const form = document.getElementById('pages-niconico-form');
    const queryInput = document.getElementById('pages-niconico-query');
    const sortSelect = document.getElementById('pages-niconico-sort');
    const statusEl = document.getElementById('pages-niconico-status');
    const errorEl = document.getElementById('pages-niconico-error');
    const resultsEl = document.getElementById('pages-niconico-results');
    const officialLink = document.getElementById('pages-niconico-official');

    if (!form || !queryInput) return;

    function updateOfficialLink() {
      if (!officialLink) return;
      const sort = { '-viewCounter': 'v', '-startTime': 'f', '-likeCounter': 'likeCount', '-mylistCounter': 'm' };
      const params = new URLSearchParams({ sort: sort[sortSelect?.value] || 'v', order: 'd' });
      officialLink.href = `https://www.nicovideo.jp/search/${encodeURIComponent(queryInput.value.trim())}?${params}`;
    }
    queryInput.addEventListener('input', updateOfficialLink);
    sortSelect?.addEventListener('change', updateOfficialLink);
    updateOfficialLink();

    let currentRequest = null;
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const q = queryInput.value.trim();
      if (!q) return;
      updateOfficialLink();
      if (currentRequest) currentRequest.abort();
      const request = new AbortController();
      currentRequest = request;
      let timedOut = false;
      const timeout = setTimeout(() => { timedOut = true; request.abort(); }, 10000);

      if (statusEl) statusEl.textContent = 'Searching Niconico...';
      if (errorEl) {
        errorEl.hidden = true;
        errorEl.textContent = '';
      }
      if (resultsEl) resultsEl.replaceChildren();

      try {
        const sort = sortSelect ? sortSelect.value : '-viewCounter';
        const data = await searchNiconico(q, sort, request.signal);
        if (currentRequest !== request) return;
        const total = data?.meta?.totalCount ?? 0;
        if (statusEl) statusEl.textContent = `Found ${total.toLocaleString()} total results (showing top ${data?.data?.length || 0}).`;
        if (resultsEl) renderResults(resultsEl, data);
      } catch (err) {
        if (currentRequest !== request) return;
        if (statusEl) statusEl.textContent = '';
        if (errorEl) {
          errorEl.hidden = false;
          errorEl.textContent = timedOut ? 'Search timed out after 10 seconds. Try again later or open Search on Niconico.'
            : err instanceof TypeError ? 'Cannot read the Niconico API response. The browser may block it because of CORS, or the network may be unavailable. Open Search on Niconico instead.'
            : err.message === 'Niconico API error: 503' ? 'Niconico API error: 503. The service is busy; wait at least 5 minutes before retrying.'
            : (err.message || 'Failed to fetch Niconico search results.');
        }
      } finally {
        clearTimeout(timeout);
        if (currentRequest === request) currentRequest = null;
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initNiconicoApp);
  } else {
    initNiconicoApp();
  }
})();
