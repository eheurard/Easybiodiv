'use strict';

/* ───────────────────────── Supply chain ────────────────────────────────────
 * Chaque lien fournisseur → asset est dessiné comme une courbe de Bézier
 * quadratique. De petites flèches glissent le long de la courbe (du
 * fournisseur vers l'asset) via une boucle requestAnimationFrame qui met à
 * jour une source GeoJSON de points orientés. Les fournisseurs non détenus
 * sont des points cliquables.
 *
 * Partagé entre la page LEAP Locate et la Vue d'ensemble :
 *   const supply = SupplyChain.create(map, { colorFor, legend: { box, list } });
 *   supply.addLayers('id-couche-assets'); // au 'load' puis après chaque setStyle
 *   supply.setData(locateData);            // réponse de l'API leap-locate
 *   supply.setVisible(true);
 * Dépend de escHtml (main.js) et de maplibregl.
 * ------------------------------------------------------------------------ */
window.SupplyChain = (function () {
  const DEFAULT_COLOR = '#1f6f5c'; // teal, couleur par défaut / repli

  // Palette catégorielle par défaut pour distinguer les commodités.
  const PALETTE = [
    '#1f6f5c', '#c2603f', '#e0a83c', '#4f7cac', '#8a5a9e',
    '#6b8f3d', '#cf5d8a', '#3d9fa3', '#b5793b', '#7a6cc4',
  ];

  const ARROWS_PER_LINK = 4; // nombre de flèches simultanées sur chaque courbe
  const ARROW_SPEED = 0.006; // progression de la phase par frame (boucle 0→1)
  const CURVE_BOW = 0.18;    // amplitude de la courbure (0 = ligne droite)
  const CURVE_SAMPLES = 48;  // points échantillonnés pour tracer la courbe

  const SOURCE_IDS = ['ll-supplier-lines', 'll-supplier-arrows', 'll-suppliers'];
  const LAYER_IDS = ['ll-supplier-lines-layer', 'll-supplier-arrows-layer', 'll-suppliers-layer'];

  function emptyCollection() { return { type: 'FeatureCollection', features: [] }; }

  // Nom d'image MapLibre déterministe pour une couleur donnée.
  function arrowImageName(color) { return 'll-arrow-' + color.replace('#', ''); }

  // Point de contrôle : milieu décalé perpendiculairement au segment.
  function control(p0, p1) {
    const mx = (p0[0] + p1[0]) / 2;
    const my = (p0[1] + p1[1]) / 2;
    const dx = p1[0] - p0[0];
    const dy = p1[1] - p0[1];
    // Vecteur perpendiculaire (-dy, dx) → courbure constante du même côté.
    return [mx - dy * CURVE_BOW, my + dx * CURVE_BOW];
  }

  function bez(p0, c, p1, t) {
    const u = 1 - t;
    return [
      u * u * p0[0] + 2 * u * t * c[0] + t * t * p1[0],
      u * u * p0[1] + 2 * u * t * c[1] + t * t * p1[1],
    ];
  }

  function bezTangent(p0, c, p1, t) {
    const u = 1 - t;
    return [
      2 * u * (c[0] - p0[0]) + 2 * t * (p1[0] - c[0]),
      2 * u * (c[1] - p0[1]) + 2 * t * (p1[1] - c[1]),
    ];
  }

  // Cap (degrés, sens horaire depuis le nord) pour orienter l'icône flèche.
  function bearing(tan, lat) {
    const dx = tan[0] * Math.cos(lat * Math.PI / 180); // compression des longitudes
    const dy = tan[1];
    return Math.atan2(dx, dy) * 180 / Math.PI;
  }

  // Icône flèche dessinée sur un canvas, pointant vers le haut (= nord).
  function arrowImage(color) {
    const size = 18;
    const c = document.createElement('canvas');
    c.width = c.height = size;
    const ctx = c.getContext('2d');
    ctx.fillStyle = color || DEFAULT_COLOR;
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.9)';
    ctx.lineWidth = 1.3;
    ctx.beginPath();
    ctx.moveTo(size / 2, 2);          // pointe (haut)
    ctx.lineTo(size - 3, size - 4);   // aile droite
    ctx.lineTo(size / 2, size - 7);   // encoche
    ctx.lineTo(3, size - 4);          // aile gauche
    ctx.closePath();
    ctx.fill();
    ctx.stroke();
    return ctx.getImageData(0, 0, size, size);
  }

  function create(map, opts) {
    const options = opts || {};
    const state = {
      data: null,       // réponse leap-locate (suppliers, supplier_links)
      visible: false,
      links: [],        // courbes mises en cache pour l'animation
      colors: {},       // commodité → couleur des liens courants
      animFrame: null,  // id requestAnimationFrame de l'animation des flèches
      animPhase: 0,
      bound: false,     // évènements déjà liés à la carte ?
      arrowsEmpty: false, // dernier setData déjà vidé : inutile de le répéter
    };

    function linkFeatures() {
      return (state.data && state.data.supplier_links && state.data.supplier_links.features) || [];
    }

    // Commodité → couleur, par ordre alphabétique des commodités des liens.
    function buildColors() {
      const names = Array.from(
        new Set(linkFeatures().map(f => f.properties && f.properties.commodity).filter(Boolean))
      ).sort();
      const colors = {};
      names.forEach((n, i) => {
        colors[n] = options.colorFor ? options.colorFor(n) : PALETTE[i % PALETTE.length];
      });
      return colors;
    }

    // (Ré)enregistre une icône flèche par couleur de commodité + l'icône par défaut.
    function ensureArrowImages() {
      if (!map.hasImage('ll-arrow')) map.addImage('ll-arrow', arrowImage(DEFAULT_COLOR));
      const colors = new Set(Object.values(state.colors));
      colors.add(DEFAULT_COLOR);
      colors.forEach((col) => {
        const name = arrowImageName(col);
        if (!map.hasImage(name)) map.addImage(name, arrowImage(col));
      });
    }

    // Légende des couleurs de commodités, visible uniquement avec la supply chain.
    function renderLegend() {
      const legend = options.legend;
      if (!legend || !legend.box || !legend.list) return;
      const names = Object.keys(state.colors);
      if (!names.length) { legend.box.hidden = true; legend.list.innerHTML = ''; return; }
      legend.list.innerHTML = names.map(n =>
        `<li><span class="map-legend__dot" style="background:${state.colors[n]}"></span>${escHtml(n)}</li>`
      ).join('');
      legend.box.hidden = !state.visible;
    }

    function bindEvents() {
      if (state.bound) return;
      state.bound = true;
      map.on('click', 'll-suppliers-layer', (e) => {
        const p = e.features[0].properties;
        let comms = p.commodities;
        if (typeof comms === 'string') { try { comms = JSON.parse(comms); } catch (_) { comms = []; } }
        comms = comms || [];
        // Le point reprend la couleur de la commodité dans la légende.
        const list = comms.length
          ? `<div class="asset-popup__body">${comms.map(c => {
              const dot = state.colors[c] ? ` style="background:${state.colors[c]}"` : '';
              return `<div class="asset-popup__prod-row">
                <span class="asset-popup__prod-dot"${dot}></span>
                <span class="asset-popup__prod-name">${escHtml(c)}</span>
              </div>`;
            }).join('')}</div>`
          : '';
        new maplibregl.Popup({ maxWidth: '260px' })
          .setLngLat(e.lngLat)
          .setHTML(`
            <div class="asset-popup">
              <div class="asset-popup__header">
                <div class="asset-popup__name">${escHtml(p.name)}</div>
                <div class="asset-popup__meta">${escHtml(p.country || '')}</div>
                <span class="asset-popup__badge">Fournisseur</span>
              </div>
              ${list}
            </div>`)
          .addTo(map);
      });
      map.on('mouseenter', 'll-suppliers-layer', () => { map.getCanvas().style.cursor = 'pointer'; });
      map.on('mouseleave', 'll-suppliers-layer', () => { map.getCanvas().style.cursor = ''; });
    }

    function updateArrows(phase) {
      const src = map.getSource('ll-supplier-arrows');
      if (!src) return;
      // Sans lien, un seul setData vide suffit : inutile de le rejouer à chaque frame.
      if (!state.links.length) {
        if (state.arrowsEmpty) return;
        state.arrowsEmpty = true;
      } else {
        state.arrowsEmpty = false;
      }
      const feats = [];
      state.links.forEach(l => {
        for (let k = 0; k < ARROWS_PER_LINK; k++) {
          const t = (phase + k / ARROWS_PER_LINK) % 1;
          const pos = bez(l.p0, l.c, l.p1, t);
          const tan = bezTangent(l.p0, l.c, l.p1, t);
          feats.push({
            type: 'Feature',
            geometry: { type: 'Point', coordinates: pos },
            properties: { bearing: bearing(tan, pos[1]), icon: l.icon },
          });
        }
      });
      src.setData({ type: 'FeatureCollection', features: feats });
    }

    // Recalcule courbes + points fournisseurs depuis state.data.
    function sync() {
      state.colors = buildColors();
      const links = [];
      const lineFeats = [];
      linkFeatures().forEach(f => {
        const [p0, p1] = f.geometry.coordinates;
        const c = control(p0, p1);
        const commodity = f.properties && f.properties.commodity;
        const color = state.colors[commodity] || DEFAULT_COLOR;
        links.push({ p0: p0, c: c, p1: p1, icon: arrowImageName(color) });
        const pts = [];
        for (let i = 0; i <= CURVE_SAMPLES; i++) pts.push(bez(p0, c, p1, i / CURVE_SAMPLES));
        lineFeats.push({
          type: 'Feature',
          geometry: { type: 'LineString', coordinates: pts },
          properties: { color: color },
        });
      });
      state.links = links;
      renderLegend();

      // Couches pas encore créées (carte en chargement) : addLayers resynchronisera.
      if (!map.getSource('ll-supplier-lines')) return;
      ensureArrowImages();
      map.getSource('ll-supplier-lines').setData({ type: 'FeatureCollection', features: lineFeats });
      const supFeats = (state.data && state.data.suppliers && state.data.suppliers.features) || [];
      map.getSource('ll-suppliers').setData({ type: 'FeatureCollection', features: supFeats });
      // Si l'animation tourne mais qu'il n'y a plus de lien, la source se vide.
      if (state.visible) updateArrows(state.animPhase);
    }

    // Sources, couches et évènements. Idempotent : selon le style, setStyle peut
    // conserver (diff) ou détruire les sources custom ; on ne recrée que ce qui
    // manque. Les courbes passent sous beforeLayerId (les points d'assets),
    // flèches et fournisseurs au-dessus.
    function addLayers(beforeLayerId) {
      ensureArrowImages();
      const vis = state.visible ? 'visible' : 'none';
      SOURCE_IDS.forEach((id) => {
        if (!map.getSource(id)) map.addSource(id, { type: 'geojson', data: emptyCollection() });
      });
      const before = beforeLayerId && map.getLayer(beforeLayerId) ? beforeLayerId : undefined;
      if (!map.getLayer('ll-supplier-lines-layer')) {
        map.addLayer({
          id: 'll-supplier-lines-layer',
          type: 'line',
          source: 'll-supplier-lines',
          layout: { 'line-cap': 'round', 'line-join': 'round', visibility: vis },
          paint: {
            'line-color': ['coalesce', ['get', 'color'], DEFAULT_COLOR],
            'line-width': 1.6,
            'line-opacity': 0.4,
            'line-dasharray': [2, 2],
          },
        }, before);
      }
      if (!map.getLayer('ll-supplier-arrows-layer')) {
        map.addLayer({
          id: 'll-supplier-arrows-layer',
          type: 'symbol',
          source: 'll-supplier-arrows',
          layout: {
            'icon-image': ['coalesce', ['get', 'icon'], 'll-arrow'],
            'icon-size': 0.85,
            'icon-rotate': ['get', 'bearing'],
            'icon-rotation-alignment': 'map',
            'icon-allow-overlap': true,
            'icon-ignore-placement': true,
            visibility: vis,
          },
        });
      }
      if (!map.getLayer('ll-suppliers-layer')) {
        map.addLayer({
          id: 'll-suppliers-layer',
          type: 'circle',
          source: 'll-suppliers',
          layout: { visibility: vis },
          paint: {
            'circle-radius': 5.5,
            'circle-color': DEFAULT_COLOR,
            'circle-opacity': 0.9,
            'circle-stroke-width': 1.5,
            'circle-stroke-color': '#ffffff',
          },
        });
      }
      bindEvents();
      sync();
    }

    function start() {
      if (state.animFrame) return;
      const step = () => {
        state.animPhase = (state.animPhase + ARROW_SPEED) % 1;
        updateArrows(state.animPhase);
        state.animFrame = requestAnimationFrame(step);
      };
      state.animFrame = requestAnimationFrame(step);
    }

    function stop() {
      if (state.animFrame) cancelAnimationFrame(state.animFrame);
      state.animFrame = null;
    }

    return {
      addLayers: addLayers,
      setData(data) { state.data = data; sync(); },
      setVisible(visible) {
        state.visible = visible;
        const vis = visible ? 'visible' : 'none';
        LAYER_IDS.forEach(id => {
          if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', vis);
        });
        renderLegend();
        if (visible) start(); else stop();
      },
      isVisible() { return state.visible; },
      colors() { return state.colors; },
      stop: stop,
      resume() { if (state.visible) start(); },
    };
  }

  return { create: create, DEFAULT_COLOR: DEFAULT_COLOR, PALETTE: PALETTE };
})();
