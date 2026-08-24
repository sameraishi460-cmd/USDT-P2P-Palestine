/* ============================================================
   USDT P2P Palestine — Shared JavaScript (v4)
   Auth: cookie-based sessions + localStorage user cache + CSRF
   Telegram WebApp Integration
   ============================================================ */
const API_BASE = location.origin + '/api';

/* ── Telegram WebApp SDK ──────────────────────────────── */
const tg = window.Telegram?.WebApp || null;
let _isTelegram = !!tg;

function initTelegram() {
  if (!tg) return;
  // Expand to full height
  tg.expand();
  // Close confirmation
  tg.ready();
  // Apply Telegram theme colors
  if (tg.themeParams) {
    document.documentElement.style.setProperty('--tg-bg', tg.themeParams.bg_color || '');
    document.documentElement.style.setProperty('--tg-text', tg.themeParams.text_color || '');
    document.documentElement.style.setProperty('--tg-hint', tg.themeParams.hint_color || '');
    document.documentElement.style.setProperty('--tg-link', tg.themeParams.link_color || '');
    document.documentElement.style.setProperty('--tg-button', tg.themeParams.button_color || '');
    document.documentElement.style.setProperty('--tg-button-text', tg.themeParams.button_text_color || '');
    document.documentElement.style.setProperty('--tg-secondary-bg', tg.themeParams.secondary_bg_color || '');
  }
  // Listen for theme changes
  tg.onEvent('themeChanged', () => {
    if (tg.themeParams) {
      document.documentElement.style.setProperty('--tg-bg', tg.themeParams.bg_color || '');
      document.documentElement.style.setProperty('--tg-text', tg.themeParams.text_color || '');
      document.documentElement.style.setProperty('--tg-button', tg.themeParams.button_color || '');
      document.documentElement.style.setProperty('--tg-button-text', tg.themeParams.button_text_color || '');
      document.documentElement.style.setProperty('--tg-secondary-bg', tg.themeParams.secondary_bg_color || '');
    }
  });
  // Main button (hidden by default, can be shown per page)
  tg.MainButton.hide();
  // BackButton handling
  tg.BackButton.onClick(() => {
    if (window.history.length > 1) window.history.back();
    else tg.close();
  });
  // Set header color
  tg.setHeaderColor('#0a0e18');
  tg.setBackgroundColor('#0a0e18');
}

function isTelegram() { return _isTelegram; }
function tgUser() { return tg?.initDataUnsafe?.user || null; }
function tgInitData() { return tg?.initData || ''; }

// Haptic feedback helpers
function hapticFeedback(type) {
  if (!tg) return;
  if (type === 'success') tg.HapticFeedback.impactOccurred('medium');
  else if (type === 'error') tg.HapticFeedback.notificationOccurred('error');
  else if (type === 'tap') tg.HapticFeedback.impactOccurred('light');
  else tg.HapticFeedback.impactOccurred('medium');
}
const USER_KEY = 'usp_user';
const CSRF_KEY = 'usp_csrf';

let _user = null;
let _csrf = '';

function loadUser() {
  try { _user = JSON.parse(localStorage.getItem(USER_KEY)); } catch { _user = null; }
  _csrf = localStorage.getItem(CSRF_KEY) || '';
}
loadUser();

function saveUser(u, csrf) {
  _user = u; _csrf = csrf || _csrf;
  if (u) localStorage.setItem(USER_KEY, JSON.stringify(u));
  else localStorage.removeItem(USER_KEY);
  if (csrf) localStorage.setItem(CSRF_KEY, csrf);
}
function clearUser() { _user = null; _csrf = ''; localStorage.removeItem(USER_KEY); localStorage.removeItem(CSRF_KEY); }

function isLoggedIn() { return !!_user; }
function currentUser() { return _user; }

