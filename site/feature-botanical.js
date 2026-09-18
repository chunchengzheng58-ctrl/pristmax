// Pine botanical animation for feature card expansions.
// Grows a stylized pine tree on each feature card expansion.

(function () {
  var REDUCED = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function init() {
    document.querySelectorAll('.feature-card').forEach(function (card) {
      card.addEventListener('toggle', function () {
        if (card.open && !REDUCED) {
          growPine(card);
        }
      });
    });
  }

  function growPine(card) {
    var expansion = card.querySelector('.feature-expansion');
    if (!expansion) return;

    // Remove existing pine
    var existing = expansion.querySelector('.pine-svg');
    if (existing) existing.remove();

    var idx = [].slice.call(document.querySelectorAll('.feature-card')).indexOf(card);
    var seed = (idx + 1) * 7919;

    var svg = createPineSVG(seed, idx);
    // Insert as first child so it's behind text content
    expansion.insertAdjacentHTML('afterbegin', svg);

    // Small delay to ensure SVG is in DOM
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        expansion.classList.add('pine-growing');
      });
    });

    // Allow replay by removing class after animation
    expansion.addEventListener('animationend', function () {
      expansion.classList.remove('pine-growing');
    }, { once: true });
  }

  // Seeded pseudo-random (LCG)
  function makeRand(seed) {
    var s = seed;
    return function () {
      s = (s * 1664525 + 1013904223) >>> 0;
      return s / 0xffffffff;
    };
  }

  function createPineSVG(seed, idx) {
    var rand = makeRand(seed);
    var r = function () { return rand(); };

    var W = 360, H = 280;

    // Trunk
    var trunkX = W * 0.5;
    var trunkBaseY = H;
    var trunkH = 110 + r() * 30;
    var trunkTopX = trunkX + (r() - 0.5) * 8;
    var trunkTopY = trunkBaseY - trunkH;
    var trunkLen = Math.sqrt(Math.pow(trunkTopX - trunkX, 2) + Math.pow(trunkTopY - trunkBaseY, 2));

    // 4 branch levels
    var levels = [];
    for (var i = 0; i < 4; i++) {
      var t = (i + 1) / 5;
      var ly = trunkBaseY - trunkH * t;
      var lx = trunkX + (trunkTopX - trunkX) * t;
      var llen = (35 + r() * 20) * (1 - t * 0.25);
      var dir = (i % 2 === 0) ? 1 : -1;
      levels.push({ x: lx, y: ly, len: llen, dir: dir });
    }

    var parts = [];

    // Trunk path
    parts.push('<path class="pine-trunk" d="M' + trunkX + ',' + trunkBaseY + ' L' + trunkTopX + ',' + trunkTopY + '"/>');

    // Branches (one side then mirror)
    levels.forEach(function (lv, i) {
      var delay = (0.25 + i * 0.12).toFixed(2);
      // right branch
      var rEx = lv.x + lv.dir * lv.len;
      var rEy = lv.y - lv.len * 0.25;
      parts.push('<path class="pine-branch" d="M' + lv.x + ',' + lv.y + ' Q' + (lv.x + lv.dir * lv.len * 0.5) + ',' + (lv.y - 8) + ' ' + rEx + ',' + rEy + '" style="animation-delay:' + delay + 's"/>');
      // left branch (mirror)
      var mlen = lv.len * (0.75 + r() * 0.2);
      var mEx = lv.x - lv.dir * mlen;
      var mEy = lv.y - mlen * 0.25;
      parts.push('<path class="pine-branch" d="M' + lv.x + ',' + lv.y + ' Q' + (lv.x - lv.dir * mlen * 0.5) + ',' + (lv.y - 7) + ' ' + mEx + ',' + mEy + '" style="animation-delay:' + (parseFloat(delay) + 0.05).toFixed(2) + 's"/>');

      // needles cluster at branch tip
      var needleCount = 5 + Math.floor(r() * 4);
      for (var n = 0; n < needleCount; n++) {
        var nt = n / needleCount;
        var nx = lv.x + lv.dir * lv.len * nt * 0.9;
        var ny = lv.y - 4 + r() * 8;
        var nlen = 12 + r() * 18;
        var nAngle = lv.dir * (60 + r() * 40) * (n % 2 === 0 ? 1 : -1);
        var rad = (nAngle - 90) * Math.PI / 180;
        var nx2 = nx + Math.cos(rad) * nlen;
        var ny2 = ny + Math.sin(rad) * nlen;
        var nd = (0.55 + i * 0.1 + n * 0.01).toFixed(2);
        parts.push('<line class="pine-needle" x1="' + nx.toFixed(1) + '" y1="' + ny.toFixed(1) + '" x2="' + nx2.toFixed(1) + '" y2="' + ny2.toFixed(1) + '" style="animation-delay:' + nd + 's"/>');
      }
    });

    return '<svg class="pine-svg" viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="xMaxYMax meet" aria-hidden="true" focusable="false">' +
      '<defs><linearGradient id="pg' + idx + '" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="white" stop-opacity="0"/><stop offset="50%" stop-color="white" stop-opacity="0.5"/><stop offset="100%" stop-color="white" stop-opacity="0.85"/></linearGradient></defs>' +
      '<g>' + parts.join('') + '</g>' +
      '<rect width="' + W + '" height="' + H + '" fill="url(#pg' + idx + ')"/>' +
      '</svg>';
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
