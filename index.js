(async () => {
  const grid = document.getElementById('project-grid');
  if (!grid) return;

  try {
    const res = await fetch('./projects.json', { cache: 'no-store' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const items = await res.json();

    const frag = document.createDocumentFragment();

    items.forEach(({ name, desc, url, topics = [] }) => {
      const card = document.createElement('article');
      card.className = 'card';

      const title = document.createElement('h3');
      const link = document.createElement('a');
      link.href = url;
      link.textContent = name;
      link.rel = 'noopener noreferrer';
      link.target = '_blank';
      title.appendChild(link);

      const p = document.createElement('p');
      p.textContent = desc || '';

      const badges = document.createElement('div');
      badges.className = 'badges';
      topics.slice(0, 6).forEach(t => {
        const span = document.createElement('span');
        span.className = 'tag';
        span.textContent = t;
        badges.appendChild(span);
      });

      const shields = document.createElement('img');
      shields.loading = 'lazy';
      shields.alt = 'GitHub stars';
      shields.src = `https://img.shields.io/github/stars/myon-bioinformatics/${encodeURIComponent(name)}?style=social`;
      shields.style.marginTop = '6px';

      card.appendChild(title);
      card.appendChild(p);
      card.appendChild(badges);
      card.appendChild(shields);
      frag.appendChild(card);
    });

    grid.innerHTML = '';
    grid.appendChild(frag);
  } catch (e) {
    grid.innerHTML = `<p>Failed to load projects. Please refresh.</p>`;
    console.error(e);
  }
})();