/* =====================================================================
   lite.js — the only JavaScript the lite site adds on top of script.js
   ---------------------------------------------------------------------
   There is no form-processing backend any more, so the contact,
   volunteer and newsletter forms open the visitor's email app with a
   ready-made message to cbnetwork.sierraleone@gmail.com.

   Any <form data-mailto="address" data-subject="…{name}…"> is handled.
   ===================================================================== */
(function () {
  'use strict';

  var CBN_EMAIL = 'cbnetwork.sierraleone@gmail.com';

  function labelFor(form, el) {
    var l = el.id ? form.querySelector('label[for="' + el.id + '"]') : null;
    var t = (l ? l.textContent : el.name) || el.name || '';
    return t.replace(/\*/g, '').replace(/\s+/g, ' ').trim();
  }

  document.querySelectorAll('form[data-mailto]').forEach(function (form) {
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      if (!form.checkValidity()) { form.reportValidity(); return; }

      var to = form.getAttribute('data-mailto') || CBN_EMAIL;
      var subject = form.getAttribute('data-subject') || 'Message from the CBN website';
      var lines = [];
      var nameVal = '';

      form.querySelectorAll('input, select, textarea').forEach(function (el) {
        if (!el.name || el.name === 'website') return;                 // honeypot / unnamed
        if (el.type === 'checkbox' && !el.checked) return;
        var val = el.type === 'checkbox' ? 'yes' : (el.value || '').trim();
        if (!val) return;
        if (!nameVal && /^(name|first|first_name)$/.test(el.name)) nameVal = val;
        lines.push(labelFor(form, el) + ': ' + val);
      });
      subject = subject.replace('{name}', nameVal);
      lines.push('', '— sent from the CBN website');

      var href = 'mailto:' + to + '?subject=' + encodeURIComponent(subject) +
                 '&body=' + encodeURIComponent(lines.join('\n'));
      window.location.href = href;

      var msg = form.querySelector('.form-msg');
      if (msg) {
        msg.innerHTML = '✓ Your email app should now open with your message ready to send. ' +
                        'If nothing happened, email us directly at <a href="mailto:' + to + '">' + to + '</a>.';
        msg.classList.add('show');
      }
    });
  });

  /* contact.html?subject=…  → pre-fill the subject box (used by "Request the full report" links) */
  var qs = new URLSearchParams(window.location.search);
  var subj = qs.get('subject');
  var subjField = document.getElementById('c-subject');
  if (subj && subjField && !subjField.value) subjField.value = subj;
})();
