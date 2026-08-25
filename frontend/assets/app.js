/* ============================================================
   USDT P2P Palestine — Shared JavaScript (v5)
   Auth: cookie-based sessions + localStorage user cache + CSRF
   Telegram WebApp Integration
   ============================================================ */
const API_BASE = location.origin + '/api';

/* ── Telegram Deep-Link Login ──────────────────────────
   When user clicks a bot URL button with ?tg_token=XXX,
   exchange it for a proper web session cookie. */
(function() {
  const params = new URLSearchParams(location.search);
  const tgToken = params.get('tg_token');
  if (!tgToken) return;
  // Remove token from URL immediately (prevent re-use/bookmark)
  params.delete('tg_token');
  const cleanUrl = location.pathname + (params.toString() ? '?' + params.toString() : '') + location.hash;
  history.replaceState(null, '', cleanUrl);
  // Exchange token for a session
  fetch(API_BASE + '/auth/telegram-login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: 'token=' + encodeURIComponent(tgToken),
    credentials: 'include',
  }).then(r => r.json()).then(data => {
    if (data.ok) {
      // Store CSRF token if returned
      if (data.csrf_token) {
        try { localStorage.setItem('csrf_token', data.csrf_token); } catch {}
      }
      // Reload to pick up the new session
      location.reload();
    } else {
      console.warn('[tg-login] Token exchange failed:', data.error);
    }
  }).catch(err => {
    console.error('[tg-login] Network error:', err);
  });
})();

/* ── Telegram WebApp SDK ──────────────────────────────── */
const tg = window.Telegram?.WebApp || null;
let _isTelegram = !!tg;

function initTelegram() {
  if (!tg) return;
  tg.expand();
  tg.ready();
  if (tg.themeParams) {
    document.documentElement.style.setProperty('--tg-bg', tg.themeParams.bg_color || '');
    document.documentElement.style.setProperty('--tg-text', tg.themeParams.text_color || '');
    document.documentElement.style.setProperty('--tg-hint', tg.themeParams.hint_color || '');
    document.documentElement.style.setProperty('--tg-link', tg.themeParams.link_color || '');
    document.documentElement.style.setProperty('--tg-button', tg.themeParams.button_color || '');
    document.documentElement.style.setProperty('--tg-button-text', tg.themeParams.button_text_color || '');
    document.documentElement.style.setProperty('--tg-secondary-bg', tg.themeParams.secondary_bg_color || '');
  }
  tg.onEvent('themeChanged', () => {
    if (tg.themeParams) {
      document.documentElement.style.setProperty('--tg-bg', tg.themeParams.bg_color || '');
      document.documentElement.style.setProperty('--tg-text', tg.themeParams.text_color || '');
      document.documentElement.style.setProperty('--tg-button', tg.themeParams.button_color || '');
      document.documentElement.style.setProperty('--tg-button-text', tg.themeParams.button_text_color || '');
      document.documentElement.style.setProperty('--tg-secondary-bg', tg.themeParams.secondary_bg_color || '');
    }
  });
  tg.MainButton.hide();
  tg.BackButton.onClick(() => {
    if (window.history.length > 1) window.history.back();
    else tg.close();
  });
  tg.setHeaderColor('#0a0e18');
  tg.setBackgroundColor('#0a0e18');
}

function isTelegram() { return _isTelegram; }
function tgUser() { return tg?.initDataUnsafe?.user || null; }
function tgInitData() { return tg?.initData || ''; }

function hapticFeedback(type) {
  if (!tg) return;
  if (type === 'success') tg.HapticFeedback.impactOccurred('medium');
  else if (type === 'error') tg.HapticFeedback.notificationOccurred('error');
  else if (type === 'tap') tg.HapticFeedback.impactOccurred('light');
  else tg.HapticFeedback.impactOccurred('medium');
}

const USER_KEY = 'usp_user';
const CSRF_KEY = 'usp_csrf';
const LOGOUT_KEY = 'usp_logged_out';

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
  // Clear logout flag on successful login
  localStorage.removeItem(LOGOUT_KEY);
}

function clearUser() {
  _user = null; _csrf = '';
  localStorage.removeItem(USER_KEY);
  localStorage.removeItem(CSRF_KEY);
}

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
  // Mark as logged out to prevent Telegram auto-re-login
  localStorage.setItem(LOGOUT_KEY, '1');
  await api('/auth/logout', { method: 'POST' });
  clearUser();
  window.location.href = '/login';
}

