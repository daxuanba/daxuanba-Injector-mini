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
        this.elements.loginBtn.addEventListener('click', () => this.login());
        this.elements.logoutBtn.addEventListener('click', () => this.logout());
        this.elements.snackbarClose.addEventListener('click', () => this.hideSnackbar());
        this.fetchGames('');
        this.restoreCookie();
    }

    async restoreCookie() {
        try {
            const r = await fetch('/api/config/detailed');
            if (r.ok) {
                const d = await r.json();
                const cookie = d.config && d.config.steam_cookie;
                if (cookie) {
                    this.elements.cookieInput.value = cookie;
                    this.login();
                }
            }
        } catch (e) { /* ignore */ }
    }

    async login() {
        const cookie = this.elements.cookieInput.value.trim();
        if (!cookie) { this.showSnackbar('请输入 steamLoginSecure Cookie。', 'error'); return; }
        this.elements.loginBtn.disabled = true;
        try {
            const resp = await fetch('/api/free/account', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ cookie })
            });
            const d = await resp.json();
            if (d.success) {
                this.elements.name.textContent = d.name || '未知账号';
                this.elements.balance.textContent = (d.balance != null)
                    ? `余额: ${(d.balance / 100).toFixed(2)} ${d.currency || ''}` : '';
                if (d.avatar) {
                    this.elements.avatar.src = d.avatar;
                    this.elements.avatar.style.display = 'block';
                }
                this.elements.logoutBtn.style.display = 'inline-block';
                this.showSnackbar('已读取账号信息。', 'success');
            } else {
                this.showSnackbar(d.message || '读取失败', 'error');
            }
        } catch (e) {
            this.showSnackbar(`请求失败: ${e.message}`, 'error');
        } finally {
            this.elements.loginBtn.disabled = false;
        }
    }

    logout() {
        this.elements.cookieInput.value = '';
        this.elements.name.textContent = '未登录';
        this.elements.balance.textContent = '';
        this.elements.avatar.style.display = 'none';
        this.elements.logoutBtn.style.display = 'none';
        this.showSnackbar('已清除本地登录态。', 'info');
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
        this.elements.grid.innerHTML = games.map(g => {
            const img = g.header_image || `https://cdn.akamai.steamstatic.com/steam/apps/${g.appid}/header.jpg`;
            return `
            <div class="game-card free-card" data-appid="${g.appid}">
                <div class="game-card-header">
                    <img src="${img}" alt="${g.name}" loading="lazy" onerror="this.parentElement.innerHTML='<div class=\\'placeholder\\'><span class=\\'material-icons\\'>hide_image</span></div>'">
                </div>
                <div class="game-card-body">
                    <span class="game-title" title="${g.name}">${g.name}</span>
                    <span class="game-appid">APPID: ${g.appid}</span>
                    <div class="game-card-actions">
                        <button class="btn btn-primary free-install" data-appid="${g.appid}"><span class="material-icons">download</span> 安装</button>
                        <button class="btn btn-icon free-store" data-appid="${g.appid}" title="商店页"><span class="material-icons">open_in_new</span></button>
                    </div>
                </div>
            </div>`;
        }).join('');

        this.elements.grid.querySelectorAll('.free-install').forEach(btn => {
            btn.addEventListener('click', e => {
                e.stopPropagation();
                window.open(`steam://install/${btn.dataset.appid}`);
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
