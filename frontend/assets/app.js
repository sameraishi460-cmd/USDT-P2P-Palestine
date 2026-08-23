/**
 * USDT P2P Palestine — Shared frontend JS client.
 * API calls, auth session, CSRF, toast, form helpers.
 */
const API_BASE = window.API_BASE || location.origin + '/api';

let CSRF = localStorage.getItem('csrf_token') || '';
const USER_KEY = 'user_data';

function getUser() { try { return JSON.parse(localStorage.getItem(USER_KEY)); } catch { return null; } }
function setUser(u) { localStorage.setItem(USER_KEY, JSON.stringify(u)); }
function clearAuth() { localStorage.removeItem(USER_KEY); localStorage.removeItem('csrf_token'); CSRF = ''; }
function setCsrf(t) { CSRF = t; localStorage.setItem('csrf_token', t); }

// Auth-gated navigation — if no session, redirect
function requireAuth(page) {
  if (!getUser()) { location.href = '/login.html?returnTo=' + encodeURIComponent(page); return false; }
  return true;
}

// ─── Toast ────────────────────────────────────────────────────
let toastTimer;
function toast(msg, ms = 3000) {
  let el = document.getElementById('toast');
  if (!el) { el = document.createElement('div'); el.id = 'toast'; document.body.appendChild(el); }
  clearTimeout(toastTimer);
  el.textContent = msg; el.classList.add('show');
  toastTimer = setTimeout(() => el.classList.remove('show'), ms);
}

// ─── API helper ───────────────────────────────────────────────
async function api(path, opts = {}) {
  const url = API_BASE + path;
  const headers = opts.headers || {};
  if (opts.body && !(opts.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(opts.body);
  } else if (opts.body instanceof FormData) {
    // Don't set Content-Type — browser sets boundary
  }
  if (CSRF && ['POST', 'PUT', 'DELETE'].includes(opts.method || 'GET')) {
    headers['X-CSRF-Token'] = CSRF;
  }
  try {
    const res = await fetch(url, { credentials: 'same-origin', ...opts, headers });
    const json = await res.json().catch(() => ({}));
    if (res.status === 401) { clearAuth(); location.href = '/login.html'; return null; }
    return json;
  } catch (e) {
    toast('خطأ في الاتصال بالخادم');
    return null;
  }
}

function get(path) { return api(path); }
function post(path, body) { return api(path, { method: 'POST', body }); }
function postForm(path, form) { return api(path, { method: 'POST', body: form }); }

// ─── Render helpers ──────────────────────────────────────────
function $(sel) { return document.querySelector(sel); }
function $$(sel) { return document.querySelectorAll(sel); }

function statusBadge(s) {
  const labels = {
    PENDING: '⏳ بانتظار', PAYMENT_SENT: '💳 تم الدفع', CONFIRMING: '🔄 تأكيد',
    COMPLETED: '✅ مكتمل', CANCELLED: '❌ ملغي', DISPUTED: '⚠️ نزاع',
    OPEN: '🟢 مفتوح', ACTIVE: '🟢 نشط', BANNED: '🔴 محظور',
    RELEASED: '🔓 محرر', REFUNDED: '↩️ مرجّع', PROCESSING: '⏳ معالجة',
    PENDING_VERIFICATION: '⏳ بانتظار التحقق',
  };
  return `<span class="badge badge-${s}">${labels[s] || s}</span>`;
}

function profileAvatar(name) {
  return `<div class="avatar">${(name || '?')[0].toUpperCase()}</div>`;
}

function escHtml(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

function copyText(text) {
  navigator.clipboard.writeText(text).then(() => toast('تم النسخ ✅')).catch(() => {});
}

// ─── Active bottom-nav highlight ──────────────────────────────
function highlightNav(id) {
  document.querySelectorAll('.bottom-nav a').forEach(a => a.classList.toggle('active', a.id === id));
}

// ─── Market price fetcher ─────────────────────────────────────
let cachedPrice = null;
async function getMarketPrice() {
  if (cachedPrice && Date.now() - cachedPrice._ts < 60000) return cachedPrice;
  const r = await get('/market/price');
  if (r?.ok) { cachedPrice = { ...r.price, _ts: Date.now() }; return cachedPrice; }
  return null;
}
