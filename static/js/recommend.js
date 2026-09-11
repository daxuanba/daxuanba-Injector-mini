// --- 游戏推荐页：特惠 / 热销 / 新品 / 即将推出 ---
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
        };
        this.elements.refreshBtn.addEventListener('click', () => this.load());
        this.elements.snackbarClose.addEventListener('click', () => this.hideSnackbar());
        this.load();
    }

    fmtPrice(cents, currency) {
        if (cents === null || cents === undefined) return '';
        if (cents === 0) return '免费';
        return `¥${(cents / 100).toFixed(2)}`;
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
                        <img src="/api/steam/img/${g.appid}" alt="${g.name}" loading="lazy" referrerpolicy="no-referrer">
                    </div>
                    <div class="game-card-body">
                        <span class="game-title" title="${g.name}">${g.name}</span>
                        <span class="game-appid">APPID: ${g.appid}</span>
                        <div class="rec-price-row">${off}${price}${oldPrice}</div>
                        <div class="game-card-actions">
                            <button class="btn btn-primary rec-inject" data-appid="${g.appid}" data-name="${g.name}">
                                <span class="material-icons">library_add</span> 入库
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
        this.elements.sections.querySelectorAll('.rec-store').forEach(btn => {
            btn.addEventListener('click', e => {
                e.stopPropagation();
                window.open(`https://store.steampowered.com/app/${btn.dataset.appid}`, '_blank');
            });
        });
    }

    async inject(appid, name) {
        this.showSnackbar(`正在入库 ${name || appid}...`, 'info');
        try {
            const resp = await fetch('/api/free/inject', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ appids: [appid], names: { [appid]: name || '' } })
            });
            const d = await resp.json();
            if (d.success) {
                const skipped = d.skipped ? '（已存在，跳过）' : '';
                this.showSnackbar(`已入库 ${name || appid}${skipped}，重启 Steam 生效。`, 'success');
            } else {
                this.showSnackbar(d.message || '入库失败', 'error');
            }
        } catch (e) {
            this.showSnackbar(`入库失败: ${e.message}`, 'error');
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
