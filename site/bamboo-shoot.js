/** Pristmax - All Rights Reserved. Copyright © 2024-2026 */
// Bamboo shoot growth animation for feature card expansions.

(function () {
  var REDUCED = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function init() {
    var cards = document.querySelectorAll('.feature-card');
    cards.forEach(function (card) {
      card.addEventListener('toggle', function () {
        if (card.open && !REDUCED) {
          growBamboo(card);
        }
      });
    });
  }

  function growBamboo(card) {
    var expansion = card.querySelector('.feature-expansion');
    if (!expansion) return;

    var existing = expansion.querySelector('.bamboo-svg');
    if (existing) existing.remove();

    var idx = Array.prototype.slice.call(document.querySelectorAll('.feature-card')).indexOf(card);
    var seed = (idx + 1) * 3571;

    var svg = createBambooSVG(seed, idx);
    expansion.insertAdjacentHTML('afterbegin', svg);

    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        expansion.classList.add('bamboo-growing');
      });
    });

    expansion.addEventListener('animationend', function () {
      expansion.classList.remove('bamboo-growing');
    }, { once: true });
  }

  function makeRand(seed) {
    var s = seed;
    return function () {
      s = (s * 1664525 + 1013904223) >>> 0;
      return s / 0xffffffff;
    };
  }

  function createBambooSVG(seed, idx) {
    var rand = makeRand(seed);
    var r = function () { return rand(); };

    // viewBox: narrow vertical strip
    var W = 120, H = 90;

    // 4 stalk segments (joints)
    var segs = [];
    var totalH = H;
    var segH = totalH / 4.5;
    for (var i = 0; i < 4; i++) {
      var y = H - (i + 1) * segH;
      var segW = 10 + r() * 4 - i * 1.5; // slightly narrower toward top
      segs.push({ y: y, w: segW });
    }

    var p = [];

    // Ground / soil line
    p.push('<path class="bamboo-ground" d="M0,' + H + ' L' + W + ',' + H + '" stroke="#8a7a5a" stroke-width="2" fill="none"/>');

    // Stalk segments - each a rounded rectangle shape
    segs.forEach(function (seg, i) {
      var cx = W * 0.5;
      var topY = seg.y;
      var botY = seg.y + segH;
      var hw = seg.w / 2;
      // Simple stalk body
      p.push('<path class="bamboo-stalk" d="M' + (cx - hw) + ',' + botY + ' L' + (cx - hw) + ',' + topY + ' L' + (cx + hw) + ',' + topY + ' L' + (cx + hw) + ',' + botY + ' Z" fill="#4a8c5c" style="animation-delay:' + (i * 0.15).toFixed(2) + 's"/>');
      // Joint ring
      p.push('<ellipse class="bamboo-joint" cx="' + cx + '" cy="' + topY + '" rx="' + (hw + 1) + '" ry="2" fill="#3d7a4e" style="animation-delay:' + (i * 0.15 + 0.05).toFixed(2) + 's"/>');
    });

    // Young leaves at top
    var topCX = W * 0.5;
    var topY = segs[segs.length - 1].y;
    var leafCount = 4 + Math.floor(r() * 3);
    for (var l = 0; l < leafCount; l++) {
      var side = l % 2 === 0 ? 1 : -1;
      var lt = l / leafCount;
      var leafX = topCX + side * (3 + lt * 8);
      var leafY = topY - 2 - lt * 4;
      var leafLen = 14 + r() * 12;
      var angle = side * (30 + r() * 40);
      var rad = (angle - 90) * Math.PI / 180;
      var leafX2 = leafX + Math.cos(rad) * leafLen;
      var leafY2 = leafY + Math.sin(rad) * leafLen;
      p.push('<line class="bamboo-leaf" x1="' + leafX.toFixed(1) + '" y1="' + leafY.toFixed(1) + '" x2="' + leafX2.toFixed(1) + '" y2="' + leafY2.toFixed(1) + '" stroke="#5a9a6a" stroke-width="1.5" stroke-linecap="round" style="animation-delay:' + (0.5 + l * 0.05).toFixed(2) + 's"/>');
    }

    return '<svg class="bamboo-svg" viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="xMidYMax meet" aria-hidden="true" focusable="false">' +
      '<defs><linearGradient id="bg' + idx + '" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="white" stop-opacity="0"/><stop offset="70%" stop-color="white" stop-opacity="0.4"/><stop offset="100%" stop-color="white" stop-opacity="0.85"/></linearGradient></defs>' +
      '<g>' + p.join('') + '</g>' +
      '<rect width="' + W + '" height="' + H + '" fill="url(#bg' + idx + ')"/>' +
      '</svg>';
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
