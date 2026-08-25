/* ============================================================
   USDT P2P Palestine — Shared JavaScript (v5)
   Auth: cookie-based sessions + localStorage user cache + CSRF
   Telegram WebApp Integration
   ============================================================ */
const API_BASE = location.origin + '/api';

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
function themeIcon() { const t = getTheme(); return t === 'dark' ? '🌙' : t === 'light' ? '☀️' : '⚙️'; }

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
      <a href="/" class="navbar-brand">🇵🇸 <span>USDT</span> P2P</a>
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
  header.innerHTML = `<div class="mobile-header-left">
      ${showBack ? '<button class="mobile-header-back" onclick="history.back()" aria-label="رجوع">←</button>' : ''}
      <span class="mobile-header-title">${title}</span>
    </div>
    <button class="mobile-header-menu" onclick="toggleMobileSidebar()" aria-label="فتح القائمة" aria-expanded="false">☰</button>`;
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

  // Build sidebar items
  const guestItems = [
    { href: '/', icon: '◈', label: 'الرئيسية' },
    { href: '/market', icon: '⇄', label: 'سوق USDT' },
    { href: '/login', icon: '→', label: 'دخول' },
    { href: '/register', icon: '+', label: 'حساب جديد' },
  ];

  const userItems = [
    { href: '/', icon: '◈', label: 'الرئيسية' },
    { href: '/market', icon: '⇄', label: 'سوق USDT' },
    { href: '/trades', icon: '◎', label: 'الصفقات' },
    { href: '/wallet', icon: '◉', label: 'المحفظة' },
    { href: '/my_ads', icon: '♢', label: 'إعلاناتي' },
    { href: '/create_ad', icon: '＋', label: 'إنشاء إعلان' },
    { href: '/notifications', icon: '⬡', label: 'الإشعارات' },
    { href: '/profile', icon: '○', label: 'الملف الشخصي' },
  ];

  const adminItem = u && u.isAdmin ? [{ href: '/admin', icon: '⚙', label: 'لوحة الإدارة' }] : [];
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
      <span class="mobile-sidebar-item-icon">←</span>
      <span>تسجيل الخروج</span>
    </button>` : '';

  const themeToggle = `
    <div class="mobile-sidebar-divider"></div>
    <div class="mobile-sidebar-theme">
      <button onclick="toggleTheme()" style="background:none;border:none;cursor:pointer;font-size:1.1rem;color:var(--text-primary);padding:4px 8px" title="تبديل المظهر">${themeIcon()}</button>
      <span style="font-size:0.8rem;">تبديل المظهر</span>
    </div>`;

  panel.innerHTML = `
    <div class="mobile-sidebar-header">
      <span class="mobile-sidebar-brand">🇵🇸 <span>USDT</span> P2P</span>
      <button class="mobile-sidebar-close" onclick="closeMobileSidebar()" aria-label="إغلاق القائمة">✕</button>
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
