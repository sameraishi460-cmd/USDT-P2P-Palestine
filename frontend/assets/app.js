/* ============================================================
   USDT P2P Palestine — Shared JavaScript
   ============================================================ */
const API_BASE = window.API_BASE || location.origin + '/api';
let CSRF = localStorage.getItem('csrf_token') || '';
const USER_KEY = 'usdt_user';

function getUser() { try { return JSON.parse(localStorage.getItem(USER_KEY)); } catch { return null; } }
function setUser(u) { localStorage.setItem(USER_KEY, JSON.stringify(u)); }
function clearAuth() { localStorage.removeItem(USER_KEY); localStorage.removeItem('csrf_token'); CSRF = ''; }
function setCsrf(t) { CSRF = t; localStorage.setItem('csrf_token', t); }

function requireAuth(redirect) {
  if (!getUser()) {
    const rt = encodeURIComponent(location.pathname + location.search);
    location.href = (redirect || '/login') + '?returnTo=' + rt;
    return false;
  }
  return true;
}

let _toastTimer;
function toast(msg, ms) {
  ms = ms || 3000;
  let el = document.getElementById('toast');
  if (!el) { el = document.createElement('div'); el.id = 'toast'; document.body.appendChild(el); }
  clearTimeout(_toastTimer);
  el.textContent = msg; el.classList.add('show');
  _toastTimer = setTimeout(function() { el.classList.remove('show'); }, ms);
}