/* ── Theme (Dark/Light) ──────────────────────────────── */
const THEME_KEY = 'usp_theme';
function getTheme() { return localStorage.getItem(THEME_KEY) || 'dark'; }
function setTheme(t) {
  localStorage.setItem(THEME_KEY, t);
  applyTheme(t);
}
function applyTheme(t) {
  if (t === 'auto') {
    t = window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
  }
  document.documentElement.setAttribute('data-theme', t);
}
applyTheme(getTheme());
function toggleTheme() {
  const cur = getTheme();
  const next = cur === 'dark' ? 'light' : cur === 'light' ? 'auto' : 'dark';
  setTheme(next);
  toast(next === 'dark' ? '🌙 الوضع الليلي' : next === 'light' ? '☀️ الوضع الفاتح' : '⚙️ تلقائي حسب الجهاز');
}

/* ── Toast ─────────────────────────────────────────────────── */
let _tt;
function toast(msg, ms) {
  ms = ms || 3000;
  let el = document.getElementById('toast');
  if (!el) { el = document.createElement('div'); el.id = 'toast'; document.body.appendChild(el); }
  clearTimeout(_tt);
  el.textContent = msg; el.className = 'toast show';
  _tt = setTimeout(() => el.className = 'toast', ms);
}

/* ── API ───────────────────────────────────────────────────── */
async function api(path, opts) {
  opts = opts || {};
  const url = API_BASE + path;
  const headers = Object.assign({}, opts.headers);
  if (opts.body && typeof opts.body === 'object' && !(opts.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(opts.body);
  }
  // CSRF on mutations
  if (['POST', 'PUT', 'DELETE'].includes(opts.method || 'GET') && _csrf) {
    headers['X-CSRF-Token'] = _csrf;
  }
  try {
    const res = await fetch(url, { credentials: 'same-origin', ...opts, headers });
    const json = await res.json().catch(() => ({}));
    if (res.status === 401 && json.authenticated === false) { clearUser(); return json; }
    if (res.status === 429) { toast('تم تجاوز الحد المسموح، حاول لاحقاً'); return json; }
    if (!res.ok && !json.ok) { toast(json.error || 'خطأ في الخادم', 4000); return json; }
    return json;
  } catch {
    toast(navigator.onLine === false ? 'لا يوجد اتصال بالإنترنت' : 'خطأ في الاتصال');
    return null;
  }
}

/* ── Auth helpers ──────────────────────────────────────────── */
async function doRegister(username, email, password) {
  const r = await api('/auth/register', { method: 'POST', body: { username, email, password } });
  if (r && r.ok) {
    const me = await api('/auth/me');
    if (me && me.authenticated) saveUser(me, r.csrf_token);
    return r;
  }
  return r;
}

async function doLogin(identifier, password) {
  const r = await api('/auth/login', { method: 'POST', body: { username: identifier, password } });
  if (r && r.ok) {
    const me = await api('/auth/me');
    if (me && me.authenticated) saveUser(me, r.csrf_token);
    return r;
  }
  return r;
}

async function doAdminLogin(username, password) {
  const r = await api('/auth/admin-login', { method: 'POST', body: { username, password } });
  if (r && r.ok) {
    const me = await api('/auth/me');
    if (me && me.authenticated) { saveUser(me, r.csrf_token); me.isAdmin = true; }
    return r;
  }
  return r;
}

async function doLogout() {
  await api('/auth/logout', { method: 'POST' });
  clearUser();
  location.href = '/login';
}

function requireAuth() {
  if (!isLoggedIn()) {
    const rt = encodeURIComponent(location.pathname + location.search);
    location.href = '/login?returnTo=' + rt;
    return false;
  }
  return true;
}

/* ── Status helpers ────────────────────────────────────────── */
const STATUS_MAP = {
  OPEN: { label: '🟢 مفتوحة', cls: 'badge-buy' },
  PENDING: { label: '⏳ بانتظار', cls: 'badge-pending' },
  PAYMENT_SENT: { label: '💳 تم الدفع', cls: 'badge-info' },
  PAYMENT_CONFIRMED: { label: '✅ تم التأكيد', cls: 'badge-success' },
  COMPLETED: { label: '✅ مكتمل', cls: 'badge-success' },
  CANCELLED: { label: '❌ ملغي', cls: 'badge-error' },
  DISPUTED: { label: '⚠️ نزاع', cls: 'badge-error' },
  RELEASED: { label: '🔓 محرر', cls: 'badge-success' },
  REFUNDED: { label: '↩️ مرجّع', cls: 'badge-pending' },
  SELL: { label: '💰 بيع', cls: 'badge-sell' },
  BUY: { label: '🛒 شراء', cls: 'badge-buy' },
};
function statusBadge(s) { const i = STATUS_MAP[s] || { label: s, cls: '' }; return `<span class="badge ${i.cls}">${i.label}</span>`; }
function typeBadge(t) { return t === 'BUY' ? '<span class="badge badge-buy">🛒 شراء</span>' : '<span class="badge badge-sell">💰 بيع</span>'; }
function profileAvatar(name, extra) {
  const c = name ? name[0].toUpperCase() : '?';
  return `<div class="avatar" style="width:32px;height:32px;font-size:13px">${c}</div>`;
}
function verifiedBadge(size) {
  return '<span class="badge badge-verified" style="font-size:10px">✓ موثق</span>';
}
function trustBadge(score) {
  if (!score) return '';
  const cls = score >= 80 ? 'trust-high' : score >= 50 ? 'trust-mid' : 'trust-low';
  return `<span class="trust-score ${cls}">🟢 ${score}% موثوق</span>`;
}
function esc(s) { const d = document.createElement('div'); d.textContent = s ?? ''; return d.innerHTML; }
function fmtNum(n, d) { return Number(n || 0).toFixed(d ?? 2); }
function fmtDate(d) { return d ? new Date(d).toLocaleString('ar', { dateStyle: 'medium', timeStyle: 'short' }) : ''; }
function copyText(t) { navigator.clipboard?.writeText(t); toast('تم النسخ'); }

/* ── Navigation ────────────────────────────────────────────── */
function themeIcon() { const t = getTheme(); return t === 'dark' ? '🌙' : t === 'light' ? '☀️' : '⚙️'; }

function renderNav() {
  const nav = document.getElementById('nav');
  if (!nav) return;
  const u = currentUser();
  nav.innerHTML = `<div class="navbar-inner">
    <a href="/" class="navbar-brand">🇵🇸 <span>USDT</span> P2P</a>
    <div class="navbar-links">
      ${u ? `<a href="/market">السوق</a><a href="/trades">الصفقات</a><a href="/wallet">المحفظة</a><a href="/notifications">الإشعارات</a><a href="/profile">حسابي</a>${u.isAdmin ? '<a href="/admin">الإدارة</a>' : ''}` : `<a href="/login" class="btn-nav">دخول</a><a href="/register" class="btn-nav-accent btn-nav">حساب جديد</a>`}
      <button onclick="toggleTheme()" style="background:none;border:none;cursor:pointer;font-size:1.1rem;padding:4px 8px" title="تبديل المظهر">${themeIcon()}</button>
    </div></div>`;
  const bn = document.getElementById('bottomNav');
  if (bn && u) {
    const p = location.pathname;
    bn.innerHTML = `<a href="/market" class="${p==='/market'?'active':''}"><span class="nav-icon">🛒</span><span class="nav-label">السوق</span></a>
      <a href="/trades" class="${p==='/trades'?'active':''}"><span class="nav-icon">📄</span><span class="nav-label">الصفقات</span></a>
      <a href="/wallet" class="${p==='/wallet'?'active':''}"><span class="nav-icon">💰</span><span class="nav-label">المحفظة</span></a>
      <a href="/profile" class="${p==='/profile'?'active':''}"><span class="nav-icon">👤</span><span class="nav-label">حسابي</span></a>`;
  }
}

/* ── Init on load ──────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  initTelegram();
  renderNav();
  // Hide desktop nav when in Telegram (use bottom nav only)
  if (_isTelegram) {
    const nav = document.getElementById('nav');
    if (nav) nav.style.display = 'none';
    document.body.classList.add('tg-webapp');
  }
});
