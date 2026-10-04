class FreeGamesApp {
    constructor() {
        this.elements = {
            grid: document.getElementById('freeGrid'),
            loading: document.getElementById('freeLoading'),
            noResults: document.getElementById('freeNoResults'),
            search: document.getElementById('freeSearch'),
            searchBtn: document.getElementById('freeSearchBtn'),
            refreshBtn: document.getElementById('freeRefreshBtn'),
            avatar: document.getElementById('accountAvatar'),
            name: document.getElementById('accountName'),
            balance: document.getElementById('accountBalance'),
            cookieInput: document.getElementById('cookieInput'),
            cookieSubmitBtn: document.getElementById('cookieSubmitBtn'),
            cookieManual: document.getElementById('cookieManual'),
            cookieRow: document.getElementById('cookieRow'),
            manualToggleBtn: document.getElementById('manualToggleBtn'),
            openLoginBtn: document.getElementById('openLoginBtn'),
            openLoginBtn2: document.getElementById('openLoginBtn2'),
            loginModal: document.getElementById('loginModal'),
            loginStep1: document.getElementById('loginStep1'),
            loginStep2: document.getElementById('loginStep2'),
            loginUser: document.getElementById('loginUser'),
            loginPass: document.getElementById('loginPass'),
            loginCode: document.getElementById('loginCode'),
            loginErr: document.getElementById('loginErr'),
            loginErr2: document.getElementById('loginErr2'),
            loginMaskMail: document.getElementById('loginMaskMail'),
            loginNextBtn: document.getElementById('loginNextBtn'),
            loginBackBtn: document.getElementById('loginBackBtn'),
            loginCancelBtn: document.getElementById('loginCancelBtn'),
            loginModalClose: document.getElementById('loginModalClose'),
            loginHelper: document.getElementById('loginHelper'),
            loginBtn: document.getElementById('loginBtn'),
            logoutBtn: document.getElementById('logoutBtn'),
            loginBox: document.getElementById('accountLogin'),
            snackbar: document.getElementById('snackbar'),
            snackbarMessage: document.getElementById('snackbarMessage'),
            snackbarClose: document.getElementById('snackbarClose'),
            injectPageBtn: document.getElementById('injectPageBtn'),
            injectAllBtn: document.getElementById('injectAllBtn'),
            prevPageBtn: document.getElementById('prevPageBtn'),
            nextPageBtn: document.getElementById('nextPageBtn'),
            pageInfo: document.getElementById('pageInfo'),
            pagination: document.getElementById('freePagination'),
            log: document.getElementById('freeLog'),
            logClear: document.getElementById('freeLogClear'),
        };
        this.pageSize = 20;
        this.page = 1;
        this.games = [];
        this.pollTimer = null;
        this.busy = false;
        this.store = window.DxbTaskLog ? window.DxbTaskLog.local('free') : null;
        this.initialize();
    }

    log(type, msg) {
        if (this.store) this.store.append(type, msg);
    }

    initialize() {
        this.elements.searchBtn.addEventListener('click', () => { this.page = 1; this.fetchGames(this.elements.search.value.trim()); });
        this.elements.search.addEventListener('keydown', e => { if (e.key === 'Enter') { this.page = 1; this.fetchGames(this.elements.search.value.trim()); } });
        this.elements.refreshBtn.addEventListener('click', () => { this.page = 1; this.fetchGames(this.elements.search.value.trim()); });
        this.elements.prevPageBtn.addEventListener('click', () => { if (this.page > 1) { this.page--; this.renderGames(); } });
        this.elements.nextPageBtn.addEventListener('click', () => { if (this.page < this.totalPages()) { this.page++; this.renderGames(); } });
        this.elements.injectPageBtn.addEventListener('click', () => this.inject(this.currentPageGames()));
        this.elements.injectAllBtn.addEventListener('click', () => this.inject(this.games));
        if (this.elements.openLoginBtn) this.elements.openLoginBtn.addEventListener('click', () => this.openLoginModal());
        if (this.elements.openLoginBtn2) this.elements.openLoginBtn2.addEventListener('click', () => this.openLoginModal());
        if (this.elements.logoutBtn) this.elements.logoutBtn.addEventListener('click', () => this.logout());
        if (this.elements.loginNextBtn) this.elements.loginNextBtn.addEventListener('click', () => this.handleLoginNext());
        if (this.elements.loginBackBtn) this.elements.loginBackBtn.addEventListener('click', () => this.backToStep1());
        if (this.elements.loginCancelBtn) this.elements.loginCancelBtn.addEventListener('click', () => this.closeLoginModal());
        if (this.elements.loginModalClose) this.elements.loginModalClose.addEventListener('click', () => this.closeLoginModal());
        if (this.elements.loginModal) {
            this.elements.loginModal.addEventListener('mousedown', e => {
                if (e.target === this.elements.loginModal) this.closeLoginModal();
            });
        }
        if (this.elements.loginCode) {
            this.elements.loginCode.addEventListener('keydown', e => { if (e.key === 'Enter') this.handleLoginNext(); });
        }
        if (this.elements.loginPass) {
            this.elements.loginPass.addEventListener('keydown', e => { if (e.key === 'Enter') this.handleLoginNext(); });
        }
        const avToggle = document.getElementById('avatarToggleBtn');
        if (avToggle) {
            avToggle.addEventListener('click', () => {
                const on = !this.wantAvatar();
                try { localStorage.setItem('dxb-show-avatar', on ? '1' : '0'); } catch (e) { /* ignore */ }
                this.syncAvatarToggleBtn();
                this.restoreLogin();
            });
        }
        this.elements.snackbarClose.addEventListener('click', () => this.hideSnackbar());
        if (this.elements.manualToggleBtn) {
            this.elements.manualToggleBtn.addEventListener('click', () => {
                const row = this.elements.cookieRow;
                if (row) row.style.display = (row.style.display === 'none' || !row.style.display) ? 'flex' : 'none';
                const box = this.elements.cookieManual;
                if (box) box.style.display = (box.style.display === 'none' || !box.style.display) ? 'flex' : 'none';
            });
        }
        if (this.elements.cookieSubmitBtn) {
            this.elements.cookieSubmitBtn.addEventListener('click', () => this.manualLogin());
        }
        if (this.store) this.store.mount(this.elements.log);
        if (this.elements.logClear && this.store) {
            this.elements.logClear.addEventListener('click', () => this.store.clear());
        }
        this.fetchGames('');
        this.restoreLogin();
    }


    async currentCookie() {
        if (this.elements.cookieInput && (this.elements.cookieInput.value || '').trim()) {
            return this.elements.cookieInput.value.trim();
        }
        try {
            const r = await fetch('/api/config/detailed');
            if (r.ok) {
                const d = await r.json();
                const c = d.config && d.config.steam_cookie;
                if (c) return (c || '').trim();
            }
        } catch (e) { /* ignore */ }
        return '';
    }

    async checkSession(cookieValue, silent = false) {
        const cookie = (cookieValue !== undefined && cookieValue !== null && cookieValue !== '')
            ? cookieValue : await this.currentCookie();
        if (!cookie || cookie.indexOf('steamLoginSecure') < 0) {
            this.applyNoSession(silent ? '' : '请先粘贴登录 Steam 网站后的 Cookie（必须含 steamLoginSecure）。');
            this.sessionReady = false;
            return false;
        }
        try {
            const r = await fetch('/api/free/session', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ cookie })
            });
            const d = await r.json();
            if (d && d.success && d.session_ok) {
                this.cookie = cookie;
                this.sessionReady = true;
                if (this.elements.cookieInput) this.elements.cookieInput.value = cookie;
                this.applyAccount(d, silent);
                return true;
            }
            this.sessionReady = false;
            this.applyNoSession((d && d.message) || 'Steam 会话校验失败，请重新登录商店并粘贴新 Cookie。');
            return false;
        } catch (e) {
            this.sessionReady = false;
            this.applyNoSession(`连接失败: ${e.message}`);
            return false;
        }
    }

    async restoreLogin() {
        const saved = await this.currentCookie();
        if (saved && saved.indexOf('steamLoginSecure') >= 0) {
            await this.checkSession(saved, true);
        } else {
            this.applyNoSession('未连接 Steam 官方账号：点「登录 Steam」输用户名密码。');
        }
    }

    async isLoggedIn() {
        if (this.sessionReady && this.cookie) return true;
        const saved = await this.currentCookie();
        if (saved && saved.indexOf('steamLoginSecure') >= 0) return await this.checkSession(saved, true);
        this.applyNoSession('未连接 Steam 官方账号：点「登录 Steam」输用户名密码。');
        return false;
    }

    applyNoSession(msg) {
        this.sessionReady = false;
        this.elements.name.textContent = '未连接 Steam 官方账号会话';
        this.elements.balance.textContent = msg || '点「登录 Steam」输用户名密码';
        this.elements.avatar.style.display = 'none';
        if (this.elements.logoutBtn) this.elements.logoutBtn.style.display = 'none';
        if (this.elements.cookieInput && !this.elements.cookieInput.value) {
            this.elements.cookieInput.placeholder = '粘贴 Cookie（必须包含 steamLoginSecure=...）';
        }
    }

    openLoginModal() {
        this.loginChallenge = '';
        this.loginStep = 1;
        if (this.elements.loginStep1) this.elements.loginStep1.style.display = '';
        if (this.elements.loginStep2) this.elements.loginStep2.style.display = 'none';
        if (this.elements.loginBackBtn) this.elements.loginBackBtn.style.display = 'none';
        if (this.elements.loginNextBtn) {
            this.elements.loginNextBtn.textContent = '下一步';
            this.elements.loginNextBtn.disabled = false;
        }
        if (this.elements.loginErr) this.elements.loginErr.textContent = '';
        if (this.elements.loginErr2) this.elements.loginErr2.textContent = '';
        if (this.elements.loginUser) this.elements.loginUser.value = '';
        if (this.elements.loginPass) this.elements.loginPass.value = '';
        if (this.elements.loginCode) this.elements.loginCode.value = '';
        if (this.elements.loginModal) this.elements.loginModal.style.display = 'flex';
        if (this.elements.loginUser) setTimeout(() => this.elements.loginUser.focus(), 30);
    }

    closeLoginModal() {
        if (this.elements.loginModal) this.elements.loginModal.style.display = 'none';
        this.loginChallenge = '';
    }

    backToStep1() {
        this.loginStep = 1;
        if (this.elements.loginStep1) this.elements.loginStep1.style.display = '';
        if (this.elements.loginStep2) this.elements.loginStep2.style.display = 'none';
        if (this.elements.loginBackBtn) this.elements.loginBackBtn.style.display = 'none';
        if (this.elements.loginNextBtn) {
            this.elements.loginNextBtn.textContent = '下一步';
            this.elements.loginNextBtn.disabled = false;
        }
    }

    showLoginError(which, msg) {
        const box = which === 2 ? this.elements.loginErr2 : this.elements.loginErr;
        if (box) box.textContent = msg || '';
    }

    async handleLoginNext() {
        if (this.loginStep === 1) return this.doLoginStep1();
        return this.doLoginStep2();
    }

    async doLoginStep1() {
        const user = (this.elements.loginUser.value || '').trim();
        const pass = this.elements.loginPass.value || '';
        if (!user || !pass) {
            this.showLoginError(1, '请输入用户名和密码。');
            return;
        }
        this.showLoginError(1, '正在登录 Steam…');
        if (this.elements.loginNextBtn) this.elements.loginNextBtn.disabled = true;
        try {
            const r = await fetch('/api/free/login/start', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username: user, password: pass })
            });
            const d = await r.json();
            if (d && d.success) {
                this.showLoginError(1, '');
                this.log('success', '用户名密码已通过，等待邮箱验证码。');
                this.enterStep2(d);
                return;
            }
            const msg = (d && d.message) || '登录失败。';
            this.showLoginError(1, msg);
            this.log('error', `Steam 登录失败：${msg}`);
        } catch (e) {
            this.showLoginError(1, `请求失败: ${e.message}`);
            this.log('error', `登录请求失败：${e.message}`);
        } finally {
            if (this.elements.loginNextBtn) this.elements.loginNextBtn.disabled = false;
        }
    }

    enterStep2(data) {
        this.loginStep = 2;
        this.loginChallenge = data && data.challenge ? data.challenge : '';
        if (this.elements.loginStep1) this.elements.loginStep1.style.display = 'none';
        if (this.elements.loginStep2) this.elements.loginStep2.style.display = '';
        if (this.elements.loginBackBtn) this.elements.loginBackBtn.style.display = '';
        if (this.elements.loginNextBtn) {
            this.elements.loginNextBtn.textContent = '登录';
            this.elements.loginNextBtn.disabled = false;
        }
        const masked = (data && data.masked_email) || (data && data.email) || '邮箱';
        const title = document.getElementById('loginModalTitle');
        if (title) title.textContent = '邮箱验证';
        if (this.elements.loginMaskMail) this.elements.loginMaskMail.textContent = masked;
        this.showLoginError(2, '');
        if (this.elements.loginCode) setTimeout(() => this.elements.loginCode.focus(), 30);
    }

    async doLoginStep2() {
        const code = (this.elements.loginCode.value || '').trim();
        if (!code) {
            this.showLoginError(2, '请输入邮箱里的验证码。');
            return;
        }
        if (!this.loginChallenge) {
            this.showLoginError(2, '登录上下文已失效，请重新登录。');
            this.backToStep1();
            return;
        }
        this.showLoginError(2, '正在校验验证码…');
        if (this.elements.loginNextBtn) this.elements.loginNextBtn.disabled = true;
        try {
            const r = await fetch('/api/free/login/finish', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ code, challenge: this.loginChallenge })
            });
            const d = await r.json();
            if (d && d.success) {
                if (d.session && d.session.success) {
                    this.sessionReady = true;
                    this.applyAccount(d.session, false);
                    this.closeLoginModal();
                    this.showSnackbar(`登录成功：${d.session.name || 'Steam 账号'}，可以入库了。`, 'success');
                    this.log('success', `Steam 官方会话已就绪：${d.session.name || ''}`);
                } else {
                    this.showLoginError(2, (d.session && d.session.message) || d.message || '会话校验失败。');
                }
                return;
            }
            const msg = (d && d.message) || '验证码校验失败。';
            this.showLoginError(2, msg);
            this.log('error', `验证码校验失败：${msg}`);
        } catch (e) {
            this.showLoginError(2, `请求失败: ${e.message}`);
            this.log('error', `验证码请求失败：${e.message}`);
        } finally {
            if (this.elements.loginNextBtn) this.elements.loginNextBtn.disabled = false;
        }
    }

    wantAvatar() {
        try { return localStorage.getItem('dxb-show-avatar') !== '0'; } catch (e) { return true; }
    }

    syncAvatarToggleBtn() {
        const btn = document.getElementById('avatarToggleBtn');
        if (!btn) { return; }
        const on = this.wantAvatar();
        const t = btn.querySelector('.settings-text');
        const ic = btn.querySelector('.material-icons');
        if (t) { t.textContent = on ? '隐藏头像' : '显示头像'; }
        if (ic) { ic.textContent = on ? 'account_circle' : 'account_circle_off'; }
        if (!on) { this.elements.avatar.style.display = 'none'; }
    }

    applyAccount(acc, silent = false) {
        this.elements.name.textContent = acc.name || '已登录';
        if (acc.balance !== null && acc.balance !== undefined) {
            const sym = (acc.currency === 'CN' || !acc.currency) ? '¥' : (acc.currency + ' ');
            this.elements.balance.textContent = `余额: ${sym}${(acc.balance / 100).toFixed(2)}`;
        } else {
            this.elements.balance.textContent = '';
        }
        if (acc.avatar) {
            this.elements.avatar.src = acc.avatar;
            this.elements.avatar.style.display = 'block';
            this.elements.avatar.onerror = () => { this.elements.avatar.style.display = 'none'; };
        }
        if (acc.background) {
            const bar = document.getElementById('accountBar');
            if (bar) {
                bar.style.backgroundImage = `linear-gradient(rgba(0,0,0,.55), rgba(0,0,0,.75)), url("${acc.background}")`;
                bar.style.backgroundSize = 'cover';
                bar.style.backgroundPosition = 'center';
            }
        }
        if (this.elements.logoutBtn) this.elements.logoutBtn.style.display = 'inline-block';
        if (!silent) this.log('success', `已登录：${acc.name || 'Steam 账号'}`);
    }

    async manualLogin(cookieValue, silent = false) {
        const ok = await this.checkSession(cookieValue, silent);
        if (ok && !silent) this.showSnackbar('已连接 Steam 官方账号会话，可以入库了。', 'success');
        return ok;
    }

    async logout() {
        this.cookie = '';
        this.sessionReady = false;
        this.elements.cookieInput.value = '';
        this.applyNoSession('已断开本地会话。');
        const bar = document.getElementById('accountBar');
        if (bar) bar.style.backgroundImage = '';
        try {
            await fetch('/api/free/logout', { method: 'POST' });
        } catch (e) { /* ignore */ }
        this.showSnackbar('已断开 Steam 官方会话，下次需要重新登录。', 'info');
    }


    async fetchGames(query) {
        this.elements.loading.style.display = 'flex';
        this.elements.noResults.style.display = 'none';
        try {
            const url = '/api/free/games' + (query ? `?q=${encodeURIComponent(query)}` : '');
            const resp = await fetch(url);
            const d = await resp.json();
            this.games = (d.success && d.games) ? d.games : [];
            if (!d.success) this.showSnackbar(d.message || '获取失败', 'error');
            this.renderGames();
        } catch (e) {
            this.showSnackbar(`获取失败: ${e.message}`, 'error');
            this.games = [];
            this.renderGames();
        } finally {
            this.elements.loading.style.display = 'none';
        }
    }

    totalPages() { return Math.max(1, Math.ceil(this.games.length / this.pageSize)); }
    currentPageGames() {
        const start = (this.page - 1) * this.pageSize;
        return this.games.slice(start, start + this.pageSize);
    }

    renderGames() {
        this.renderPagination();
        const games = this.currentPageGames();
        if (!games.length) {
            this.elements.noResults.textContent = '没有找到免费游戏。';
            this.elements.noResults.style.display = 'block';
            this.elements.grid.innerHTML = '';
            return;
        }
        this.elements.noResults.style.display = 'none';
        this.elements.grid.innerHTML = games.map(g => `
            <div class="game-card free-card" data-appid="${g.appid}">
                <div class="game-card-header">
                    <img src="/api/steam/img/${g.appid}" alt="${g.name}" loading="lazy" referrerpolicy="no-referrer"
                         onerror="this.style.display='none'">
                </div>
                <div class="game-card-body">
                    <span class="game-title" title="${g.name}">${g.name}</span>
                    <span class="game-appid">APPID: ${g.appid}</span>
                    <div class="game-card-actions">
                        <button class="btn btn-primary free-inject" data-appid="${g.appid}" data-name="${g.name}">
                            <span class="material-icons">library_add</span> 入库
                        </button>
                        <button class="btn btn-secondary free-install" data-appid="${g.appid}" data-name="${g.name}" title="让 Steam 下载安装">
                            <span class="material-icons">download</span> 安装
                        </button>
                        <button class="btn btn-icon free-store" data-appid="${g.appid}" title="商店页">
                            <span class="material-icons">open_in_new</span>
                        </button>
                    </div>
                </div>
            </div>`).join('');

        this.elements.grid.querySelectorAll('.free-inject').forEach(btn => {
            btn.addEventListener('click', e => {
                e.stopPropagation();
                this.inject([{ appid: btn.dataset.appid, name: btn.dataset.name }]);
            });
        });
        this.elements.grid.querySelectorAll('.free-install').forEach(btn => {
            btn.addEventListener('click', e => {
                e.stopPropagation();
                this.install(btn.dataset.appid, btn.dataset.name);
            });
        });
        this.elements.grid.querySelectorAll('.free-store').forEach(btn => {
            btn.addEventListener('click', e => {
                e.stopPropagation();
                window.open(`https://store.steampowered.com/app/${btn.dataset.appid}`, '_blank');
            });
        });
    }

    renderPagination() {
        const total = this.totalPages();
        if (this.page > total) this.page = total;
        this.elements.pageInfo.textContent = `第 ${this.page} / ${total} 页（共 ${this.games.length} 个）`;
        this.elements.prevPageBtn.disabled = this.page <= 1;
        this.elements.nextPageBtn.disabled = this.page >= total;
        this.elements.pagination.style.display = this.games.length ? 'flex' : 'none';
    }

    async install(appid, name) {
        this.log('info', `请求 Steam 安装 ${name || appid}（AppID ${appid}）…`);
        try {
            const r = await fetch('/api/steam/launch', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action: 'install', appid })
            });
            const d = await r.json();
            if (d.success) {
                this.showSnackbar(`已请求 Steam 安装 ${name || appid}，请在 Steam 客户端确认。`, 'success');
                this.log('success', `已请求 Steam 安装 ${name || appid}。`);
            } else {
                this.showSnackbar(d.message || '安装请求失败', 'error');
                this.log('error', `安装请求失败：${d.message || ''}`);
            }
        } catch (e) {
            this.showSnackbar(`安装请求失败: ${e.message}`, 'error');
            this.log('error', `安装请求失败：${e.message}`);
        }
    }

    async inject(list) {
        if (this.busy) return;
        if (!list || !list.length) { this.showSnackbar('没有可入库的游戏。', 'warning'); return; }

        if (!(await this.isLoggedIn())) {
            const tip = '入库必须连 Steam 官方账号：请粘贴包含 steamLoginSecure 的 Cookie 后点「连接账号」。';
            this.showSnackbar(tip, 'warning');
            this.log('warn', tip);
            if (this.elements.cookieManual) this.elements.cookieManual.style.display = 'flex';
            return;
        }

        const appids = list.map(g => g.appid);
        const names = {};
        list.forEach(g => { names[g.appid] = g.name; });
        this.busy = true;
        this.elements.injectAllBtn.disabled = true;
        this.elements.injectPageBtn.disabled = true;
        this.showSnackbar(`正在通过 Steam 官方接口入库 ${appids.length} 个游戏...`, 'info');
        this.log('info', `开始通过官方接口入库 ${appids.length} 个游戏：${appids.slice(0, 20).join(', ')}${appids.length > 20 ? ' …' : ''}`);
        try {
            const resp = await fetch('/api/free/inject', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ appids, names, cookie: this.cookie || '' })
            });
            const d = await resp.json();
            if (d.success) {
                const msg = `已通过 Steam 官方接口写入 ${d.injected} 个到你的账号库`
                    + (d.account ? `（${d.account}）` : '')
                    + (d.injected ? '，永久有效、不用重启 Steam' : '');
                this.showSnackbar(msg, 'success');
                this.log('success', msg);
                (d.items || []).forEach(it => {
                    if (it.status === 'added') this.log('success', `[官方入库] ${it.name || it.appid} (${it.appid})`);
                });
                const bad = (d.items || []).filter(it => it.status !== 'added');
                if (bad.length) {
                    bad.slice(0, 20).forEach(it => this.log('error', `[失败] ${it.name || it.appid} (${it.appid})：${it.message || ''}`));
                }
            } else if (d.need_login) {
                this.showSnackbar(d.message || '请先登录 Steam 账号。', 'warning');
                this.log('warn', d.message || '请先登录 Steam 账号。');
            } else {
                this.showSnackbar(d.message || '入库失败', 'error');
                this.log('error', `入库失败：${d.message || ''}`);
            }
        } catch (e) {
            this.showSnackbar(`入库失败: ${e.message}`, 'error');
            this.log('error', `入库失败：${e.message}`);
        } finally {
            this.busy = false;
            this.elements.injectAllBtn.disabled = false;
            this.elements.injectPageBtn.disabled = false;
        }
    }

    showSnackbar(message, type = 'info') {
        this.elements.snackbarMessage.textContent = message;
        this.elements.snackbar.className = `snackbar show ${type}`;
        clearTimeout(this._t);
        this._t = setTimeout(() => this.hideSnackbar(), 5000);
    }
    hideSnackbar() { this.elements.snackbar.classList.remove('show'); }
}

document.addEventListener('DOMContentLoaded', () => { new FreeGamesApp(); });
