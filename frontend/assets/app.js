/* ============================================================
   USDT P2P Palestine — Shared JavaScript (v6)
   Auth: cookie-based sessions + localStorage user cache + CSRF
   Telegram Deep-Link Login + Admin Button Fix + Icon System
   ============================================================ */
const API_BASE = location.origin + '/api';

/* ── Professional SVG Icon System ───────────────────────── */
const ICO = {
  home:    `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 9.5L12 3l9 6.5V20a1 1 0 01-1 1H4a1 1 0 01-1-1V9.5z"/><path d="M9 21V12h6v9"/></svg>`,
  market:  `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 20h18"/><path d="M5 16l4-8 4 4 4-10"/></svg>`,
  trades:  `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M17 3l4 4-4 4"/><path d="M3 11V9a4 4 0 014-4h14"/><path d="M7 21l-4-4 4-4"/><path d="M21 13v2a4 4 0 01-4 4H3"/></svg>`,
  wallet:  `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="5" width="20" height="14" rx="2"/><path d="M16 12h2"/><path d="M2 10h20"/></svg>`,
  plus:    `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 8v8m-4-4h8"/></svg>`,
  bell:    `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M18 8a6 6 0 00-12 0c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 01-3.46 0"/></svg>`,
  user:    `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="4"/><path d="M5 20c0-4 3-7 7-7s7 3 7 7"/></svg>`,
  admin:   `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2l8 4v6c0 5.25-3.5 8.75-8 10-4.5-1.25-8-4.75-8-10V6l8-4z"/><path d="M9 12l2 2 4-4"/></svg>`,
  settings:`<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 01-2.83 2.83l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/></svg>`,
  guide:   `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 015.83 1c0 2-3 3-3 3"/><path d="M12 17h.01"/></svg>`,
  palette: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><circle cx="8" cy="10" r="1.5" fill="currentColor"/><circle cx="16" cy="10" r="1.5" fill="currentColor"/><circle cx="12" cy="15" r="1.5" fill="currentColor"/></svg>`,
  logout:  `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4"/><path d="M16 17l5-5-5-5"/><path d="M21 12H9"/></svg>`,
  login:   `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M15 3h4a2 2 0 012 2v14a2 2 0 01-2 2h-4"/><path d="M10 17l5-5-5-5"/><path d="M15 12H3"/></svg>`,
  register:`<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M16 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="8.5" cy="7" r="4"/><path d="M20 8v6m3-3h-6"/></svg>`,
  back:    `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M15 19l-7-7 7-7"/></svg>`,
  close:   `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6L6 18M6 6l12 12"/></svg>`,
  menu:    `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M4 6h16M4 12h16M4 18h16"/></svg>`,
  buy:     `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14m-7-7h14"/></svg>`,
  sell:    `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14m-7-7l7 7-7 7"/></svg>`,
  shield:  `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2l8 4v6c0 5.25-3.5 8.75-8 10-4.5-1.25-8-4.75-8-10V6l8-4z"/></svg>`,
  chart:   `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 20h18"/><path d="M5 16l4-8 4 4 4-10"/></svg>`,
  dollar:  `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6"/></svg>`,
  refresh: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M23 4v6h-6"/><path d="M1 20v-6h6"/><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/></svg>`,
  lock:    `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0110 0v4"/></svg>`,
  globe:   `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M2 12h20"/><path d="M12 2a15.3 15.3 0 014 10 15.3 15.3 0 01-4 10 15.3 15.3 0 01-4-10 15.3 15.3 0 014-10z"/></svg>`,
  moon:    `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/></svg>`,
  sun:     `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><path d="M12 1v2m0 18v2M4.22 4.22l1.42 1.42m12.72 12.72l1.42 1.42M1 12h2m18 0h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>`,
  list:    `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/></svg>`,
  check:   `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6L9 17l-5-5"/></svg>`,
  refresh2:`<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/></svg>`,
};

