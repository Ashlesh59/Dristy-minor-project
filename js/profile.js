document.addEventListener('DOMContentLoaded', function () {
'use strict';

var API_BASE_URL = window.INVESTIQ_API_BASE || 'http://127.0.0.1:5000';

var form = document.getElementById('profileForm');
var editBtn = document.getElementById('editProfileBtn');
var cancelBtn = document.getElementById('cancelProfileBtn');
var actions = document.getElementById('profileFormActions');

if (!form || !editBtn) return;

// Bio has no backing column on the User model (see models/user.py) --
// it stays out of both the editable set and the save payload rather
// than pretending to persist it. See profile.html's "Not saved yet"
// label next to it.
var editableFields = Array.prototype.slice.call(form.querySelectorAll('.form-input:not([data-no-persist])'));

// Maps each field's HTML `name` to the JSON key PUT /api/auth/profile
// expects (see backend/routes/auth.py's update_profile()).
var FIELD_TO_API_KEY = {
  fullName: 'name',
  email: 'email',
  company: 'company',
  jobRole: 'job_role',
  phone: 'phone',
  country: 'country',
  timeZone: 'timezone'
};

var originalValues = {};
var isEditing = false;
var hasUnsavedChanges = false;
var currentUser = null;

function fetchJson(url, options) {
  return fetch(API_BASE_URL + url, Object.assign({ credentials: 'include' }, options))
    .then(function (response) {
      return response.json().then(function (data) {
        return { ok: response.ok, data: data };
      });
    });
}

function snapshotValues() {
  originalValues = {};
  editableFields.forEach(function (field) {
    originalValues[field.name] = field.value;
  });
}

function restoreValues() {
  editableFields.forEach(function (field) {
    if (originalValues.hasOwnProperty(field.name)) {
      field.value = originalValues[field.name];
    }
    clearFieldError(field);
  });
}

function setFieldsEditable(editable) {
  editableFields.forEach(function (field) {
    if (field.tagName === 'SELECT') {
      field.disabled = !editable;
    } else {
      if (editable) {
        field.removeAttribute('readonly');
      } else {
        field.setAttribute('readonly', '');
      }
    }
  });
}

function setFieldError(field) {
  field.classList.add('is-invalid');
}

function clearFieldError(field) {
  field.classList.remove('is-invalid');
}

function isValidEmail(value) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim());
}

function validateForm() {
  var isValid = true;

  editableFields.forEach(function (field) {
    clearFieldError(field);
    var value = field.value.trim();

    // Only name and email are actually required by the backend --
    // company/job role/phone/country/timezone are optional profile
    // fields, so an empty one there isn't an error.
    var required = field.name === 'fullName' || field.name === 'email';

    if (required && !value) {
      setFieldError(field);
      isValid = false;
      return;
    }

    if (field.type === 'email' && value && !isValidEmail(value)) {
      setFieldError(field);
      isValid = false;
    }
  });

  return isValid;
}

/* ------------------------------------------------------------------
   LOAD REAL PROFILE
   ------------------------------------------------------------------ */
function applyUserToForm(user) {
  currentUser = user;
  var nameField = form.querySelector('[name="fullName"]');
  if (nameField) nameField.value = user.name || '';
  var emailField = form.querySelector('[name="email"]');
  if (emailField) emailField.value = user.email || '';
  var companyField = form.querySelector('[name="company"]');
  if (companyField) companyField.value = user.company || '';
  var jobRoleField = form.querySelector('[name="jobRole"]');
  if (jobRoleField) jobRoleField.value = user.job_role || '';
  var phoneField = form.querySelector('[name="phone"]');
  if (phoneField) phoneField.value = user.phone || '';
  var countryField = form.querySelector('[name="country"]');
  if (countryField && user.country) countryField.value = user.country;
  var timeZoneField = form.querySelector('[name="timeZone"]');
  if (timeZoneField && user.timezone) timeZoneField.value = user.timezone;

  var headerName = document.querySelector('.profile-header__name');
  if (headerName) headerName.textContent = user.name || '';
  var headerRole = document.querySelector('.profile-header__role');
  if (headerRole) headerRole.textContent = (user.job_role || 'InvestIQ user') + (user.company ? ' · ' + user.company : '');
  var avatarInitials = document.querySelector('.profile-avatar__initials');
  if (avatarInitials && user.name) {
    var parts = user.name.trim().split(/\s+/);
    avatarInitials.textContent = ((parts[0][0] || '') + (parts.length > 1 ? parts[parts.length - 1][0] : '')).toUpperCase();
  }

  snapshotValues();
}

