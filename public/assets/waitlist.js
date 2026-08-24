// Early-access form. Never reports a signup it did not store.
(function () {
  var form = document.getElementById('wl');
  if (!form) return;
  form.addEventListener('submit', async function (e) {
    e.preventDefault();
    var email = document.getElementById('wlemail').value.trim();
    var note = document.getElementById('wlnote').value.trim();
    var msg = document.getElementById('wlmsg');
    msg.className = 'formmsg';
    msg.textContent = '';
    try {
      var r = await fetch('/api/waitlist', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email, note: note, source: form.dataset.source || 'site' })
      });
      var data = await r.json();
      if (data.stored) {
        msg.className = 'formmsg ok';
        msg.textContent = 'Recorded — thank you. I read every one.';
        return;
      }
      throw new Error(data.error || 'unavailable');
    } catch (err) {
      // Built as DOM nodes, not markup: nothing from the network is ever parsed as HTML.
      msg.className = 'formmsg err';
      msg.textContent = 'Signup store is offline right now, so nothing was saved. ';
      var a = document.createElement('a');
      a.href = 'mailto:' + form.dataset.contact +
        '?subject=' + encodeURIComponent('Pramana early access') +
        '&body=' + encodeURIComponent(note ? ('From: ' + email + '\n\n' + note) : ('From: ' + email));
      a.textContent = 'Send it by mail instead →';
      msg.appendChild(a);
    }
  });
})();