/* ── Telegram Deep-Link Login ────────────────────────── */
window.__tgLoginPending = false;
(function() {
  const params = new URLSearchParams(location.search);
  const tgToken = params.get('tg_token');
  if (!tgToken) return;
  window.__tgLoginPending = true;
  try { sessionStorage.setItem('tg_login_pending', '1'); } catch {}
  params.delete('tg_token');
  const cleanUrl = location.pathname + (params.toString() ? '?' + params.toString() : '') + location.hash;
  history.replaceState(null, '', cleanUrl);
  fetch(API_BASE + '/auth/telegram-login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: 'token=' + encodeURIComponent(tgToken),
    credentials: 'include',
  }).then(r => r.json()).then(data => {
    if (data.ok) {
      if (data.csrf_token) try { localStorage.setItem('csrf_token', data.csrf_token); } catch {}
      fetch(API_BASE + '/auth/me', { credentials: 'include' })
        .then(r => r.json()).then(me => {
          if (me && me.authenticated) try { localStorage.setItem(USER_KEY, JSON.stringify(me)); } catch {}
          location.reload();
        }).catch(() => location.reload());
    } else {
      console.warn('[tg-login] Failed:', data.error);
      window.__tgLoginPending = false;
      try { sessionStorage.removeItem('tg_login_pending'); } catch {}
    }
  }).catch(() => {
    window.__tgLoginPending = false;
    try { sessionStorage.removeItem('tg_login_pending'); } catch {}
  });
})();

/* ── Telegram WebApp SDK ──────────────────────────────── */
const tg = window.Telegram?.WebApp || null;
let _isTelegram = !!tg;
function initTelegram() {
  if (!tg) return;
  tg.expand(); tg.ready();
  if (tg.themeParams) {
    Object.entries({ '--tg-bg': 'bg_color', '--tg-text': 'text_color', '--tg-hint': 'hint_color', '--tg-link': 'link_color', '--tg-button': 'button_color', '--tg-button-text': 'button_text_color', '--tg-secondary-bg': 'secondary_bg_color' }).forEach(([v, k]) => {
      document.documentElement.style.setProperty(v, tg.themeParams[k] || '');
    });
  }
  tg.MainButton.hide();
  tg.BackButton.onClick(() => { window.history.length > 1 ? window.history.back() : tg.close(); });
  tg.setHeaderColor('#07090D');
  tg.setBackgroundColor('#07090D');
}
function isTelegram() { return _isTelegram; }

/* ── User State ───────────────────────────────────────── */
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
  localStorage.removeItem(LOGOUT_KEY);
}
function clearUser() { _user = null; _csrf = ''; localStorage.removeItem(USER_KEY); localStorage.removeItem(CSRF_KEY); }
function isLoggedIn() { return !!_user; }
function currentUser() { return _user; }
function isUserAdmin(u) {
  u = u || _user;
  return !!(u && (u.isAdmin === true || u.status === 'ADMIN'));
}

/* ── Theme & Accent ───────────────────────────────────── */
const THEME_KEY = 'usp_theme';
const ACCENT_KEY = 'usp_accent';
function getTheme() { return localStorage.getItem(THEME_KEY) || 'dark'; }
function setTheme(t) { localStorage.setItem(THEME_KEY, t); applyTheme(t); }
function applyTheme(t) {
  if (t === 'auto') t = window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', t);
}
applyTheme(getTheme());
function toggleTheme() {
  const cur = getTheme(); const next = cur === 'dark' ? 'light' : cur === 'light' ? 'auto' : 'dark';
  setTheme(next);
  toast(next === 'dark' ? '🌙 الوضع الليلي' : next === 'light' ? '☀️ الوضع الفاتح' : '⚙️ تلقائي');
}
const ACCENTS = [
  { id: 'green', label: 'أخضر', color: '#00D6A0' },
  { id: 'yellow', label: 'أصفر', color: '#F5C542' },
  { id: 'blue', label: 'أزرق', color: '#3B82F6' },
  { id: 'red', label: 'أحمر', color: '#EF4444' },
];
function getAccent() { return localStorage.getItem(ACCENT_KEY) || 'green'; }
function setAccent(id) { localStorage.setItem(ACCENT_KEY, id); document.documentElement.setAttribute('data-accent', id); }
function applyAccent() { document.documentElement.setAttribute('data-accent', getAccent()); }
applyAccent();
function toggleAccentPicker(ev) {
  ev.stopPropagation();
  let pop = document.getElementById('accent-picker');
  if (!pop) {
    pop = document.createElement('div');
    pop.id = 'accent-picker';
    pop.className = 'theme-picker-popover';
    pop.innerHTML = `<div class="theme-picker-title">لون الواجهة</div><div class="theme-picker-options"></div>`;
    document.body.appendChild(pop);
    const opts = pop.querySelector('.theme-picker-options');
    ACCENTS.forEach(a => {
      const btn = document.createElement('button');
      btn.className = 'theme-picker-opt' + (getAccent() === a.id ? ' selected' : '');
      btn.innerHTML = `<span class="theme-picker-swatch" style="background:${a.color}"></span><span>${a.label}</span>${ICO.check}`;
      btn.onclick = (e) => { e.stopPropagation(); setAccent(a.id); opts.querySelectorAll('.theme-picker-opt').forEach(o => o.classList.remove('selected')); btn.classList.add('selected'); toast('تم تغيير اللون'); };
      opts.appendChild(btn);
    });
    document.addEventListener('click', () => pop.classList.remove('open'));
  }
  pop.classList.toggle('open');
}

