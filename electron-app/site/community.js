/** Pristmax - All Rights Reserved. Copyright © 2024-2026 */
// GitHub stats fetcher for community section
// Falls back gracefully when GitHub API is unreachable or rate-limited.

const REPO = 'chunchengzheng58-ctrl/pristmax';

async function fetchGitHubStats() {
  const endpoints = [
    ['/repos/' + REPO, ['stargazers_count', 'forks_count', 'open_issues_count']],
    ['/repos/' + REPO + '/contributors?per_page=10', null]
  ];

  for (const [endpoint, fields] of endpoints) {
    try {
      const res = await fetch('https://api.github.com' + endpoint, {
        headers: { 'Accept': 'application/vnd.github.v3+json' }
      });
      if (!res.ok) throw new Error('API ' + res.status);

      const data = await res.json();

      if (endpoint.includes('/contributors')) {
        const count = Array.isArray(data) ? data.length : 0;
        const el = document.getElementById('gh-contributors');
        if (el) el.textContent = count > 0 ? count : '1';
      } else if (fields) {
        fields.forEach(field => {
          if (field === 'stargazers_count') {
            const el = document.getElementById('gh-stars');
            if (el) el.textContent = data[field] || '0';
          } else if (field === 'forks_count') {
            const el = document.getElementById('gh-forks');
            if (el) el.textContent = data[field] || '0';
          } else if (field === 'open_issues_count') {
            const el = document.getElementById('gh-issues');
            if (el) el.textContent = data[field] || '0';
          }
        });
      }
    } catch (e) {
      // Keep fallback dashes on failure
      console.debug('GitHub stats unavailable:', e.message);
    }
  }
}

document.addEventListener('DOMContentLoaded', () => {
  fetchGitHubStats();
  initFAQ();
  initCountUp();
});

// FAQ search + category filter
function initFAQ() {
  const search = document.getElementById('faq-search');
  const cats = document.querySelectorAll('.faq-cat');
  const details = document.querySelectorAll('.faq-list details');
  const empty = document.getElementById('faq-empty');
  if (!search || !details.length) return;

  function filter() {
    const q = search.value.trim().toLowerCase();
    const activeCat = document.querySelector('.faq-cat.active')?.dataset.category || 'all';
    let visible = 0;

    details.forEach(d => {
      const cat = d.dataset.category || 'all';
      const text = (d.querySelector('summary')?.textContent + d.querySelector('p')?.textContent || '').toLowerCase();
      const matchesCat = activeCat === 'all' || cat === activeCat;
      const matchesQ = !q || text.includes(q);
      const show = matchesCat && matchesQ;
      d.hidden = !show;
      if (show) visible++;
    });

    if (empty) empty.hidden = visible > 0;
  }

  search.addEventListener('input', filter);
  cats.forEach(btn => {
    btn.addEventListener('click', () => {
      cats.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      filter();
    });
  });

  // Maintain aria-expanded on FAQ details
  details.forEach(d => {
    const summary = d.querySelector('summary');
    if (!summary) return;
    summary.setAttribute('aria-expanded', d.open);
    d.addEventListener('toggle', () => {
      summary.setAttribute('aria-expanded', d.open);
    });
  });
}

// Count-up animation for stat values
function initCountUp() {
  const statEls = document.querySelectorAll('.stat-value');
  if (!statEls.length) return;

  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (!entry.isIntersecting) return;
      const el = entry.target;
      const final = parseInt(el.textContent, 10);
      if (isNaN(final) || final <= 0) return;

      let start = 0;
      const duration = 1200;
      const step = 16;
      const increment = Math.max(1, Math.ceil(final / (duration / step)));

      const timer = setInterval(() => {
        start += increment;
        if (start >= final) {
          el.textContent = final;
          clearInterval(timer);
        } else {
          el.textContent = start;
        }
      }, step);

      el.classList.add('counting');
      observer.unobserve(el);
    });
  }, { threshold: 0.5 });

  statEls.forEach(el => observer.observe(el));
}
