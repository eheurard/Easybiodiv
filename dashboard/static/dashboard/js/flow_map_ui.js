'use strict';

// Outils partagés par les scripts de la carte des flux : URL et sélecteurs (tous
// les visiteurs), écriture JSON et liste de recherche serveur (Créateurs).
//
//   FlowMapUI.idUrl(template, id[, id2])  remplace les « /0/ » d'une URL
//                                  {% url … pk=0 %}, dans l'ordre (company_pk=0 pk=0)
//   FlowMapUI.rangeQuery(start, end) -> « ?start=…&end=… »
//   FlowMapUI.cssEscape(value)     valeur sûre dans un sélecteur [data-key="…"]
//   FlowMapUI.post(url, payload) -> Promise<{ok, status, data}>
//   FlowMapUI.getJson(url)       -> Promise<{ok, status, data}>
//   FlowMapUI.combobox(opts)     -> {hide(), cancel(), set(changes)}
//     opts.input     <input role=combobox>   opts.list  <ul role=listbox>
//     opts.type      'asset'|'company'|'country'|'region'|'commodity'
//     opts.url       URL de flow_map_search
//     opts.canCreate vrai : « + Créer « … »… » proposé sans résultat exact
//     opts.onSelect(item)  item = {id, name, detail} choisi dans la liste
//     opts.onCreate(name)  option de création choisie
//     opts.onInput()       à chaque frappe (avant la recherche)
//   set(changes) modifie ces options (ex. {type, canCreate}) ; cancel() ferme la
//   liste et ignore la recherche en cours.
// Recherche à partir de 2 caractères, après 200 ms ; une réponse dépassée par
// une frappe plus récente est ignorée. Flèches, Entrée et Échap au clavier.
window.FlowMapUI = (function () {
  var SEARCH_MIN = 2;
  var SEARCH_DELAY = 200;

  function idUrl(template) {
    var url = template;
    for (var i = 1; i < arguments.length; i += 1) {
      url = url.replace('/0/', '/' + arguments[i] + '/');
    }
    return url;
  }

  function rangeQuery(start, end) {
    return '?start=' + encodeURIComponent(start) + '&end=' + encodeURIComponent(end);
  }

  function cssEscape(value) {
    return window.CSS && CSS.escape ? CSS.escape(value) : value;
  }

  function getCookie(name) {
    var match = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
    return match ? match.pop() : '';
  }

  function answer(response) {
    return response.json().catch(function () { return {}; }).then(function (data) {
      return { ok: response.ok, status: response.status, data: data || {} };
    });
  }

  function post(url, payload) {
    return fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
        'X-CSRFToken': getCookie('csrftoken'),
      },
      body: JSON.stringify(payload),
    }).then(answer);
  }

  function getJson(url) {
    return fetch(url, { headers: { Accept: 'application/json' } }).then(answer);
  }

  function combobox(opts) {
    var input = opts.input;
    var list = opts.list;
    var options = [];
    var active = -1;
    var request = 0;
    var timer = 0;

    function hide() {
      list.hidden = true;
      input.setAttribute('aria-expanded', 'false');
      input.removeAttribute('aria-activedescendant');
      active = -1;
    }

    function cancel() {
      clearTimeout(timer);
      request += 1;
      hide();
    }

    function render(q, results) {
      options = results.map(function (r) {
        return { item: r, label: r.detail ? r.name + ' — ' + r.detail : r.name };
      });
      var lower = q.toLowerCase();
      var exact = results.some(function (r) { return r.name.toLowerCase() === lower; });
      if (opts.canCreate && !exact) {
        options.push({
          create: q, label: interpolate(gettext('+ Créer « %(name)s »…'), { name: q }, true),
        });
      }
      list.textContent = '';
      if (!options.length) {
        var none = document.createElement('li');
        none.className = 'fm-combo__none';
        none.setAttribute('role', 'option');
        none.setAttribute('aria-disabled', 'true');
        none.textContent = gettext('Aucun résultat.');
        list.appendChild(none);
      }
      options.forEach(function (option, i) {
        var li = document.createElement('li');
        li.id = list.id + '-option-' + i;
        li.className = 'fm-combo__option' + (option.create ? ' fm-combo__option--create' : '');
        li.setAttribute('role', 'option');
        li.setAttribute('aria-selected', 'false');
        li.textContent = option.label;
        li.addEventListener('click', function () { choose(i); });
        list.appendChild(li);
      });
      active = -1;
      input.removeAttribute('aria-activedescendant');
      list.hidden = false;
      input.setAttribute('aria-expanded', 'true');
    }

    function search(q) {
      var mine = ++request;
      var url = opts.url + '?type=' + encodeURIComponent(opts.type) + '&q='
        + encodeURIComponent(q);
      getJson(url)
        .then(function (res) {
          if (!res.ok) throw new Error('HTTP ' + res.status);
          if (mine === request && document.activeElement === input) {
            render(q, res.data.results || []);
          }
        })
        .catch(function (err) {
          if (mine !== request) return;
          console.error('flow_map search failed:', err);
          if (document.activeElement === input) render(q, []);
        });
    }

    function setActive(index) {
      var items = list.querySelectorAll('.fm-combo__option');
      if (!items.length) return;
      active = (index + items.length) % items.length;
      Array.prototype.forEach.call(items, function (li, i) {
        li.classList.toggle('is-active', i === active);
        li.setAttribute('aria-selected', i === active ? 'true' : 'false');
      });
      input.setAttribute('aria-activedescendant', items[active].id);
      items[active].scrollIntoView({ block: 'nearest' });
    }

    function choose(index) {
      var option = options[index];
      if (!option) return;
      hide();
      if (option.create) {
        if (opts.onCreate) opts.onCreate(option.create);
        return;
      }
      input.value = option.item.name;
      opts.onSelect(option.item);
    }

    input.addEventListener('input', function () {
      if (opts.onInput) opts.onInput();
      clearTimeout(timer);
      var q = input.value.trim();
      if (q.length < SEARCH_MIN) {
        request += 1;
        hide();
        return;
      }
      timer = setTimeout(function () { search(q); }, SEARCH_DELAY);
    });
    input.addEventListener('keydown', function (event) {
      var open = !list.hidden;
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        if (!open) return;
        event.preventDefault();
        setActive(active + (event.key === 'ArrowDown' ? 1 : -1));
      } else if (event.key === 'Enter' && open) {
        event.preventDefault();
        if (active >= 0) choose(active);
      } else if (event.key === 'Escape' && open) {
        event.preventDefault();
        hide();
      }
    });
    input.addEventListener('blur', hide);
    list.addEventListener('mousedown', function (event) { event.preventDefault(); });

    function set(changes) {
      Object.assign(opts, changes);
    }

    return { hide: hide, cancel: cancel, set: set };
  }

  return {
    idUrl: idUrl, rangeQuery: rangeQuery, cssEscape: cssEscape, post: post, getJson: getJson,
    combobox: combobox,
  };
})();
