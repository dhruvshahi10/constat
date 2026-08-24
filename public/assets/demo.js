// Live demo client.
//
// SECURITY: nothing that comes back from /api/ask is ever assigned to innerHTML.
// An answer is a paragraph lifted verbatim from an evidence document, and a
// document is attacker-influenced input in exactly the threat model this
// product is about — a paragraph containing markup would otherwise execute in
// the visitor's browser. Every network-derived value below is set with
// textContent or appended as a text node.
(function () {
  var $ = function (id) { return document.getElementById(id); };
  var SAMPLES = [
    'Are you ISO/IEC 27001 certified?',
    'Within how many days of contract termination is customer data deleted?',
    'Has an independent penetration test been performed in the last 12 months?',
    'Will you contractually commit to unlimited liability for any breach?',
    'Is customer data encrypted at rest?',
    'Do you use customer data to train models?',
    "What does Globex's policy say about access reviews?"
  ];

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined && text !== null) n.textContent = text;
    return n;
  }

  function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }

  function chipClass(v) {
    if (v.indexOf('CITED · GATE-CLEAN') === 0) return 'chip c-ok';
    if (v.indexOf('CITED') === 0) return 'chip c-rev';
    return 'chip c-warn';
  }

  async function boot() {
    var info = await (await fetch('/api/ask')).json();
    var tenants = info.tenants || ['acme'];
    var sel = $('tenant');
    clear(sel);
    tenants.forEach(function (t) {
      var o = document.createElement('option');
      o.value = t;
      o.textContent = 'workspace: ' + t;
      sel.appendChild(o);
    });
    var chips = $('chips');
    clear(chips);
    SAMPLES.forEach(function (sample) {
      var b = el('button', null, sample);
      b.type = 'button';
      b.addEventListener('click', function () { $('q').value = sample; });
      chips.appendChild(b);
    });
  }

  function render(data) {
    var c = data.contract;
    $('verdict').textContent = data.verdict;
    $('verdict').className = chipClass(data.verdict);

    var answer = $('answer');
    clear(answer);
    if (c.answer) {
      answer.appendChild(document.createTextNode(c.answer));
    } else {
      answer.appendChild(el('em', null, 'No answer released.'));
    }

    var prov = $('prov');
    clear(prov);
    if (c.citations.length) {
      var box = el('div', 'prov');
      c.citations.forEach(function (x, i) {
        if (i) box.appendChild(document.createElement('br'));
        box.appendChild(document.createTextNode(
          x.source_id + ' · v' + x.version + ' · ' + x.location));
      });
      prov.appendChild(box);
    } else {
      prov.appendChild(el('div', 'prov p-warn',
        'no citation released · routed to ' + (c.route || 'no-evidence')));
    }

    var gaps = $('gaps');
    clear(gaps);
    c.gaps.forEach(function (g) { gaps.appendChild(el('div', 'gap', '▸ ' + g)); });

    $('meta').textContent =
      'coverage=' + c.evidence_coverage + ' · risk=' + c.risk +
      ' · drafter=' + c.drafter +
      ' · human_review=' + (c.requires_human ? 'required' : 'not required') +
      (c.gate_flags.length ? ' · flags: ' + c.gate_flags.join(' | ') : '');
    $('result').style.display = 'block';
  }

  function renderError(message) {
    $('verdict').textContent = 'ENGINE ERROR';
    $('verdict').className = 'chip c-bad';
    clear($('answer'));
    $('answer').appendChild(el('em', null, message));
    clear($('prov'));
    clear($('gaps'));
    $('meta').textContent = '';
    $('result').style.display = 'block';
  }

  $('ask').addEventListener('click', async function () {
    var q = $('q').value.trim();
    if (!q) return;
    $('spin').style.display = 'inline';
    $('result').style.display = 'none';
    $('ask').disabled = true;
    try {
      var r = await fetch('/api/ask', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q, tenant: $('tenant').value })
      });
      var data = await r.json();
      if (data.error) throw new Error(data.error);
      render(data);
    } catch (e) {
      renderError(e.message);
    }
    $('spin').style.display = 'none';
    $('ask').disabled = false;
  });

  boot();
})();