function wasLoggedOut() {
  return localStorage.getItem(LOGOUT_KEY) === '1';
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
function themeIcon() { const t = getTheme(); if (t === 'dark') return '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/></svg>'; if (t === 'light') return '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>'; return '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/></svg>'; }

/* Page titles for mobile header */
const PAGE_TITLES = {
  '/': 'الرئيسية',
  '/market': 'سوق USDT',
  '/trades': 'الصفقات',
  '/wallet': 'المحفظة',
  '/profile': 'الملف الشخصي',
  '/create_ad': 'إنشاء إعلان',
  '/notifications': 'الإشعارات',
  '/login': 'دخول',
  '/register': 'حساب جديد',
  '/admin_login': 'دخول الإدارة',
  '/my_ads': 'إعلاناتي',
  '/cash_market': 'سوق الكاش',
  '/disputes': 'النزاعات',
  '/forgot_password': 'نسيت كلمة المرور',
  '/verify_email': 'تحقق من البريد',
};

/* Pages where back button is needed */
const INNER_PAGES = ['/trade', '/trader', '/wallet', '/profile', '/create_ad', '/edit_ad',
  '/notifications', '/my_ads', '/disputes', '/verify_email', '/forgot_password'];

/* Pages with their own full layout (skip mobile header) */
const STANDALONE_PAGES = ['/admin', '/admin_login', '/login', '/register'];

function getPageTitle(p) {
  // Check exact match first
  if (PAGE_TITLES[p]) return PAGE_TITLES[p];
  // Check dynamic pages
  if (p.startsWith('/trade/')) return 'تفاصيل الصفقة';
  if (p.startsWith('/trader/')) return 'البروفايل';
  if (p.startsWith('/edit_ad/')) return 'تعديل الإعلان';
  return 'USDT P2P';
}

function needsBackButton(p) {
  return INNER_PAGES.some(pg => p.startsWith(pg) && p !== pg);
}

function isStandalonePage(p) {
  return STANDALONE_PAGES.some(pg => p.startsWith(pg));
}

function renderNav() {
  const u = currentUser();
  const p = location.pathname;

  // Remove any stale bottom-nav elements from old implementations
  document.querySelectorAll('.bottom-nav, #bottomNav, #bottom-nav, [id="bottom-nav"], .mobile-bottom-nav, #adminBottomNav').forEach(el => el.remove());
  document.body.classList.remove('has-bottom-nav');

  // Skip standalone pages (admin, login, register)
  if (isStandalonePage(p)) return;

  // ── Desktop Top Navbar ──
  const nav = document.getElementById('nav');
  if (nav) {
    nav.innerHTML = `<div class="navbar-inner">
      <a href="/" class="navbar-brand"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align:middle;margin-left:4px;"><path d="M3 21V3h18v18H3zM7 11h4m-2-2v4m6-4h4m-2-2v4"/></svg> <span>USDT</span> P2P</a>
      <div class="navbar-links">
        ${u ? `
          <a href="/market">السوق</a>
          <a href="/trades">الصفقات</a>
          <a href="/wallet">المحفظة</a>
          <a href="/create_ad">إنشاء إعلان</a>
          <a href="/notifications">الإشعارات</a>
          <a href="/profile">حسابي</a>
          ${u.isAdmin ? '<a href="/admin">⚙️ الإدارة</a>' : ''}
        ` : `
          <a href="/login" class="btn-nav">دخول</a>
          <a href="/register" class="btn-nav-accent btn-nav">حساب جديد</a>
        `}
        <button onclick="toggleTheme()" style="background:none;border:none;cursor:pointer;font-size:1.1rem;padding:4px 8px" title="تبديل المظهر">${themeIcon()}</button>
      </div>
    </div>`;
  }

  // ── Mobile Header + Sidebar (only on mobile, non-standalone pages) ──
  buildMobileShell(u, p);
}

/* ── Mobile Sidebar Drawer ────────────────────────────────── */
function buildMobileShell(u, p) {
  // Prevent duplicate creation
  if (document.querySelector('.mobile-header')) return;

  const title = getPageTitle(p);
  const showBack = needsBackButton(p);

  // ── Mobile Header ──
  const header = document.createElement('header');
  header.className = 'mobile-header';
  const menuSvg = '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 6h16M4 12h16M4 18h16"/></svg>';
  const backSvg = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 19l-7-7 7-7"/></svg>';
  header.innerHTML = `<div class="mobile-header-left">
      ${showBack ? '<button class="mobile-header-back" onclick="history.back()" aria-label="رجوع">' + backSvg + '</button>' : ''}
      <span class="mobile-header-title">${title}</span>
    </div>
    <button class="mobile-header-menu" onclick="toggleMobileSidebar()" aria-label="فتح القائمة" aria-expanded="false">${menuSvg}</button>`;
  document.body.prepend(header);

  // ── Sidebar Overlay ──
  const overlay = document.createElement('div');
  overlay.className = 'mobile-sidebar-overlay';
  overlay.onclick = closeMobileSidebar;
  document.body.appendChild(overlay);

  // ── Sidebar Panel ──
  const panel = document.createElement('aside');
  panel.className = 'mobile-sidebar-panel';
  panel.setAttribute('role', 'navigation');
  panel.setAttribute('aria-label', 'قائمة التنقل');

  // SVG icon helper
  const svgIcon = (d, size = 20) => `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="${d}"/></svg>`;
  const I = {
    home: svgIcon('M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-4 0h4'),
    market: svgIcon('M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8V6m0 8v2m6-6a6 6 0 11-12 0 6 6 0 0112 0z'),
    trades: svgIcon('M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2'),
    wallet: svgIcon('M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z'),
    ads: svgIcon('M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10'),
    plus: svgIcon('M12 4v16m8-8H4'),
    bell: svgIcon('M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9'),
    user: svgIcon('M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z'),
    admin: svgIcon('M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065zM15 12a3 3 0 11-6 0 3 3 0 016 0z'),
    logout: svgIcon('M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1'),
    login: svgIcon('M11 16l-4-4m0 0l4-4m-4 4h14m-5 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h7a3 3 0 013 3v1'),
    register: svgIcon('M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z'),
  };

  // Build sidebar items
  const guestItems = [
    { href: '/', icon: I.home, label: 'الرئيسية' },
    { href: '/market', icon: I.market, label: 'سوق USDT' },
    { href: '/login', icon: I.login, label: 'دخول' },
    { href: '/register', icon: I.register, label: 'حساب جديد' },
  ];

  const userItems = [
    { href: '/', icon: I.home, label: 'الرئيسية' },
    { href: '/market', icon: I.market, label: 'سوق USDT' },
    { href: '/trades', icon: I.trades, label: 'الصفقات' },
    { href: '/wallet', icon: I.wallet, label: 'المحفظة' },
    { href: '/my_ads', icon: I.ads, label: 'إعلاناتي' },
    { href: '/create_ad', icon: I.plus, label: 'إنشاء إعلان' },
    { href: '/notifications', icon: I.bell, label: 'الإشعارات' },
    { href: '/profile', icon: I.user, label: 'الملف الشخصي' },
  ];

  const adminItem = u && u.isAdmin ? [{ href: '/admin', icon: I.admin, label: 'لوحة الإدارة' }] : [];
  const items = u ? [...userItems, ...adminItem] : guestItems;

  const navHtml = items.map(it => {
    const active = p === it.href ? ' active' : '';
    return `<a href="${it.href}" class="mobile-sidebar-item${active}">` +
      `<span class="mobile-sidebar-item-icon">${it.icon}</span>` +
      `<span>${it.label}</span></a>`;
  }).join('');

  const logoutHtml = u ? `
    <div class="mobile-sidebar-divider"></div>
    <button class="mobile-sidebar-item" onclick="doLogout()" style="color:var(--danger)">
      <span class="mobile-sidebar-item-icon">${I.logout}</span>
      <span>تسجيل الخروج</span>
    </button>` : '';

  const themeToggle = `
    <div class="mobile-sidebar-divider"></div>
    <div class="mobile-sidebar-theme">
      <button onclick="toggleTheme()" style="background:none;border:none;cursor:pointer;color:var(--text-primary);padding:4px 8px;display:flex;align-items:center;" title="تبديل المظهر">${themeIcon()}</button>
      <span style="font-size:0.8rem;">تبديل المظهر</span>
    </div>`;

  panel.innerHTML = `
    <div class="mobile-sidebar-header">
      <span class="mobile-sidebar-brand"><span>USDT</span> P2P</span>
      <button class="mobile-sidebar-close" onclick="closeMobileSidebar()" aria-label="إغلاق القائمة"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M18 6L6 18M6 6l12 12"/></svg></button>
    </div>
    <nav class="mobile-sidebar-nav">${navHtml}</nav>
    <div class="mobile-sidebar-footer">
      ${logoutHtml}
      ${themeToggle}
    </div>`;

  document.body.appendChild(panel);
}

/* Sidebar open/close */
function openMobileSidebar() {
  const overlay = document.querySelector('.mobile-sidebar-overlay');
  const panel = document.querySelector('.mobile-sidebar-panel');
  const btn = document.querySelector('.mobile-header-menu');
  if (overlay) overlay.classList.add('open');
  if (panel) panel.classList.add('open');
  if (btn) btn.setAttribute('aria-expanded', 'true');
  document.body.style.overflow = 'hidden';
}
function closeMobileSidebar() {
  const overlay = document.querySelector('.mobile-sidebar-overlay');
  const panel = document.querySelector('.mobile-sidebar-panel');
  const btn = document.querySelector('.mobile-header-menu');
  if (overlay) overlay.classList.remove('open');
  if (panel) panel.classList.remove('open');
  if (btn) btn.setAttribute('aria-expanded', 'false');
  document.body.style.overflow = '';
}
function toggleMobileSidebar() {
  const panel = document.querySelector('.mobile-sidebar-panel');
  if (panel && panel.classList.contains('open')) closeMobileSidebar();
  else openMobileSidebar();
}

// Close sidebar on Escape
document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') closeMobileSidebar();
});

/* ── Init on load ──────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  initTelegram();
  renderNav();
  // In Telegram: hide desktop nav, use mobile shell only
  if (_isTelegram) {
    const nav = document.getElementById('nav');
    if (nav) nav.style.display = 'none';
    document.body.classList.add('tg-webapp');
  }
  // Register service worker for PWA
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js').catch(() => {});
  }
});
