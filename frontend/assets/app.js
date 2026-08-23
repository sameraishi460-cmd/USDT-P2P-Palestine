/**
 * USDT P2P Palestine — Enhanced Frontend Client
 * API calls, auth, CSRF, pagination, toast, loading states.
 */
const API_BASE = window.API_BASE || location.origin + '/api';

let CSRF = localStorage.getItem('csrf_token') || '';
const USER_KEY = 'user_data';

/* ─── Auth ───────────────────────────────────────────────── */
function getUser() { try { return JSON.parse(localStorage.getItem(USER_KEY)); } catch { return null; } }
function setUser(u) { localStorage.setItem(USER_KEY, JSON.stringify(u)); }
function clearAuth() { localStorage.removeItem(USER_KEY); localStorage.removeItem('csrf_token'); CSRF = ''; }
function setCsrf(t) { CSRF = t; localStorage.setItem('csrf_token', t); }
function requireAuth(redirectTo) {
  if (!getUser()) { location.href = (redirectTo || '/login.html') + '?returnTo=' + encodeURIComponent(location.pathname + location.search); return false; }
  return true;
}

/* ─── Toast ──────────────────────────────────────────────── */
let _toastTimer;
function toast(msg, ms = 3000) {
  let el = document.getElementById('toast');
  if (!el) { el = document.createElement('div'); el.id = 'toast'; document.body.appendChild(el); }
  clearTimeout(_toastTimer);
  el.textContent = msg; el.classList.add('show');
  _toastTimer = setTimeout(() => el.classList.remove('show'), ms);
}

/* ─── API ────────────────────────────────────────────────── */
async function api(path, opts = {}) {
  const url = API_BASE + path;
  const headers = opts.headers || {};
  if (opts.body && !(opts.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(opts.body);
  }
  if (CSRF && ['POST', 'PUT', 'DELETE'].includes(opts.method || 'GET')) {
    headers['X-CSRF-Token'] = CSRF;
  }
  try {
    const res = await fetch(url, { credentials: 'same-origin', ...opts, headers });
    const json = await res.json().catch(() => ({}));
    if (res.status === 401) { clearAuth(); location.href = '/login.html'; return null; }
    if (res.status === 429) { toast('تم تجاوز الحد المسموح، حاول لاحقاً'); return null; }
    if (!res.ok && !json.ok) { toast(json.error || 'خطأ في الخادم', 4000); return json; }
    return json;
  } catch (e) {
    if (navigator.onLine === false) { toast('لا يوجد اتصال بالإنترنت'); }
    else { toast('خطأ في الاتصال بالخادم'); }
    return null;
  }
}
function get(path) { return api(path); }
function post(path, body) { return api(path, { method: 'POST', body }); }

/* ─── DOM Helpers ────────────────────────────────────────── */
function $(sel) { return document.querySelector(sel); }
function $$(sel) { return document.querySelectorAll(sel); }

function escHtml(s) { const d = document.createElement('div'); d.textContent = s ?? ''; return d.innerHTML; }
function copyText(text) { navigator.clipboard.writeText(text).then(() => toast('✅ تم النسخ')).catch(() => toast('فشل النسخ')); }

/* ─── UI Helpers ─────────────────────────────────────────── */
const STATUS_LABELS = {
  PENDING: '⏳ بانتظار', PAYMENT_SENT: '💳 تم الدفع', CONFIRMING: '🔄 جاري التأكيد',
  COMPLETED: '✅ مكتمل', CANCELLED: '❌ ملغي', DISPUTED: '⚠️ نزاع',
  OPEN: '🟢 مفتوح', ACTIVE: '🟢 نشط', BANNED: '🔴 محظور',
  RELEASED: '🔓 محرر', REFUNDED: '↩️ مرجّع', PROCESSING: '⏳ معالجة',
  PENDING_VERIFICATION: '⏳ بانتظار التحقق', SELL: '💰 بيع', BUY: '🛒 شراء',
};
function statusBadge(s) { return `<span class="badge badge-${s}">${STATUS_LABELS[s] || s}</span>`; }
function profileAvatar(name, large) {
  const cls = large ? 'avatar-lg' : '';
  return `<div class="avatar ${cls}">${((name || '?')[0] || '?').toUpperCase()}</div>`;
}
function verifiedBadge(v) { return v ? '<span class="badge badge-verified" style="font-size:10px;">✓ موثق</span>' : ''; }
function formatDate(d) { return d ? new Date(d).toLocaleString('ar', { dateStyle: 'medium', timeStyle: 'short' }) : ''; }
function formatNum(n, dec = 2) { return Number(n || 0).toFixed(dec); }
function showLoading(el) { el.innerHTML = '<div style="text-align:center;padding:30px;"><div class="spinner"></div></div>'; }
function showEmpty(el, icon, msg) { el.innerHTML = `<div class="empty"><div class="icon">${icon}</div><p>${msg}</p></div>`; }

/* ─── Pagination ─────────────────────────────────────────── */
function loadMoreBtn(container, onLoadMore) {
  const btn = document.createElement('button');
  btn.className = 'btn btn-ghost'; btn.style.marginTop = '10px';
  btn.textContent = 'تحميل المزيد'; btn.onclick = onLoadMore;
  container.appendChild(btn);
  return btn;
}

/* ─── Active Nav ─────────────────────────────────────────── */
function highlightNav(id) {
  document.querySelectorAll('.bottom-nav a').forEach(a => a.classList.toggle('active', a.id === id));
}

/* ─── Market Price Cache ─────────────────────────────────── */
let _cachedPrice = null;
async function getMarketPrice() {
  if (_cachedPrice && Date.now() - _cachedPrice._ts < 120000) return _cachedPrice;
  const r = await get('/market/price');
  if (r?.ok) { _cachedPrice = { ...r.price, _ts: Date.now() }; return _cachedPrice; }
  return null;
}

/* ─── QR Code (lightweight) ──────────────────────────────── */
function generateQrUrl(text, size = 200) {
  // Use a free QR API — no library needed
  return `https://api.qrserver.com/v1/create-qr-code/?size=${size}x${size}&data=${encodeURIComponent(text)}&color=0a0e18&bgcolor=eef2f7&format=svg`;
}