/* ── Interactive Guide ────────────────────────────────── */
const GUIDE_KEY = 'usp_guide_done';
const GUIDE_STEPS = [
  { icon: ICO.user, title: 'إنشاء حساب', desc: 'أنشئ حسابك بشكل آمن وسريع. اختر اسم مستخدم وكلمة مرور قوية.' },
  { icon: ICO.trades, title: 'اختر شراء أو بيع USDT', desc: 'تصفح سوق USDT واختر أفضل عرض يناسبك. السعر لحظي من السوق.' },
  { icon: ICO.list, title: 'اختر العرض المناسب', desc: 'كل عرض يُظهر السعر وطريقة الدفع والمبلغ المتاح والسمعة.' },
  { icon: ICO.shield, title: 'الدفع والحماية', desc: 'USDT محمية في نظام الضمان حتى يتم تأكيد الدفع.' },
  { icon: ICO.check, title: 'تأكيد العملية', desc: 'بعد الدفع، يؤكد البائع ثم يُحرر USDT لك. كل خطوة موثقة.' },
  { icon: ICO.wallet, title: 'المحفظة', desc: 'أدر محفظتك: أودع أو اسحب، وتابع رصيدك وسجل المعاملات.' },
  { icon: ICO.chart, title: 'مراقبة السعر', desc: 'تابع سعر USDT لحظياً مع الرسم البياني. أطلق تنبيهات سعر.' },
];
let _guideStep = 0;
function openGuide() { _guideStep = 0; renderGuideStep(); const o = document.getElementById('guide-overlay'); if (o) o.classList.add('open'); }
function closeGuide() { const o = document.getElementById('guide-overlay'); if (o) o.classList.remove('open'); localStorage.setItem(GUIDE_KEY, '1'); }
function guideNext() { if (_guideStep < GUIDE_STEPS.length - 1) { _guideStep++; renderGuideStep(); } else renderGuideFinal(); }
function guidePrev() { if (_guideStep > 0) { _guideStep--; renderGuideStep(); } }
function renderGuideStep() {
  const s = GUIDE_STEPS[_guideStep];
  const body = document.querySelector('.guide-body');
  const footer = document.querySelector('.guide-footer');
  const prog = document.querySelector('.guide-progress');
  if (!body) return;
  body.innerHTML = `<div class="guide-step-icon" style="background:var(--primary-dim,rgba(0,214,160,0.1));">${s.icon}</div><div class="guide-step-title">${s.title}</div><div class="guide-step-desc">${s.desc}</div>`;
  if (prog) prog.innerHTML = GUIDE_STEPS.map((_, i) => `<div class="guide-progress-dot${i === _guideStep ? ' active' : ''}"></div>`).join('');
  if (footer) footer.innerHTML = `<button class="guide-btn guide-btn-ghost" onclick="guidePrev()" ${_guideStep === 0 ? 'style="visibility:hidden"' : ''}>السابق</button><button class="guide-skip" onclick="closeGuide()">تخطي</button><button class="guide-btn guide-btn-primary" onclick="guideNext()">${_guideStep === GUIDE_STEPS.length - 1 ? 'جاهز!' : 'التالي'}</button>`;
}
function renderGuideFinal() {
  const body = document.querySelector('.guide-body');
  const footer = document.querySelector('.guide-footer');
  const prog = document.querySelector('.guide-progress');
  if (!body) return;
  body.innerHTML = `<div class="guide-step-icon" style="background:var(--primary-dim,rgba(0,214,160,0.1));color:var(--primary,#00D6A0);">${ICO.check}</div><div class="guide-step-title">جاهز للبدء؟</div><div class="guide-step-desc">أنت الآن جاهز لاستخدام المنصة!</div><div class="guide-final-actions"><a href="/market.html" class="guide-btn guide-btn-primary">شراء USDT</a><a href="/market.html?tab=sell" class="guide-btn" style="background:var(--bg-card-hover,#151E27);color:var(--text-primary,#F5F7FA);">بيع USDT</a></div>`;
  if (prog) prog.innerHTML = GUIDE_STEPS.map(() => `<div class="guide-progress-dot active"></div>`).join('');
  if (footer) footer.innerHTML = `<button class="guide-btn guide-btn-ghost" onclick="guidePrev()">السابق</button><button class="guide-btn guide-btn-primary" onclick="closeGuide()">إغلاق</button>`;
}
function createGuideOverlay() {
  if (document.getElementById('guide-overlay')) return;
  const o = document.createElement('div');
  o.id = 'guide-overlay'; o.className = 'guide-overlay';
  o.innerHTML = `<div class="guide-modal"><div class="guide-header"><span class="guide-header-title">كيف تعمل المنصة؟</span><button class="guide-close" onclick="closeGuide()" aria-label="إغلاق">${ICO.close}</button></div><div class="guide-body"></div><div class="guide-progress"></div><div class="guide-footer"></div></div>`;
  o.addEventListener('click', e => { if (e.target === o) closeGuide(); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') closeGuide(); });
  document.body.appendChild(o);
}
createGuideOverlay();

/* ── Toast ────────────────────────────────────────────── */
let _tt;
function toast(msg, ms) {
  ms = ms || 3000;
  let el = document.getElementById('toast');
  if (!el) { el = document.createElement('div'); el.id = 'toast'; document.body.appendChild(el); }
  clearTimeout(_tt); el.textContent = msg; el.className = 'toast show';
  _tt = setTimeout(() => el.className = 'toast', ms);
}

/* ── API ──────────────────────────────────────────────── */
async function api(path, opts) {
  opts = opts || {};
  const url = API_BASE + path;
  const headers = Object.assign({}, opts.headers);
  if (opts.body && typeof opts.body === 'object' && !(opts.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(opts.body);
  }
  if (['POST', 'PUT', 'DELETE'].includes(opts.method || 'GET') && _csrf) headers['X-CSRF-Token'] = _csrf;
  try {
    const res = await fetch(url, { credentials: 'same-origin', ...opts, headers });
    const json = await res.json().catch(() => ({}));
    if (res.status === 401 && json.authenticated === false) { clearUser(); return json; }
    if (res.status === 429) { toast('تم تجاوز الحد المسموح'); return json; }
    if (!res.ok && !json.ok) { toast(json.error || 'خطأ', 4000); return json; }
    return json;
  } catch { toast(navigator.onLine === false ? 'لا يوجد اتصال' : 'خطأ في الاتصال'); return null; }
}

/* ── Auth helpers ─────────────────────────────────────── */
async function doRegister(username, email, password) {
  const r = await api('/auth/register', { method: 'POST', body: { username, email, password } });
  if (r?.ok) { const me = await api('/auth/me'); if (me?.authenticated) saveUser(me, r.csrf_token); }
  return r;
}
async function doLogin(identifier, password) {
  const r = await api('/auth/login', { method: 'POST', body: { username: identifier, password } });
  if (r?.ok) { const me = await api('/auth/me'); if (me?.authenticated) saveUser(me, r.csrf_token); }
  return r;
}
async function doAdminLogin(username, password) {
  const r = await api('/auth/admin-login', { method: 'POST', body: { username, password } });
  if (r?.ok) { const me = await api('/auth/me'); if (me?.authenticated) saveUser({ ...me, isAdmin: true }, r.csrf_token); }
  return r;
}
async function doLogout() {
  localStorage.setItem(LOGOUT_KEY, '1');
  await api('/auth/logout', { method: 'POST' });
  clearUser(); window.location.href = '/login.html';
}
function wasLoggedOut() { return localStorage.getItem(LOGOUT_KEY) === '1'; }
function requireAuth() {
  if (!isLoggedIn()) {
    const rt = encodeURIComponent(location.pathname + location.search);
    location.href = '/login.html?returnTo=' + rt;
    return false;
  }
  return true;
}

/* ── Status helpers ───────────────────────────────────── */
const STATUS_MAP = {
  OPEN: { label: 'مفتوحة', cls: 'badge-buy' }, PENDING: { label: 'بانتظار', cls: 'badge-pending' },
  PAYMENT_SENT: { label: 'تم الدفع', cls: 'badge-info' }, COMPLETED: { label: 'مكتمل', cls: 'badge-success' },
  CANCELLED: { label: 'ملغي', cls: 'badge-error' }, DISPUTED: { label: 'نزاع', cls: 'badge-error' },
  SELL: { label: 'بيع', cls: 'badge-sell' }, BUY: { label: 'شراء', cls: 'badge-buy' },
};
function statusBadge(s) { const i = STATUS_MAP[s] || { label: s, cls: '' }; return `<span class="badge ${i.cls}">${i.label}</span>`; }
function esc(s) { const d = document.createElement('div'); d.textContent = s ?? ''; return d.innerHTML; }
function fmtNum(n, d) { return Number(n || 0).toFixed(d ?? 2); }
function fmtDate(d) { return d ? new Date(d).toLocaleString('ar', { dateStyle: 'medium', timeStyle: 'short' }) : ''; }

/* ── Navigation ───────────────────────────────────────── */
function themeIcon() { return getTheme() === 'dark' ? ICO.moon : getTheme() === 'light' ? ICO.sun : ICO.settings; }

const PAGE_TITLES = {
  '/': 'الرئيسية', '/market.html': 'سوق USDT', '/trades.html': 'الصفقات', '/wallet.html': 'المحفظة',
  '/profile.html': 'الملف الشخصي', '/create_ad.html': 'إنشاء إعلان', '/notifications.html': 'الإشعارات',
  '/login.html': 'دخول', '/register.html': 'حساب جديد', '/admin_login.html': 'دخول الإدارة',
  '/my_ads.html': 'إعلاناتي', '/disputes.html': 'النزاعات',
};
const INNER_PAGES = ['/trade', '/trader', '/wallet', '/profile', '/create_ad', '/edit_ad', '/notifications', '/my_ads', '/disputes'];
const STANDALONE_PAGES = ['/admin', '/admin_login', '/login', '/register'];
function getPageTitle(p) {
  if (PAGE_TITLES[p]) return PAGE_TITLES[p];
  if (p.startsWith('/trade/')) return 'تفاصيل الصفقة';
  if (p.startsWith('/trader/')) return 'البروفايل';
  return 'USDT P2P';
}
function needsBackButton(p) { return INNER_PAGES.some(pg => p.startsWith(pg)); }
function isStandalonePage(p) { return STANDALONE_PAGES.some(pg => p.startsWith(pg)); }

/* ── Desktop Navbar ───────────────────────────────────── */
function renderNav() {
  const u = currentUser();
  const p = location.pathname;

  // Remove stale bottom-nav
  document.querySelectorAll('.bottom-nav, #bottomNav, #bottom-nav, .mobile-bottom-nav').forEach(el => el.remove());
  document.body.classList.remove('has-bottom-nav');

  if (isStandalonePage(p)) return;

  const nav = document.getElementById('nav');
  if (nav) {
    const adminBtn = isUserAdmin(u) ? `<a href="/admin.html" class="navbar-admin-btn">${ICO.shield} لوحة الإدارة</a>` : '';
    nav.innerHTML = `<div class="navbar-inner">
      <a href="/" class="navbar-brand">${ICO.shield} <span>USDT</span> P2P</a>
      <div class="navbar-links">
        ${u ? `
          <a href="/market.html">السوق</a>
          <a href="/trades.html">الصفقات</a>
          <a href="/wallet.html">المحفظة</a>
          <a href="/notifications.html">الإشعارات</a>
          <a href="/profile.html">حسابي</a>
          ${adminBtn}
        ` : `
          <a href="/login.html" class="btn-nav">دخول</a>
          <a href="/register.html" class="btn-nav-accent btn-nav">حساب جديد</a>
        `}
        <button onclick="openGuide()" style="background:none;border:none;cursor:pointer;padding:4px 8px;color:var(--text-secondary,#8A96A6)" title="كيف تعمل المنصة؟">${ICO.guide}</button>
        <button onclick="toggleAccentPicker(event)" style="background:none;border:none;cursor:pointer;padding:4px 8px;color:var(--text-secondary,#8A96A6)" title="لون الواجهة">${ICO.palette}</button>
        <button onclick="toggleTheme()" style="background:none;border:none;cursor:pointer;padding:4px 8px;color:var(--text-secondary,#8A96A6)" title="تبديل المظهر">${themeIcon()}</button>
      </div>
    </div>`;
  }

  buildMobileShell(u, p);
}

/* ── Mobile Sidebar ───────────────────────────────────── */
let _sidebarBuilt = false;
function buildMobileShell(u, p) {
  if (_sidebarBuilt && document.querySelector('.mobile-header')) {
    // Update admin items without full rebuild
    updateSidebarAdminItems(u);
    return;
  }
  _sidebarBuilt = true;

  const title = getPageTitle(p);
  const showBack = needsBackButton(p);

  // Mobile Header
  const header = document.createElement('header');
  header.className = 'mobile-header';
  header.innerHTML = `<div class="mobile-header-left">
      ${showBack ? `<button class="mobile-header-back" onclick="history.back()" aria-label="رجوع">${ICO.back}</button>` : ''}
      <span class="mobile-header-title">${title}</span>
    </div>
    <button class="mobile-header-menu" onclick="toggleMobileSidebar()" aria-label="فتح القائمة">${ICO.menu}</button>`;
  document.body.prepend(header);

  // Overlay
  const overlay = document.createElement('div');
  overlay.className = 'mobile-sidebar-overlay';
  overlay.onclick = closeMobileSidebar;
  document.body.appendChild(overlay);

  // Panel
  const panel = document.createElement('aside');
  panel.className = 'mobile-sidebar-panel';
  panel.setAttribute('role', 'navigation');
  panel.setAttribute('aria-label', 'قائمة التنقل');

  rebuildSidebarContent(panel, u, p);
  document.body.appendChild(panel);
}

function rebuildSidebarContent(panel, u, p) {
  const guestItems = [
    { href: '/', icon: ICO.home, label: 'الرئيسية' },
    { href: '/market.html', icon: ICO.market, label: 'سوق USDT' },
    { href: '/login.html', icon: ICO.login, label: 'دخول' },
    { href: '/register.html', icon: ICO.register, label: 'حساب جديد' },
  ];
  const userItems = [
    { href: '/', icon: ICO.home, label: 'الرئيسية' },
    { href: '/market.html', icon: ICO.market, label: 'سوق USDT' },
    { href: '/trades.html', icon: ICO.trades, label: 'الصفقات' },
    { href: '/wallet.html', icon: ICO.wallet, label: 'المحفظة' },
    { href: '/create_ad.html', icon: ICO.plus, label: 'إنشاء إعلان' },
    { href: '/notifications.html', icon: ICO.bell, label: 'الإشعارات' },
    { href: '/profile.html', icon: ICO.user, label: 'الملف الشخصي' },
  ];
  const adminItem = isUserAdmin(u) ? [{ href: '/admin.html', icon: ICO.admin, label: 'لوحة الإدارة', cls: 'sidebar-admin-item' }] : [];
  const items = u ? [...userItems, ...adminItem] : guestItems;

  const navHtml = items.map(it => {
    const active = p === it.href || (it.href !== '/' && p.startsWith(it.href)) ? ' active' : '';
    const cls = it.cls || '';
    return `<a href="${it.href}" class="mobile-sidebar-item${active} ${cls}">
      <span class="mobile-sidebar-item-icon">${it.icon}</span>
      <span>${it.label}</span>
    </a>`;
  }).join('');

  const logoutHtml = u ? `
    <div class="mobile-sidebar-divider"></div>
    <button class="mobile-sidebar-item" onclick="doLogout()" style="color:var(--danger,#FF5C6C)">
      <span class="mobile-sidebar-item-icon">${ICO.logout}</span>
      <span>تسجيل الخروج</span>
    </button>` : '';

  panel.innerHTML = `
    <div class="mobile-sidebar-header">
      <span class="mobile-sidebar-brand"><span style="color:var(--primary,#00D6A0)">USDT</span> P2P</span>
      <button class="mobile-sidebar-close" onclick="closeMobileSidebar()" aria-label="إغلاق">${ICO.close}</button>
    </div>
    <nav class="mobile-sidebar-nav">${navHtml}</nav>
    <div class="mobile-sidebar-footer">
      ${logoutHtml}
      <div class="mobile-sidebar-divider"></div>
      <button class="mobile-sidebar-item" onclick="closeMobileSidebar();setTimeout(openGuide,300)" style="color:var(--text-secondary,#8A96A6)">
        <span class="mobile-sidebar-item-icon">${ICO.guide}</span>
        <span>كيف تعمل المنصة؟</span>
      </button>
      <button class="mobile-sidebar-item" onclick="toggleAccentPicker(event)" style="color:var(--text-secondary,#8A96A6)">
        <span class="mobile-sidebar-item-icon">${ICO.palette}</span>
        <span>لون الواجهة</span>
      </button>
      <button class="mobile-sidebar-item" onclick="toggleTheme()" style="color:var(--text-secondary,#8A96A6)">
        <span class="mobile-sidebar-item-icon">${themeIcon()}</span>
        <span>${getTheme() === 'dark' ? 'الوضع الليلي' : getTheme() === 'light' ? 'الوضع الفاتح' : 'تلقائي'}</span>
      </button>
    </div>`;
}

function updateSidebarAdminItems(u) {
  const panel = document.querySelector('.mobile-sidebar-panel');
  if (!panel) return;
  const nav = panel.querySelector('.mobile-sidebar-nav');
  if (!nav) return;

  // Check if admin item already exists
  const existingAdmin = nav.querySelector('.sidebar-admin-item');
  const shouldShow = isUserAdmin(u);

  if (shouldShow && !existingAdmin) {
    // Add admin item before logout
    const adminLink = document.createElement('a');
    adminLink.href = '/admin.html';
    adminLink.className = 'mobile-sidebar-item sidebar-admin-item';
    adminLink.innerHTML = `<span class="mobile-sidebar-item-icon">${ICO.admin}</span><span>لوحة الإدارة</span>`;
    // Insert before the divider
    const divider = nav.nextElementSibling;
    if (divider) nav.parentElement.insertBefore(adminLink, divider);
    else nav.parentElement.appendChild(adminLink);
  } else if (!shouldShow && existingAdmin) {
    existingAdmin.remove();
  }
}

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
  document.querySelectorAll('.mobile-sidebar-overlay, .mobile-sidebar-panel').forEach(el => el.classList.remove('open'));
  const btn = document.querySelector('.mobile-header-menu');
  if (btn) btn.setAttribute('aria-expanded', 'false');
  document.body.style.overflow = '';
}
function toggleMobileSidebar() {
  const panel = document.querySelector('.mobile-sidebar-panel');
  panel && panel.classList.contains('open') ? closeMobileSidebar() : openMobileSidebar();
}
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeMobileSidebar(); });

/* ── Refresh user from server (updates isAdmin etc.) ── */
async function refreshUserFromServer() {
  if (window.__tgLoginPending) return;
  try {
    const me = await fetch(API_BASE + '/auth/me', { credentials: 'include' }).then(r => r.json());
    if (me && me.authenticated) {
      const old = currentUser() || {};
      const merged = { ...old, ...me };
      saveUser(merged, me.csrf_token || _csrf);
      try { sessionStorage.removeItem('tg_login_pending'); } catch {}
      renderNav();
    } else if (me && me.authenticated === false) {
      clearUser();
    }
  } catch {}
}

/* ── Init on load ─────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  initTelegram();
  renderNav();
  refreshUserFromServer();
  if (_isTelegram) {
    const nav = document.getElementById('nav');
    if (nav) nav.style.display = 'none';
    document.body.classList.add('tg-webapp');
  }
  if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => {});
});
