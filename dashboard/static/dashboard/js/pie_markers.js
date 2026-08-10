'use strict';

// Marqueurs camembert réutilisables pour une carte MapLibre.
// Partagé entre la page Dette écologique et l'onglet Risque de transition.
window.PieMarkers = (function () {
  var PALETTE = [
    '#2d6a4f', '#74c69d', '#d4a373', '#e76f51',
    '#457b9d', '#e9c46a', '#8338ec', '#f4a261',
  ];
  var NS = 'http://www.w3.org/2000/svg';

  // Couleur stable par commodité (ordre alphabétique du nom).
  function colorMap(commodities) {
    var map = {};
    commodities.slice().sort(function (a, b) {
      return a.name.localeCompare(b.name);
    }).forEach(function (c, i) {
      map[c.name] = PALETTE[i % PALETTE.length];
    });
    return map;
  }

  // Élément SVG camembert pour un point (commodities: [{name, pct}]).
  function buildPieEl(point, r, colors, handlers) {
    var size = r * 2, cx = r, cy = r;
    var svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('width', size);
    svg.setAttribute('height', size);
    svg.setAttribute('viewBox', '0 0 ' + size + ' ' + size);
    svg.style.cursor = 'pointer';
    svg.style.overflow = 'visible';

    if (point.commodities.length === 1) {
      var disc = document.createElementNS(NS, 'circle');
      disc.setAttribute('cx', cx); disc.setAttribute('cy', cy);
      disc.setAttribute('r', r);
      disc.setAttribute('fill', colors[point.commodities[0].name] || '#ccc');
      svg.appendChild(disc);
    } else {
      var startAngle = -Math.PI / 2;
      point.commodities.forEach(function (c) {
        var slice = c.pct * 2 * Math.PI;
        var endAngle = startAngle + slice;
        var x1 = cx + r * Math.cos(startAngle), y1 = cy + r * Math.sin(startAngle);
        var x2 = cx + r * Math.cos(endAngle), y2 = cy + r * Math.sin(endAngle);
        var large = slice > Math.PI ? 1 : 0;
        var path = document.createElementNS(NS, 'path');
        path.setAttribute('d',
          'M' + cx + ',' + cy + ' L' + x1 + ',' + y1 +
          ' A' + r + ',' + r + ' 0 ' + large + ',1 ' + x2 + ',' + y2 + ' Z');
        path.setAttribute('fill', colors[c.name] || '#ccc');
        path.setAttribute('stroke', '#fff');
        path.setAttribute('stroke-width', '1');
        svg.appendChild(path);
        startAngle = endAngle;
      });
    }

    var border = document.createElementNS(NS, 'circle');
    border.setAttribute('cx', cx); border.setAttribute('cy', cy);
    border.setAttribute('r', r); border.setAttribute('fill', 'none');
    border.setAttribute('stroke', '#fff'); border.setAttribute('stroke-width', '2');
    svg.appendChild(border);

    if (handlers) {
      if (handlers.onEnter) {
        svg.addEventListener('mouseenter', function (e) { handlers.onEnter(point, e); });
      }
      if (handlers.onMove) { svg.addEventListener('mousemove', handlers.onMove); }
      if (handlers.onLeave) { svg.addEventListener('mouseleave', handlers.onLeave); }
    }
    return svg;
  }

  // Crée les marqueurs MapLibre pour `points`. Rayon ∝ √(valeur / max).
  function render(map, points, colors, handlers) {
    var markers = [];
    if (!map || !points || !points.length) { return markers; }
    var maxVal = points.reduce(function (m, p) {
      return p.total_lbiodiv > m ? p.total_lbiodiv : m;
    }, 0);
    var MIN_R = 8, MAX_R = 30;
    points.forEach(function (point) {
      var r = maxVal > 0
        ? Math.max(MIN_R, MAX_R * Math.sqrt(point.total_lbiodiv / maxVal))
        : MIN_R;
      var el = buildPieEl(point, r, colors, handlers);
      var marker = new maplibregl.Marker({ element: el, anchor: 'center' })
        .setLngLat([point.longitude, point.latitude])
        .addTo(map);
      markers.push(marker);
    });
    return markers;
  }

  return {
    PALETTE: PALETTE, colorMap: colorMap,
    buildPieEl: buildPieEl, render: render,
  };
})();
