// Pine botanical animation for feature card expansions.
// Each feature gets a unique pine tree (seeded variation) that grows on open.

(function () {
  const REDUCED = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  let initialized = false;

  function init() {
    if (initialized) return;
    initialized = true;

    document.querySelectorAll('.feature-card').forEach((card) => {
      card.addEventListener('toggle', () => {
        if (card.open && !REDUCED) {
          growPine(card);
        }
      });
    });
  }

  function growPine(card) {
    const expansion = card.querySelector('.feature-expansion');
    if (!expansion) return;

    // Remove existing pine if any
    const existing = expansion.querySelector('.pine-svg');
    if (existing) existing.remove();

    // Unique seed from card index for variation
    const idx = [...document.querySelectorAll('.feature-card')].indexOf(card);
    const seed = (idx + 1) * 7919; // prime multiplier for variation

    const svg = createPineSVG(seed, idx);
    expansion.insertAdjacentHTML('afterbegin', svg);

    // Trigger animation on next frame
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        expansion.classList.add('pine-growing');
      });
    });

    // Remove animation class after it completes so replay works
    expansion.addEventListener('animationend', () => {
      expansion.classList.remove('pine-growing');
    }, { once: true });
  }

  function seededRand(seed) {
    // LCG pseudo-random
    let s = seed;
    return function () {
      s = (s * 1664525 + 1013904223) & 0xffffffff;
      return ((s >>> 0) / 0xffffffff);
    };
  }

  function createPineSVG(seed, index) {
    const rand = seededRand(seed);
    const r = () => rand();

    // Dimensions
    const W = 400, H = 320;
    // Trunk base
    const trunkBaseX = W * 0.5;
    const trunkBaseY = H;
    const trunkHeight = 120 + r() * 40; // 120-160px variation
    const trunkTopX = trunkBaseX + (r() - 0.5) * 10;
    const trunkTopY = trunkBaseY - trunkHeight;

    // 4 layers of branches
    const layers = [];
    for (let i = 0; i < 4; i++) {
      const t = (i + 1) / 5; // 0.2, 0.4, 0.6, 0.8 of trunk height
      const y = trunkBaseY - trunkHeight * t;
      const x = trunkBaseX + (trunkTopX - trunkBaseX) * t;
      const len = (40 + r() * 25) * (1 - t * 0.3); // shorter toward top
      const side = i % 2 === 0 ? 1 : -1; // alternate sides
      layers.push({ x, y, len, side, angle: (15 + r() * 20) * (i % 2 === 0 ? 1 : -1) });
    }

    // Needle clusters
    const needles = [];
    layers.forEach((layer, li) => {
      const needleCount = 6 + Math.floor(r() * 5);
      for (let n = 0; n < needleCount; n++) {
        const t = n / needleCount;
        const nx = layer.x + layer.side * layer.len * t;
        const ny = layer.y - 5 + r() * 10;
        const nlen = 15 + r() * 20;
        const angle = layer.angle + (r() - 0.5) * 30;
        needles.push({ nx, ny, nlen, angle, delay: li * 0.1 + n * 0.02 });
      }
    });

    // Build SVG
    let paths = '';

    // Trunk
    const trunkLen = Math.hypot(trunkTopX - trunkBaseX, trunkTopY - trunkBaseY);
    paths += `<path class="pine-trunk" d="M${trunkBaseX},${trunkBaseY} L${trunkTopX},${trunkTopY}"
      stroke-dasharray="${trunkLen}" stroke-dashoffset="${trunkLen}"/>`;

    // Branches
    layers.forEach((layer, i) => {
      const endX = layer.x + layer.side * layer.len;
      const endY = layer.y - layer.len * 0.3;
      // Left branch
      paths += `<path class="pine-branch" d="M${layer.x},${layer.y} Q${layer.x + layer.side * layer.len * 0.5},${layer.y - 10} ${endX},${endY}"
        stroke-dasharray="${layer.len * 1.2}" stroke-dashoffset="${layer.len * 1.2}"
        style="animation-delay:${0.3 + i * 0.1}s"/>`;
      // Mirror branch on other side
      const mirrorLen = layer.len * (0.8 + r() * 0.2);
      const mirrorEndX = layer.x - layer.side * mirrorLen;
      const mirrorEndY = layer.y - mirrorLen * 0.3;
      paths += `<path class="pine-branch" d="M${layer.x},${layer.y} Q${layer.x - layer.side * mirrorLen * 0.5},${layer.y - 8} ${mirrorEndX},${mirrorEndY}"
        stroke-dasharray="${mirrorLen * 1.2}" stroke-dashoffset="${mirrorLen * 1.2}"
        style="animation-delay:${0.35 + i * 0.1}s"/>`;
    });

    // Needles
    needles.forEach((n) => {
      const rad = (n.angle - 90) * Math.PI / 180;
      const nx2 = n.nx + Math.cos(rad) * n.nlen;
      const ny2 = n.ny + Math.sin(rad) * n.nlen;
      paths += `<line class="pine-needle" x1="${n.nx}" y1="${n.ny}" x2="${nx2}" y2="${ny2}"
        stroke-dasharray="${n.nlen}" stroke-dashoffset="${n.nlen}"
        style="animation-delay:${0.6 + n.delay}s"/>`;
    });

    return `<svg class="pine-svg" viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMax meet"
      aria-hidden="true" focusable="false">
      <defs>
        <linearGradient id="pine-fade-${index}" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="white" stop-opacity="0"/>
          <stop offset="60%" stop-color="white" stop-opacity="0.6"/>
          <stop offset="100%" stop-color="white" stop-opacity="0.9"/>
        </linearGradient>
      </defs>
      <g opacity="0.9">${paths}</g>
      <rect width="${W}" height="${H}" fill="url(#pine-fade-${index})"/>
    </svg>`;
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
