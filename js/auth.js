/* ==========================================================================
   AUTH.JS
   --------------------------------------------------------------------------
   Shared behavior for login.html, signup.html, and forgot-password.html.
   This file is loaded on all three pages, but each init function checks
   whether its form actually exists on the current page before doing
   anything (`if (!form) return;`) -- so nothing breaks on pages that
   don't have, say, a signup form.

   IMPORTANT FOR LATER PHASES:
   Right now there is no backend, so "submitting" a form just runs
   validation, shows a loading spinner for a moment, then shows a success
   message -- there's no real account creation or authentication happening
   yet. Every place that will need a real fetch() call to Flask later is
   marked with a "BACKEND HOOK" comment so it's easy to find and swap in.
   ========================================================================== */

(function () {
  'use strict';

  var API_BASE_URL = window.INVESTIQ_API_BASE || 'http://127.0.0.1:5000';

  /* ------------------------------------------------------------------
     VALIDATORS
     Small, composable, reusable across every form on the site.
     ------------------------------------------------------------------ */
  var validators = {
    required: function (value) {
      return value.trim().length > 0;
    },
    email: function (value) {
      // Good-enough email pattern for client-side UX validation.
      // Real, authoritative validation always happens server-side too.
      return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim());
    },
    minLength: function (value, length) {
      return value.length >= length;
    }
  };

  /**
   * Marks a field as invalid: adds the red border, sets aria-invalid
   * for screen readers, and reveals the matching .field-error text.
   */
  function setFieldError(input, message) {
    var group = input.closest('.form-group');
    input.classList.add('is-invalid');
    input.setAttribute('aria-invalid', 'true');
    if (group) {
      var errorEl = group.querySelector('.field-error');
      if (errorEl) {
        errorEl.textContent = message;
        errorEl.classList.add('is-visible');
      }
    }
  }

  /** Clears a single field's error state. */
  function clearFieldError(input) {
    var group = input.closest('.form-group');
    input.classList.remove('is-invalid');
    input.removeAttribute('aria-invalid');
    if (group) {
      var errorEl = group.querySelector('.field-error');
      if (errorEl) {
        errorEl.textContent = '';
        errorEl.classList.remove('is-visible');
      }
    }
  }

  /**
   * Shows one of the two top-of-form alert banners (success or error)
   * and hides the other. `type` is 'success' or 'error'.
   */
  function showAlert(form, type, message) {
    var parent = form.closest('.auth-card') || form.parentElement || form;
    var success = parent.querySelector('.alert-success');
    var error = parent.querySelector('.alert-error');
    [success, error].forEach(function (el) {
      if (el) el.classList.remove('is-visible');
    });
    var target = type === 'success' ? success : error;
    if (target) {
      var textEl = target.querySelector('.alert__text');
      if (textEl) textEl.textContent = message;
      target.classList.add('is-visible');
    }
  }

  /** Toggles a submit button between its normal and loading state. */
  function setLoading(button, isLoading) {
    button.classList.toggle('is-loading', isLoading);
    button.disabled = isLoading;
  }

  /* ------------------------------------------------------------------
     SESSION (frontend-only, no backend yet)
     Stores a "logged in" flag plus a dummy user profile in localStorage
     so the Dashboard and its sub-pages know a session exists, and so
     the topbar/sidebar have a name/email to show later. auth-guard.js
     reads the same key to decide whether to allow access to the
     Dashboard pages or bounce back to login.

     BACKEND HOOK: once Flask exists, replace this localStorage write
     with the real session/token returned by /api/login or /api/signup.
     ------------------------------------------------------------------ */
  var SESSION_KEY = 'investiq_auth';
  var USER_KEY = 'investiq_user';

  function startSession(user) {
    localStorage.setItem(SESSION_KEY, 'true');
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  }

  /* ------------------------------------------------------------------
     PASSWORD SHOW/HIDE TOGGLE
     Works on any button with a `data-toggle-password="inputId"`
     attribute -- used on login, signup, and confirm-password fields.
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
     PASSWORD STRENGTH METER (signup page)
     Scores 0-4 based on length + character variety, then colors the
     four bars accordingly. Purely a UX nudge, not a security control.
     ------------------------------------------------------------------ */
  function scorePassword(pw) {
    var score = 0;
    if (pw.length >= 8) score++;
    if (/[A-Z]/.test(pw)) score++;
    if (/[0-9]/.test(pw)) score++;
    if (/[^A-Za-z0-9]/.test(pw)) score++;
    return score;
  }

  function updateStrengthMeter(pw) {
    var meter = document.querySelector('.strength-meter');
    if (!meter) return;
    var bars = meter.querySelectorAll('.strength-meter__bar');
    var label = meter.querySelector('.strength-meter__label');
    var score = pw ? scorePassword(pw) : 0;
    var levels = ['', 'Weak', 'Fair', 'Good', 'Strong'];
    var colors = ['', 'var(--color-danger)', 'var(--color-warning)', 'var(--color-primary)', 'var(--color-success)'];

    bars.forEach(function (bar, i) {
      bar.style.background = i < score ? colors[score] : 'var(--color-border)';
    });

    if (label) {
      label.textContent = pw ? levels[score] : '';
      label.style.color = pw ? colors[score] : 'var(--color-text-muted)';
    }
  }

  /* ------------------------------------------------------------------
     LOGIN FORM
     ------------------------------------------------------------------ */
  function initLoginForm() {
    var form = document.getElementById('loginForm');
    if (!form) return;

    var email = form.querySelector('#loginEmail');
    var password = form.querySelector('#loginPassword');
    var submitBtn = form.querySelector('button[type="submit"]');

    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var isValid = true;

      clearFieldError(email);
      clearFieldError(password);

      if (!validators.required(email.value)) {
        setFieldError(email, 'Email is required.');
        isValid = false;
      } else if (!validators.email(email.value)) {
        setFieldError(email, 'Enter a valid email address.');
        isValid = false;
      }

      if (!validators.required(password.value)) {
        setFieldError(password, 'Password is required.');
        isValid = false;
      } else if (!validators.minLength(password.value, 8)) {
        setFieldError(password, 'Password must be at least 8 characters.');
        isValid = false;
      }

      if (!isValid) {
        showAlert(form, 'error', 'Please fix the highlighted fields and try again.');
        return;
      }

      setLoading(submitBtn, true);

fetch(API_BASE_URL + '/api/auth/login', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json'
  },
  credentials: 'include',
  body: JSON.stringify({
    email: email.value.trim(),
    password: password.value
  })
})
  .then(function (response) {
    return response.json().then(function (data) {
      return {
        ok: response.ok,
        data: data
      };
    });
  })
  .then(function (result) {

    setLoading(submitBtn, false);

    if (!result.ok) {
      showAlert(
        form,
        'error',
        result.data.message || 'Login failed. Please try again.'
      );
      return;
    }

    showAlert(
      form,
      'success',
      'Login successful. Redirecting to your dashboard...'
    );

    if (result.data.user) {
      localStorage.setItem(
        USER_KEY,
        JSON.stringify(result.data.user)
      );
      localStorage.setItem(SESSION_KEY, 'true');
    }

    setTimeout(function () {
      window.location.href = 'dashboard.html';
    }, 900);

  })
  .catch(function (err) {
    console.error('Login error:', err);
    setLoading(submitBtn, false);

    showAlert(
      form,
      'error',
      'Unable to connect to the server. Please make sure the backend is running.'
    );

  });
    });
  }

  /* ------------------------------------------------------------------
     SIGNUP FORM
     ------------------------------------------------------------------ */
  function initSignupForm() {
    var form = document.getElementById('signupForm');
    if (!form) return;

    var name = form.querySelector('#signupName');
    var email = form.querySelector('#signupEmail');
    var password = form.querySelector('#signupPassword');
    var confirmPassword = form.querySelector('#signupConfirmPassword');
    var terms = form.querySelector('#signupTerms');
    var submitBtn = form.querySelector('button[type="submit"]');

    if (password) {
      password.addEventListener('input', function () {
        updateStrengthMeter(password.value);
      });
    }

    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var isValid = true;

      [name, email, password, confirmPassword].forEach(clearFieldError);

      if (!validators.required(name.value)) {
        setFieldError(name, 'Full name is required.');
        isValid = false;
      }

      if (!validators.required(email.value)) {
        setFieldError(email, 'Email is required.');
        isValid = false;
      } else if (!validators.email(email.value)) {
        setFieldError(email, 'Enter a valid email address.');
        isValid = false;
      }

      if (!validators.required(password.value)) {
        setFieldError(password, 'Password is required.');
        isValid = false;
      } else if (!validators.minLength(password.value, 8)) {
        setFieldError(password, 'Use at least 8 characters.');
        isValid = false;
      }

      if (!validators.required(confirmPassword.value) || confirmPassword.value !== password.value) {
        setFieldError(confirmPassword, 'Passwords do not match.');
        isValid = false;
      }

      if (!isValid) {
        showAlert(form, 'error', 'Please fix the highlighted fields and try again.');
        return;
      }

      if (terms && !terms.checked) {
        showAlert(form, 'error', 'Please accept the Terms of Service to continue.');
        return;
      }

      setLoading(submitBtn, true);

      fetch(API_BASE_URL + '/api/auth/signup', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        credentials: 'include',
        body: JSON.stringify({
          name: name.value.trim(),
          email: email.value.trim(),
          password: password.value
        })
      })
        .then(function (response) {
          return response.json().then(function (data) {
            return { ok: response.ok, data: data };
          });
        })
        .then(function (result) {
          setLoading(submitBtn, false);

          if (!result.ok) {
            // Covers both validation errors and a duplicate-email 409
            // from the backend -- the message it returns already
            // distinguishes those cases for the user.
            showAlert(
              form,
              'error',
              result.data.message || 'Could not create your account. Please try again.'
            );
            return;
          }

          if (result.data.user) {
            localStorage.setItem(USER_KEY, JSON.stringify(result.data.user));
            localStorage.setItem(SESSION_KEY, 'true');
            showAlert(form, 'success', 'Account created! Redirecting to dashboard...');
            setTimeout(function () {
              window.location.href = 'dashboard.html';
            }, 900);
          } else {
            showAlert(form, 'success', 'Account created! Redirecting to login...');
            setTimeout(function () {
              window.location.href = 'login.html';
            }, 1200);
          }
        })
        .catch(function () {
          setLoading(submitBtn, false);
          showAlert(
            form,
            'error',
            'Unable to connect to the server. Please make sure the backend is running.'
          );
        });
    });
  }

  /* ------------------------------------------------------------------
     FORGOT PASSWORD FORM
     There is no real email/password-reset infrastructure in the
     backend yet (see backend/routes/auth.py) -- the form is disabled
     in the HTML itself (see forget-password.html) so this only exists
     as a defensive no-op in case it's ever re-enabled, and never shows
     a fake "reset email sent" success message.
     ------------------------------------------------------------------ */
  function initForgotForm() {
    var form = document.getElementById('forgotForm');
    if (!form) return;

    form.addEventListener('submit', function (e) {
      e.preventDefault();
      showAlert(form, 'error', 'Password reset isn\'t available yet. Please contact support or try logging in with your existing password.');
    });
  }

  /* ------------------------------------------------------------------
     INIT -- runs once the DOM is ready. Since our <script> tags use
     `defer`, the DOM is already parsed by the time this file runs, but
     we still listen for DOMContentLoaded defensively in case this
     script is ever moved or loaded differently.
     ------------------------------------------------------------------ */
  function init() {
    initPasswordToggles();
    initLoginForm();
    initSignupForm();
    initForgotForm();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();