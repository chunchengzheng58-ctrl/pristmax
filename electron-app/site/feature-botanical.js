/** Pristmax - All Rights Reserved. Copyright © 2024-2026 */
// Pine botanical animation for feature card expansions.

(function () {
  var REDUCED = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function init() {
    var cards = document.querySelectorAll('.feature-card');
    cards.forEach(function (card) {
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

    var idx = Array.prototype.slice.call(document.querySelectorAll('.feature-card')).indexOf(card);
    var seed = (idx + 1) * 7919;

    var svg = createPineSVG(seed, idx);
    expansion.insertAdjacentHTML('afterbegin', svg);

    // Trigger animation
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        expansion.classList.add('pine-growing');
      });
    });

    expansion.addEventListener('animationend', function () {
      expansion.classList.remove('pine-growing');
    }, { once: true });
  }

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

    // Compact viewBox - fits within ~80px expansion height
    var W = 280, H = 100;

    // Trunk
    var tx = W * 0.5;
    var tbY = H;
    var trunkH = 45 + r() * 15;
    var ttX = tx + (r() - 0.5) * 4;
    var ttY = tbY - trunkH;

    // 3 branch levels
    var lvls = [];
    for (var i = 0; i < 3; i++) {
      var t = (i + 1) / 4;
      var ly = tbY - trunkH * t;
      var lx = tx + (ttX - tx) * t;
      var llen = (18 + r() * 12) * (1 - t * 0.3);
      var dir = (i % 2 === 0) ? 1 : -1;
      lvls.push({ x: lx, y: ly, len: llen, dir: dir });
    }

    var p = [];

    // Trunk
    p.push('<path class="pine-trunk" d="M' + tx.toFixed(1) + ',' + tbY + ' L' + ttX.toFixed(1) + ',' + ttY.toFixed(1) + '"/>');

    // Branches + needles
    lvls.forEach(function (lv, i) {
      var d = (0.2 + i * 0.1).toFixed(2);

      // Right branch
      var rEx = lv.x + lv.dir * lv.len;
      var rEy = lv.y - lv.len * 0.2;
      p.push('<path class="pine-branch" d="M' + lv.x.toFixed(1) + ',' + lv.y.toFixed(1) + ' Q' + (lv.x + lv.dir * lv.len * 0.5).toFixed(1) + ',' + (lv.y - 4) + ' ' + rEx.toFixed(1) + ',' + rEy.toFixed(1) + '" style="animation-delay:' + d + 's"/>');

      // Left branch (mirror)
      var mlen = lv.len * (0.7 + r() * 0.2);
      var mEx = lv.x - lv.dir * mlen;
      var mEy = lv.y - mlen * 0.2;
      p.push('<path class="pine-branch" d="M' + lv.x.toFixed(1) + ',' + lv.y.toFixed(1) + ' Q' + (lv.x - lv.dir * mlen * 0.5).toFixed(1) + ',' + (lv.y - 3) + ' ' + mEx.toFixed(1) + ',' + mEy.toFixed(1) + '" style="animation-delay:' + (parseFloat(d) + 0.04).toFixed(2) + 's"/>');

      // Needle clusters at branch tips
      var nCount = 3 + Math.floor(r() * 3);
      for (var n = 0; n < nCount; n++) {
        var nt = n / nCount;
        var nx = lv.x + lv.dir * lv.len * nt * 0.85;
        var ny = lv.y - 2 + r() * 4;
        var nlen = 8 + r() * 12;
        var nAngle = lv.dir * (50 + r() * 50) * (n % 2 === 0 ? 1 : -1);
        var rad = (nAngle - 90) * Math.PI / 180;
        var nx2 = nx + Math.cos(rad) * nlen;
        var ny2 = ny + Math.sin(rad) * nlen;
        var nd = (0.4 + i * 0.08 + n * 0.02).toFixed(2);
        p.push('<line class="pine-needle" x1="' + nx.toFixed(1) + '" y1="' + ny.toFixed(1) + '" x2="' + nx2.toFixed(1) + '" y2="' + ny2.toFixed(1) + '" style="animation-delay:' + nd + 's"/>');
      }
    });

    return '<svg class="pine-svg" viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="xMaxYMax meet" aria-hidden="true" focusable="false">' +
      '<defs><linearGradient id="pg' + idx + '" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="white" stop-opacity="0"/><stop offset="60%" stop-color="white" stop-opacity="0.5"/><stop offset="100%" stop-color="white" stop-opacity="0.9"/></linearGradient></defs>' +
      '<g>' + p.join('') + '</g>' +
      '<rect width="' + W + '" height="' + H + '" fill="url(#pg' + idx + ')"/>' +
      '</svg>';
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