function loadProfile() {
  fetchJson('/api/auth/me', { method: 'GET' }).then(function (result) {
    if (result.ok && result.data.user) {
      applyUserToForm(result.data.user);
    }
  });
}

function enterEditMode() {
  isEditing = true;
  hasUnsavedChanges = false;
  snapshotValues();
  setFieldsEditable(true);
  form.classList.add('is-editing');
  if (actions) actions.hidden = false;
  editBtn.hidden = true;

  var firstField = form.querySelector('.form-input:not([disabled])');
  if (firstField) firstField.focus();

  trackChanges();
}

function exitEditMode() {
  isEditing = false;
  hasUnsavedChanges = false;
  setFieldsEditable(false);
  form.classList.remove('is-editing');
  if (actions) actions.hidden = true;
  editBtn.hidden = false;
}

function trackChanges() {
  editableFields.forEach(function (field) {
    field.addEventListener('input', function () {
      if (!isEditing) return;
      hasUnsavedChanges = field.value !== originalValues[field.name];
    });
    field.addEventListener('change', function () {
      if (!isEditing) return;
      hasUnsavedChanges = field.value !== originalValues[field.name];
    });
  });
}

editBtn.addEventListener('click', function () {
  enterEditMode();
});

if (cancelBtn) {
  cancelBtn.addEventListener('click', function () {
    if (hasUnsavedChanges) {
      var confirmed = window.confirm('You have unsaved changes. Discard them?');
      if (!confirmed) return;
    }
    restoreValues();
    exitEditMode();
  });
}

form.addEventListener('submit', function (e) {
  e.preventDefault();

  if (!validateForm()) {
    showToast('Please fill in all required fields correctly.', 'error');
    return;
  }

  var saveBtn = form.querySelector('[data-action="save-profile"]');
  var label = saveBtn ? saveBtn.querySelector('.btn-label') : null;
  var originalLabel = label ? label.textContent : '';

  if (saveBtn) saveBtn.disabled = true;
  if (label) label.textContent = 'Saving...';

  var payload = {};
  editableFields.forEach(function (field) {
    var apiKey = FIELD_TO_API_KEY[field.name];
    if (apiKey) payload[apiKey] = field.value.trim();
  });

  fetchJson('/api/auth/profile', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  }).then(function (result) {
    if (label) label.textContent = originalLabel;
    if (saveBtn) saveBtn.disabled = false;

    if (!result.ok) {
      showToast(result.data.message || 'Could not save your profile. Please try again.', 'error');
      return;
    }

    applyUserToForm(result.data.user);
    exitEditMode();
    showToast('Profile updated successfully.', 'success');
  }).catch(function () {
    if (label) label.textContent = originalLabel;
    if (saveBtn) saveBtn.disabled = false;
    showToast('Unable to connect to the server. Please make sure the backend is running.', 'error');
  });
});

window.addEventListener('beforeunload', function (e) {
  if (isEditing && hasUnsavedChanges) {
    e.preventDefault();
    e.returnValue = '';
    return '';
  }
});

function showToast(message, type) {
  var existing = document.getElementById('profileToast');
  if (existing) existing.remove();

  var toast = document.createElement('div');
  toast.id = 'profileToast';
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

setFieldsEditable(false);
if (actions) actions.hidden = true;
loadProfile();
});