async function api(path, opts) {
  opts = opts || {};
  const url = API_BASE + path;
  const headers = opts.headers || {};
  if (opts.body && typeof opts.body === 'object' && !(opts.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(opts.body);
  }
  if (CSRF && ['POST', 'PUT', 'DELETE'].indexOf(opts.method || 'GET') >= 0) {
    headers['X-CSRF-Token'] = CSRF;
  }
  try {
    const res = await fetch(url, { credentials: 'same-origin', ...opts, headers });
    const json = await res.json().catch(function() { return {}; });
    if (res.status === 401) { clearAuth(); location.href = '/login'; return null; }
    if (res.status === 429) { toast('تم تجاوز الحد المسموح، حاول لاحقاً'); return null; }
    if (!res.ok && !json.ok) { toast(json.error || 'خطأ في الخادم', 4000); return json; }
    return json;
  } catch (e) {
    if (navigator.onLine === false) toast('لا يوجد اتصال بالإنترنت');
    else toast('خطأ في الاتصال بالخادم');
    return null;
  }
}
function get(path) { return api(path); }
function post(path, body) { return api(path, { method: 'POST', body: body }); }

function $(sel) { return document.querySelector(sel); }
function $$(sel) { return document.querySelectorAll(sel); }
function escHtml(s) { const d = document.createElement('div'); d.textContent = s ?? ''; return d.innerHTML; }
function copyText(text) { navigator.clipboard.writeText(text).then(function() { toast('✅ تم النسخ'); }).catch(function() { toast('فشل النسخ'); }); }

const STATUS_MAP = {
  PENDING: { label: '⏳ بانتظار', cls: 'badge-pending' },
  PAYMENT_SENT: { label: '💳 تم الدفع', cls: 'badge-pending' },
  PAYMENT_CONFIRMED: { label: '✅ تم التأكيد', cls: 'badge-completed' },
  COMPLETED: { label: '✅ مكتمل', cls: 'badge-completed' },
  CANCELLED: { label: '❌ ملغي', cls: 'badge-cancelled' },
  DISPUTED: { label: '⚠️ نزاع', cls: 'badge-disputed' },
  OPEN: { label: '🟢 مفتوح', cls: 'badge-buy' },
  ACTIVE: { label: '🟢 نشط', cls: 'badge-buy' },
  RELEASED: { label: '🔓 محرر', cls: 'badge-completed' },
  REFUNDED: { label: '↩️ مرجّع', cls: 'badge-pending' },
  SELL: { label: '💰 بيع', cls: 'badge-sell' },
  BUY: { label: '🛒 شراء', cls: 'badge-buy' },
};
function statusBadge(s) {
  const info = STATUS_MAP[s] || { label: s, cls: 'badge-pending' };
  return '<span class="badge ' + info.cls + '">' + info.label + '</span>';
}
function typeBadge(t) {
  return t === 'BUY' ? '<span class="badge badge-buy">🛒 شراء</span>' : '<span class="badge badge-sell">💰 بيع</span>';
}
function profileAvatar(name, size) {
  const cls = size === 'lg' ? 'avatar-lg' : size === 'xl' ? 'avatar-xl' : '';
  return '<div class="avatar ' + cls + '">' + ((name || '?')[0] || '?').toUpperCase() + '</div>';
}
function verifiedBadge(v) { return v ? '<span class="badge badge-verified" style="font-size:10px;">✓ موثق</span>' : ''; }
function vipBadge(level) {
  const m = { bronze: '🥉', silver: '🥈', gold: '🥇', verified_trader: '💎' };
  if (!m[level]) return '';
  return '<span class="badge badge-vip" style="font-size:10px;">' + m[level] + ' ' + level + '</span>';
}
function formatDate(d) { return d ? new Date(d).toLocaleString('ar', { dateStyle: 'medium', timeStyle: 'short' }) : ''; }
function formatNum(n, dec) { return Number(n || 0).toFixed(dec || 2); }
function showLoading(el) { el.innerHTML = '<div class="spinner"></div>'; }
function showEmpty(el, icon, msg) { el.innerHTML = '<div class="empty"><div class="icon">' + icon + '</div><p>' + msg + '</p></div>'; }

let _cachedPrice = null;
async function getMarketPrice() {
  if (_cachedPrice && Date.now() - _cachedPrice._ts < 120000) return _cachedPrice;
  const r = await get('/market/price');
  if (r && r.ok) { _cachedPrice = Object.assign({}, r.price, { _ts: Date.now() }); return _cachedPrice; }
  return null;
}

function updateAuthUI() {
  const user = getUser();
  $$('[data-auth]').forEach(function(el) { el.style.display = user ? '' : 'none'; });
  $$('[data-noauth]').forEach(function(el) { el.style.display = user ? 'none' : ''; });
}

function buildNav(activeId) {
  const user = getUser();
  const nav = '<div class="bottom-nav">' +
    '<a href="/"><span class="icon">🏠</span>الرئيسية</a>' +
    '<a href="/market"><span class="icon">🛒</span>السوق</a>' +
    '<a href="/trades"><span class="icon">📄</span>الصفقات</a>' +
    '<a href="/wallet"><span class="icon">💰</span>المحفظة</a>' +
    '<a href="/profile"><span class="icon">👤</span>حسابي</a>' +
    '</div>';
  const el = document.getElementById('bottomNav');
  if (el) el.innerHTML = nav;
  $$('.bottom-nav a').forEach(function(a) {
    a.classList.toggle('active', a.getAttribute('href') === activeId);
  });
}

/* --- Compatibility aliases for new pages --- */
var API = {
  get: function(path) { return api(path); },
  post: function(path, body) { return api(path, { method: 'POST', body: body }); },
  put: function(path, body) { return api(path, { method: 'PUT', body: body }); },
  del: function(path, body) { return api(path, { method: 'DELETE', body: body }); }
};
var Auth = {
  isLoggedIn: function() { return !!getUser(); },
  user: function() { return getUser(); },
  logout: function() { clearAuth(); },
  token: function() { return localStorage.getItem('session_token') || ''; }
};
var fmtNum = function(n, d) { return formatNum(n, d); };
var fmtDate = function(d) { return formatDate(d); };
var escapeHtml = function(s) { return escHtml(s); };
toast.show = function(msg, type, ms) { toast((type === 'error' ? '❌ ' : type === 'success' ? '✅ ' : '') + msg, ms || 3000); };

/* --- Render nav if container exists --- */
(function() {
  var navEl = document.getElementById('nav');
  if (!navEl) return;
  var user = getUser();
  navEl.innerHTML = '<div class="nav-inner container">' +
    '<a href="/" class="nav-logo">USDT<span style="color:var(--primary)">P2P</span></a>' +
    '<div class="nav-links">' +
    '<a href="/market">السوق</a>' +
    (user ? '<a href="/trades">الصفقات</a><a href="/wallet">المحفظة</a><a href="/notifications">الإشعارات</a><a href="/profile">حسابي</a>' : '<a href="/login">تسجيل الدخول</a>') +
    '</div></div>';
  var bn = document.getElementById('bottomNav');
  if (bn && user) {
    var path = location.pathname;
    bn.innerHTML = '<a href="/market" class="' + (path === '/market' ? 'active' : '') + '"><span class="icon">🛒</span>السوق</a>' +
      '<a href="/trades" class="' + (path === '/trades' ? 'active' : '') + '"><span class="icon">📄</span>الصفقات</a>' +
      '<a href="/wallet" class="' + (path === '/wallet' ? 'active' : '') + '"><span class="icon">💰</span>المحفظة</a>' +
      '<a href="/profile" class="' + (path === '/profile' ? 'active' : '') + '"><span class="icon">👤</span>حسابي</a>';
  }
})();
