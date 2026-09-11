// --- 游戏推荐页：特惠 / 热销 / 新品 / 即将推出 ---
// 封面图用 Steam 官方给的完整 header_image（带 hash 目录），走 /api/steam/proxy 代理，
// 拼固定模板对这类新游戏必然 404。
class RecommendApp {
    constructor() {
        this.elements = {
            sections: document.getElementById('recSections'),
            loading: document.getElementById('recLoading'),
            noResults: document.getElementById('recNoResults'),
            refreshBtn: document.getElementById('recRefreshBtn'),
            snackbar: document.getElementById('snackbar'),
            snackbarMessage: document.getElementById('snackbarMessage'),
            snackbarClose: document.getElementById('snackbarClose'),
            log: document.getElementById('recLog'),
            logClear: document.getElementById('recLogClear'),
        };
        this.pollTimer = null;
        this.busy = false;
        // 入库日志走本地快照：切页回来日志还在
        this.store = window.DxbTaskLog ? window.DxbTaskLog.local('recommend') : null;
        this.elements.refreshBtn.addEventListener('click', () => this.load());
        this.elements.snackbarClose.addEventListener('click', () => this.hideSnackbar());
        if (this.store) this.store.mount(this.elements.log);
        if (this.elements.logClear && this.store) {
            this.elements.logClear.addEventListener('click', () => this.store.clear());
        }
        this.load();
    }

    log(type, msg) {
        if (this.store) this.store.append(type, msg);
    }

    fmtPrice(cents, currency) {
        if (cents === null || cents === undefined) return '';
        if (cents === 0) return '免费';
        return `¥${(cents / 100).toFixed(2)}`;
    }

    imgUrl(g) {
        if (g && g.image) {
            return `/api/steam/proxy?u=${encodeURIComponent(g.image)}&appid=${encodeURIComponent(g.appid)}`;
        }
        return `/api/steam/img/${g.appid}`;
    }

    async load() {
        this.elements.loading.style.display = 'flex';
        this.elements.noResults.style.display = 'none';
        try {
            const resp = await fetch('/api/recommend');
            const d = await resp.json();
            if (d.success && d.sections && d.sections.length) {
                this.render(d.sections);
            } else {
                this.elements.sections.innerHTML = '';
                this.elements.noResults.textContent = d.message || '暂时拿不到推荐数据，请稍后重试。';
                this.elements.noResults.style.display = 'block';
            }
        } catch (e) {
            this.elements.noResults.textContent = `获取推荐失败: ${e.message}`;
            this.elements.noResults.style.display = 'block';
        } finally {
            this.elements.loading.style.display = 'none';
        }
    }

    render(sections) {
        this.elements.sections.innerHTML = sections.map(sec => {
            const cards = sec.games.map(g => {
                const price = this.fmtPrice(g.final_price, g.currency);
                const off = g.discount_percent > 0
                    ? `<span class="price-off">-${g.discount_percent}%</span>` : '';
                const oldPrice = (g.discount_percent > 0 && g.original_price)
                    ? `<span class="price-original">${this.fmtPrice(g.original_price, g.currency)}</span>` : '';
                return `
                <div class="game-card rec-card" data-appid="${g.appid}">
                    <div class="game-card-header">
                        <img src="${this.imgUrl(g)}" alt="${g.name}" loading="lazy" referrerpolicy="no-referrer"
                             onerror="this.style.display='none'">
                    </div>
                    <div class="game-card-body">
                        <span class="game-title" title="${g.name}">${g.name}</span>
                        <span class="game-appid">APPID: ${g.appid}</span>
                        <div class="rec-price-row">${off}${price}${oldPrice}</div>
                        <div class="game-card-actions">
                            <button class="btn btn-primary rec-inject" data-appid="${g.appid}" data-name="${g.name}">
                                <span class="material-icons">library_add</span> 入库
                            </button>
                            <button class="btn btn-secondary rec-install" data-appid="${g.appid}" data-name="${g.name}" title="让 Steam 下载安装">
                                <span class="material-icons">download</span> 安装
                            </button>
                            <button class="btn btn-icon rec-store" data-appid="${g.appid}" title="商店页">
                                <span class="material-icons">open_in_new</span>
                            </button>
                        </div>
                    </div>
                </div>`;
            }).join('');
            return `
            <section class="rec-section">
                <h3 class="rec-section-title">${sec.title}</h3>
                <div class="file-grid">${cards}</div>
            </section>`;
        }).join('');

        this.elements.sections.querySelectorAll('.rec-inject').forEach(btn => {
            btn.addEventListener('click', e => {
                e.stopPropagation();
                this.inject(btn.dataset.appid, btn.dataset.name);
            });
        });
        this.elements.sections.querySelectorAll('.rec-install').forEach(btn => {
            btn.addEventListener('click', e => {
                e.stopPropagation();
                this.install(btn.dataset.appid, btn.dataset.name);
            });
        });
        this.elements.sections.querySelectorAll('.rec-store').forEach(btn => {
            btn.addEventListener('click', e => {
                e.stopPropagation();
                window.open(`https://store.steampowered.com/app/${btn.dataset.appid}`, '_blank');
            });
        });
    }

