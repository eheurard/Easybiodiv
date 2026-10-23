/* Bandeau d'information cookies (templates/includes/cookie_notice.html).
   Le choix « J'ai compris » est mémorisé dans le localStorage du navigateur,
   jamais envoyé au serveur. Stockage indisponible : le bandeau réapparaît à
   chaque page, ce qui reste sans conséquence. */
(function () {
  var KEY = 'cookie-notice-dismissed';
  var notice = document.getElementById('cookie-notice');
  var closeBtn = document.getElementById('cookie-notice-close');
  if (!notice || !closeBtn) return;

  var dismissed = false;
  try { dismissed = localStorage.getItem(KEY) === '1'; } catch (e) { /* stockage indisponible */ }
  if (dismissed) return;

  notice.hidden = false;
  closeBtn.addEventListener('click', function () {
    notice.hidden = true;
    try { localStorage.setItem(KEY, '1'); } catch (e) { /* stockage indisponible */ }
  });
})();
