document.addEventListener('DOMContentLoaded', function () {
  'use strict';

  var API_BASE_URL = window.INVESTIQ_API_BASE || 'http://127.0.0.1:5000';

  var form = document.getElementById('settingsForm');
  if (!form) return;

  var saveBtn = form.querySelector('[data-action="save-settings"]');
  var resetBtn = form.querySelector('[data-action="reset-settings"]');
  var newPassword = document.getElementById('newPassword');
  var confirmNewPassword = document.getElementById('confirmNewPassword');
  var currentPassword = document.getElementById('currentPassword');
  var emailField = document.getElementById('settingsEmail');

  // Fields with no backend column (username, theme, notification
  // toggles, etc.) -- these are stored in localStorage only, same as
  // before, and never claimed to be synced to the server. See
  // settings.html's "Local only" label next to username.
  var LOCAL_STORAGE_KEY = 'investiq_local_settings';
  var localOnlyFields = Array.prototype.slice.call(
    form.querySelectorAll('[data-no-persist]')
  );

  var trackedFields = Array.prototype.slice.call(
    form.querySelectorAll('input[name], select[name], textarea[name]')
  );

  var defaultState = {};
  var hasUnsavedChanges = false;

  function fetchJson(url, options) {
    return fetch(API_BASE_URL + url, Object.assign({ credentials: 'include' }, options))
      .then(function (response) {
        return response.json().then(function (data) {
          return { ok: response.ok, data: data };
        });
      });
  }

  function fieldValue(field) {
    if (field.type === 'checkbox' || field.type === 'radio') {
      return field.checked;
    }
    return field.value;
  }

  function snapshotDefaults() {
    defaultState = {};
    trackedFields.forEach(function (field) {
      var key = field.name + (field.type === 'radio' ? ':' + field.value : '');
      defaultState[key] = fieldValue(field);
    });
  }

  function applyField(field, value) {
    if (field.type === 'checkbox' || field.type === 'radio') {
      field.checked = value;
    } else {
      field.value = value;
    }
  }

  function markDirty() {
    hasUnsavedChanges = true;
  }

  function trackChanges() {
    trackedFields.forEach(function (field) {
      var evt = field.tagName === 'SELECT' || field.type === 'checkbox' || field.type === 'radio' ? 'change' : 'input';
      field.addEventListener(evt, markDirty);
    });
  }

  /* ------------------------------------------------------------------
     LOAD REAL EMAIL + LOCAL-ONLY FIELDS
     ------------------------------------------------------------------ */
  function loadRealAccountFields() {
    fetchJson('/api/auth/me', { method: 'GET' }).then(function (result) {
      if (result.ok && result.data.user && emailField) {
        emailField.value = result.data.user.email || '';
      }
      snapshotDefaults();
    });

    try {
      var saved = JSON.parse(localStorage.getItem(LOCAL_STORAGE_KEY) || '{}');
      localOnlyFields.forEach(function (field) {
        if (saved.hasOwnProperty(field.name)) {
          applyField(field, saved[field.name]);
        }
      });
    } catch (e) {
      // Corrupt/old localStorage value -- ignore and keep defaults.
    }
  }

  function saveLocalOnlyFields() {
    var data = {};
    localOnlyFields.forEach(function (field) {
      data[field.name] = fieldValue(field);
    });
    localStorage.setItem(LOCAL_STORAGE_KEY, JSON.stringify(data));
  }

  /* ------------------------------------------------------------------
     PASSWORD VISIBILITY TOGGLE
     ------------------------------------------------------------------ */
  function initPasswordToggles() {
    document.querySelectorAll('[data-toggle-password]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var input = document.getElementById(btn.getAttribute('data-toggle-password'));
        if (!input) return;
        var isCurrentlyPassword = input.type === 'password';
        input.type = isCurrentlyPassword ? 'text' : 'password';
        btn.classList.toggle('is-visible', isCurrentlyPassword);
        btn.setAttribute('aria-label', isCurrentlyPassword ? 'Hide password' : 'Show password');
      });
    });
  }

  /* ------------------------------------------------------------------
     VALIDATION
     ------------------------------------------------------------------ */
  function isValidEmail(value) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim());
  }

  function setFieldError(field) {
    field.classList.add('is-invalid');
  }

  function clearFieldError(field) {
    field.classList.remove('is-invalid');
  }

  function validateForm() {
    var isValid = true;

    [emailField, currentPassword, newPassword, confirmNewPassword].forEach(function (field) {
      if (field) clearFieldError(field);
    });

    if (emailField) {
      if (!emailField.value.trim()) {
        setFieldError(emailField);
        isValid = false;
      } else if (!isValidEmail(emailField.value)) {
        setFieldError(emailField);
        isValid = false;
      }
    }

    var wantsPasswordChange =
      (newPassword && newPassword.value) ||
      (confirmNewPassword && confirmNewPassword.value) ||
      (currentPassword && currentPassword.value);

    if (wantsPasswordChange) {
      if (!currentPassword || !currentPassword.value) {
        if (currentPassword) setFieldError(currentPassword);
        isValid = false;
      }
      if (!newPassword || newPassword.value.length < 8) {
        if (newPassword) setFieldError(newPassword);
        isValid = false;
      }
      if (!confirmNewPassword || confirmNewPassword.value !== (newPassword ? newPassword.value : '')) {
        if (confirmNewPassword) setFieldError(confirmNewPassword);
        isValid = false;
      }
    }

    return isValid;
  }

  /* ------------------------------------------------------------------
     SAVE SETTINGS
     Two independent real API calls (email via PUT /api/auth/profile,
     password via PUT /api/auth/password) plus local-only storage for
     everything else -- each part only reports success if it actually
     succeeded, rather than one blanket "Settings saved" regardless of
     what happened.
     ------------------------------------------------------------------ */
  function setButtonLoading(btn, isLoading, busyText) {
    if (!btn) return;
    var label = btn.querySelector('.btn-label');
    if (!label) return;
    if (isLoading) {
      btn.dataset.originalLabel = label.textContent;
      label.textContent = busyText;
      btn.disabled = true;
      btn.style.opacity = '0.75';
    } else {
      label.textContent = btn.dataset.originalLabel || label.textContent;
      btn.disabled = false;
      btn.style.opacity = '';
    }
  }

  form.addEventListener('submit', function (e) {
    e.preventDefault();

    if (!validateForm()) {
      showToast('Please fix the highlighted fields and try again.', 'error');
      return;
    }

    setButtonLoading(saveBtn, true, 'Saving...');

    var wantsPasswordChange = currentPassword && currentPassword.value;
    var tasks = [];
    var errors = [];

    if (emailField) {
      tasks.push(
        fetchJson('/api/auth/profile', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email: emailField.value.trim() })
        }).then(function (result) {
          if (!result.ok) errors.push(result.data.message || 'Could not update email.');
        })
      );
    }

    if (wantsPasswordChange) {
      tasks.push(
        fetchJson('/api/auth/password', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            current_password: currentPassword.value,
            new_password: newPassword.value
          })
        }).then(function (result) {
          if (!result.ok) errors.push(result.data.message || 'Could not change password.');
        })
      );
    }

    Promise.all(tasks)
      .then(function () {
        saveLocalOnlyFields();
        setButtonLoading(saveBtn, false);
        hasUnsavedChanges = false;
        snapshotDefaults();

        if (currentPassword) currentPassword.value = '';
        if (newPassword) newPassword.value = '';
        if (confirmNewPassword) confirmNewPassword.value = '';

        if (errors.length) {
          showToast(errors.join(' '), 'error');
        } else {
          showToast('Settings saved successfully.', 'success');
        }
      })
      .catch(function () {
        setButtonLoading(saveBtn, false);
        showToast('Unable to connect to the server. Please make sure the backend is running.', 'error');
      });
  });

  /* ------------------------------------------------------------------
     RESET TO DEFAULT
     ------------------------------------------------------------------ */
  if (resetBtn) {
    resetBtn.addEventListener('click', function () {
      var confirmed = window.confirm('Reset all settings to their default values? Unsaved changes will be lost.');
      if (!confirmed) return;

      trackedFields.forEach(function (field) {
        var key = field.name + (field.type === 'radio' ? ':' + field.value : '');
        if (defaultState.hasOwnProperty(key)) {
          applyField(field, defaultState[key]);
        }
        clearFieldError(field);
      });

      if (currentPassword) currentPassword.value = '';
      if (newPassword) newPassword.value = '';
      if (confirmNewPassword) confirmNewPassword.value = '';

      hasUnsavedChanges = false;
      showToast('Settings reset to default.', 'success');
    });
  }

  /* ------------------------------------------------------------------
     UNSAVED CHANGES WARNING
     ------------------------------------------------------------------ */
  window.addEventListener('beforeunload', function (e) {
    if (hasUnsavedChanges) {
      e.preventDefault();
      e.returnValue = '';
      return '';
    }
  });

  /* ------------------------------------------------------------------
     TOAST
     ------------------------------------------------------------------ */
  function showToast(message, type) {
    var existing = document.getElementById('settingsToast');
    if (existing) existing.remove();

    var toast = document.createElement('div');
    toast.id = 'settingsToast';
    toast.setAttribute('role', 'status');
    toast.textContent = message;

    toast.style.position = 'fixed';
    toast.style.bottom = '24px';
    toast.style.left = '50%';
    toast.style.transform = 'translate(-50%, 12px)';
    toast.style.zIndex = '999';
    toast.style.padding = '12px 20px';
    toast.style.borderRadius = 'var(--radius-sm)';
    toast.style.fontFamily = 'var(--font-body)';
    toast.style.fontSize = 'var(--fs-sm)';
    toast.style.fontWeight = 'var(--fw-medium)';
    toast.style.boxShadow = 'var(--shadow-lg)';
    toast.style.opacity = '0';
    toast.style.transition = 'opacity 0.25s ease, transform 0.25s ease';

    if (type === 'error') {
      toast.style.background = 'var(--color-danger-bg)';
      toast.style.color = '#991b1b';
    } else {
      toast.style.background = 'var(--color-success-bg)';
      toast.style.color = '#166534';
    }

    document.body.appendChild(toast);

    requestAnimationFrame(function () {
      toast.style.opacity = '1';
      toast.style.transform = 'translate(-50%, 0)';
    });

    setTimeout(function () {
      toast.style.opacity = '0';
      toast.style.transform = 'translate(-50%, 12px)';
      setTimeout(function () {
        toast.remove();
      }, 250);
    }, 2600);
  }

  /* ------------------------------------------------------------------
     DANGER ZONE
     "Deactivate Account" now just signs the user out for real (calls
     the real logout endpoint) -- see settings.html, which relabels the
     button "Sign Out" and states plainly that true deactivation isn't
     available yet, rather than claiming the account was disabled.
     "Log Out Other Sessions" is disabled in the HTML (no multi-session
     tracking exists in the backend's plain Flask-session model), so
     there's no handler for it here.
     ------------------------------------------------------------------ */
  function initDangerZone() {
    var deactivateBtn = form.querySelector('[data-action="deactivate-account"]');

    if (deactivateBtn) {
      deactivateBtn.addEventListener('click', function () {
        var confirmed = window.confirm(
          'This will sign you out of InvestIQ on this device. Continue?'
        );
        if (!confirmed) return;

        fetchJson('/api/auth/logout', { method: 'POST' }).finally(function () {
          localStorage.removeItem('investiq_auth');
          localStorage.removeItem('investiq_user');
          window.location.href = 'index.html';
        });
      });
    }
  }

  initPasswordToggles();
  loadRealAccountFields();
  trackChanges();
  initDangerZone();
});