    /* ---------- 登录态 ---------- */

    async isLoggedIn() {
        try {
            const r = await fetch('/api/steam/login/status');
            const d = await r.json();
            if (d.status === 'success' && d.account) return true;
        } catch (e) { /* ignore */ }
        try {
            const r = await fetch('/api/config/detailed');
            if (r.ok) {
                const d = await r.json();
                if (d.config && d.config.steam_cookie) return true;
            }
        } catch (e) { /* ignore */ }
        return false;
    }

    /** 拉起内置浏览器登录窗口，返回是否登录成功 */
    async browserLogin() {
        try {
            const resp = await fetch('/api/steam/login/start', { method: 'POST' });
            const d = await resp.json();
            if (!d.available) {
                this.showSnackbar('当前环境没有内置浏览器，请到「免费游戏」页手动粘贴 Cookie 登录。', 'warning');
                this.log('warn', '当前环境没有内置浏览器，无法弹出登录窗口。');
                return false;
            }
            this.showSnackbar('已打开登录窗口，请在窗口中完成 Steam 登录…', 'info');
            this.log('info', '已打开内置浏览器登录窗口，等待登录…');
            return await this.pollLogin();
        } catch (e) {
            this.showSnackbar(`打开登录窗口失败: ${e.message}`, 'error');
            this.log('error', `打开登录窗口失败：${e.message}`);
            return false;
        }
    }

    pollLogin() {
        return new Promise((resolve) => {
            clearInterval(this.pollTimer);
            const started = Date.now();
            this.pollTimer = setInterval(async () => {
                try {
                    const r = await fetch('/api/steam/login/status');
                    const d = await r.json();
                    if (d.status === 'success' && d.account) {
                        clearInterval(this.pollTimer);
                        this.showSnackbar(d.message || '已登录。', 'success');
                        this.log('success', `已登录：${d.account.name || 'Steam 账号'}`);
                        resolve(true);
                        return;
                    }
                    if (d.status === 'error') {
                        clearInterval(this.pollTimer);
                        this.showSnackbar(d.message || '登录失败。', 'error');
                        this.log('error', `登录失败：${d.message || ''}`);
                        resolve(false);
                        return;
                    }
                } catch (e) { /* 继续轮询 */ }
                if (Date.now() - started > 300000) {
                    clearInterval(this.pollTimer);
                    this.showSnackbar('等待登录超时。', 'warning');
                    this.log('warn', '等待登录超时。');
                    resolve(false);
                }
            }, 1500);
        });
    }

    /* ---------- 入库 / 安装 ---------- */

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

    async inject(appid, name) {
        if (this.busy) return;

        // 入库必须先登录：未登录则自动拉起登录窗口，登录成功后继续入库
        if (!(await this.isLoggedIn())) {
            this.showSnackbar('请先登录 Steam 账号，正在为你打开登录窗口…', 'warning');
            this.log('warn', '未登录，先打开 Steam 登录窗口…');
            const ok = await this.browserLogin();
            if (!ok) {
                this.showSnackbar('未登录，已取消入库。', 'warning');
                this.log('error', '登录未完成，已取消入库。');
                return;
            }
            this.log('success', '登录成功，继续入库。');
        }

        this.busy = true;
        this.showSnackbar(`正在入库 ${name || appid}...`, 'info');
        this.log('info', `开始入库 ${name || appid}（AppID ${appid}）…`);
        try {
            const resp = await fetch('/api/free/inject', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ appids: [appid], names: { [appid]: name || '' } })
            });
            const d = await resp.json();
            if (d.success) {
                const skipped = d.skipped ? '（已存在，跳过）' : '';
                const msg = `已入库 ${name || appid}${skipped}，重启 Steam 生效。`;
                this.showSnackbar(msg, 'success');
                this.log('success', msg);
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

document.addEventListener('DOMContentLoaded', () => { new RecommendApp(); });
