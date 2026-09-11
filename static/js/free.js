// --- 免费游戏页：账号登录（内置浏览器）+ 分页 + 一键入库 ---
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
            manualToggleBtn: document.getElementById('manualToggleBtn'),
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
        };
        this.pageSize = 20;
        this.page = 1;
        this.games = [];
        this.pollTimer = null;
        this.initialize();
    }

    initialize() {
        this.elements.searchBtn.addEventListener('click', () => { this.page = 1; this.fetchGames(this.elements.search.value.trim()); });
        this.elements.search.addEventListener('keydown', e => { if (e.key === 'Enter') { this.page = 1; this.fetchGames(this.elements.search.value.trim()); } });
        this.elements.refreshBtn.addEventListener('click', () => { this.page = 1; this.fetchGames(this.elements.search.value.trim()); });
        this.elements.prevPageBtn.addEventListener('click', () => { if (this.page > 1) { this.page--; this.renderGames(); } });
        this.elements.nextPageBtn.addEventListener('click', () => { if (this.page < this.totalPages()) { this.page++; this.renderGames(); } });
        this.elements.injectPageBtn.addEventListener('click', () => this.inject(this.currentPageGames()));
        this.elements.injectAllBtn.addEventListener('click', () => this.inject(this.games));
        this.elements.loginBtn.addEventListener('click', () => this.browserLogin());
        this.elements.logoutBtn.addEventListener('click', () => this.logout());
        this.elements.snackbarClose.addEventListener('click', () => this.hideSnackbar());
        if (this.elements.manualToggleBtn) {
            this.elements.manualToggleBtn.addEventListener('click', () => {
                const box = this.elements.cookieManual;
                box.style.display = (box.style.display === 'none' || !box.style.display) ? 'flex' : 'none';
            });
        }
        if (this.elements.cookieSubmitBtn) {
            this.elements.cookieSubmitBtn.addEventListener('click', () => this.manualLogin());
        }
        this.fetchGames('');
        this.restoreLogin();
    }

    /* ---------- 账号登录 ---------- */

    async restoreLogin() {
        // 1) 优先问服务端：内置浏览器是否已经登录过
        try {
            const r = await fetch('/api/steam/login/status');
            const d = await r.json();
            if (d.status === 'success' && d.account) { this.applyAccount(d.account); return; }
        } catch (e) { /* ignore */ }
        // 2) 回落到本地保存的 Cookie
        try {
            const r = await fetch('/api/config/detailed');
            if (r.ok) {
                const d = await r.json();
                const cookie = d.config && d.config.steam_cookie;
                if (cookie) { this.manualLogin(cookie, true); }
            }
        } catch (e) { /* ignore */ }
    }

    applyAccount(acc) {
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
        this.elements.logoutBtn.style.display = 'inline-block';
    }

    /** 用内置（沉默）浏览器登录 Steam */
    async browserLogin() {
        this.elements.loginBtn.disabled = true;
        try {
            const resp = await fetch('/api/steam/login/start', { method: 'POST' });
            const d = await resp.json();
            if (!d.available) {
                this.showSnackbar('当前环境没有内置浏览器，已打开 Steam 登录页，请登录后手动粘贴 Cookie。', 'warning');
                if (this.elements.cookieManual) this.elements.cookieManual.style.display = 'flex';
                window.open('https://store.steampowered.com/login/', '_blank');
                return;
            }
            this.showSnackbar('已打开登录窗口，请在窗口中完成 Steam 登录（会自动读取登录态）…', 'info');
            this.pollLogin();
        } catch (e) {
            this.showSnackbar(`打开登录窗口失败: ${e.message}`, 'error');
        } finally {
            this.elements.loginBtn.disabled = false;
        }
    }

    pollLogin() {
        clearInterval(this.pollTimer);
        const started = Date.now();
        this.pollTimer = setInterval(async () => {
            try {
                const r = await fetch('/api/steam/login/status');
                const d = await r.json();
                if (d.status === 'success' && d.account) {
                    clearInterval(this.pollTimer);
                    this.applyAccount(d.account);
                    this.showSnackbar(d.message || '已登录。', 'success');
                    return;
                }
                if (d.status === 'error') {
                    clearInterval(this.pollTimer);
                    this.showSnackbar(d.message || '登录失败。', 'error');
                    if (this.elements.cookieManual) this.elements.cookieManual.style.display = 'flex';
                    return;
                }
            } catch (e) { /* 继续轮询 */ }
            if (Date.now() - started > 300000) {
                clearInterval(this.pollTimer);
                this.showSnackbar('等待登录超时，可改用手动粘贴 Cookie。', 'warning');
            }
        }, 1500);
    }

    /** 手动粘贴 Cookie（降级方案） */
    async manualLogin(cookieValue, silent = false) {
        const cookie = (cookieValue !== undefined && cookieValue !== null)
            ? cookie : (this.elements.cookieInput.value || '').trim();
        if (!cookie) { this.showSnackbar('请输入 steamLoginSecure Cookie。', 'error'); return; }
        if (this.elements.cookieInput) this.elements.cookieInput.value = cookie;
        try {
            const resp = await fetch('/api/free/account', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ cookie })
            });
            const d = await resp.json();
            if (d.success) {
                this.applyAccount(d);
                if (!silent) this.showSnackbar('已读取账号信息。', 'success');
            } else if (!silent) {
                this.showSnackbar(d.message || '读取失败', 'error');
            }
        } catch (e) {
            if (!silent) this.showSnackbar(`请求失败: ${e.message}`, 'error');
        }
    }

    logout() {
        this.elements.cookieInput.value = '';
        this.elements.name.textContent = '未登录';
        this.elements.balance.textContent = '';
        this.elements.avatar.style.display = 'none';
        this.elements.logoutBtn.style.display = 'none';
        const bar = document.getElementById('accountBar');
        if (bar) bar.style.backgroundImage = '';
        this.showSnackbar('已清除本地登录态显示（可在设置里清除保存的 Cookie）。', 'info');
    }

    /* ---------- 免费游戏列表 ---------- */

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

    async inject(list) {
        if (!list || !list.length) { this.showSnackbar('没有可入库的游戏。', 'warning'); return; }
        const appids = list.map(g => g.appid);
        const names = {};
        list.forEach(g => { names[g.appid] = g.name; });
        this.elements.injectAllBtn.disabled = true;
        this.elements.injectPageBtn.disabled = true;
        this.showSnackbar(`正在永久入库 ${appids.length} 个游戏...`, 'info');
        try {
            const resp = await fetch('/api/free/inject', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ appids, names })
            });
            const d = await resp.json();
            if (d.success) {
                this.showSnackbar(`已永久入库 ${d.injected} 个${d.skipped ? `，跳过已存在 ${d.skipped} 个` : ''}。重启 Steam 生效。`, 'success');
            } else {
                this.showSnackbar(d.message || '入库失败', 'error');
            }
        } catch (e) {
            this.showSnackbar(`入库失败: ${e.message}`, 'error');
        } finally {
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
