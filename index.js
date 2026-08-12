// ── Profile (About / Skills / Career) ──────────────────────────────────────
(async () => {
  const panels = {
    about:  document.getElementById('panel-about'),
    skills: document.getElementById('panel-skills'),
    career: document.getElementById('panel-career'),
  };
  const buttons = document.querySelectorAll('#profile .tab-btn');
  if (!panels.about) return;

  let skillsAnimated = false;

  function activateTab(key) {
    buttons.forEach(b => {
      const active = b.id === `tab-${key}`;
      b.classList.toggle('active', active);
      b.setAttribute('aria-selected', active);
    });
    Object.entries(panels).forEach(([k, el]) => {
      const show = k === key;
      el.classList.toggle('active', show);
      el.hidden = !show;
    });

    if (key === 'skills' && !skillsAnimated) {
      skillsAnimated = true;
      // trigger CSS animation by setting actual width after a tick
      requestAnimationFrame(() => {
        panels.skills.querySelectorAll('.skill-bar-fill').forEach(bar => {
          bar.style.width = bar.dataset.level + '%';
        });
      });
    }
  }

  buttons.forEach(btn => {
    btn.addEventListener('click', () => {
      const key = btn.id.replace('tab-', '');
      activateTab(key);
    });
  });

  try {
    const res = await fetch('./profile.json', { cache: 'no-store' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const { about, skills, career } = await res.json();

    // About
    const aboutEl = document.createElement('p');
    aboutEl.className = 'about-text';
    aboutEl.textContent = about;
    panels.about.appendChild(aboutEl);

    // Skills
    skills.forEach(({ category, items }) => {
      const group = document.createElement('div');
      group.className = 'skill-group';

      const cat = document.createElement('h4');
      cat.className = 'skill-category';
      cat.textContent = category;
      group.appendChild(cat);

      items.forEach(({ name, level }) => {
        const row = document.createElement('div');
        row.className = 'skill-row';

        const label = document.createElement('span');
        label.className = 'skill-label';
        label.textContent = name;

        const track = document.createElement('div');
        track.className = 'skill-bar-track';

        const fill = document.createElement('div');
        fill.className = 'skill-bar-fill';
        fill.dataset.level = level;
        fill.style.width = '0%'; // start collapsed; animates when tab opens

        track.appendChild(fill);
        row.appendChild(label);
        row.appendChild(track);
        group.appendChild(row);
      });

      panels.skills.appendChild(group);
    });

    // Career
    const timeline = document.createElement('ol');
    timeline.className = 'timeline';
    career.forEach(({ year, title, desc }) => {
      const item = document.createElement('li');
      item.className = 'timeline-item';
      item.innerHTML = `<span class="tl-year">${year}</span>
        <div class="tl-body">
          <strong>${title}</strong>
          <p>${desc}</p>
        </div>`;
      timeline.appendChild(item);
    });
    panels.career.appendChild(timeline);

  } catch (e) {
    panels.about.innerHTML = '<p>Failed to load profile.</p>';
    console.error(e);
  }
})();

// ── Projects ────────────────────────────────────────────────────────────────

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