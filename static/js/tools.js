// --- 工具箱：Steam 错误诊断 / 一键修复 + 下载管理 ---
class ToolsApp {
    constructor() {
        this.elements = {
            diagBtn: document.getElementById('diagBtn'),
            fixAllBtn: document.getElementById('fixAllBtn'),
            diagSummary: document.getElementById('diagSummary'),
            diagFixBar: document.getElementById('diagFixBar'),
            diagList: document.getElementById('diagList'),
            dlRefreshBtn: document.getElementById('dlRefreshBtn'),
            dlOpenSteamBtn: document.getElementById('dlOpenSteamBtn'),
            dlActive: document.getElementById('dlActive'),
            dlDone: document.getElementById('dlDone'),
            dlDoneTitle: document.getElementById('dlDoneTitle'),
            log: document.getElementById('toolsLog'),
            logClear: document.getElementById('toolsLogClear'),
            snackbar: document.getElementById('snackbar'),
            snackbarMessage: document.getElementById('snackbarMessage'),
            snackbarClose: document.getElementById('snackbarClose'),
        };
        this.diag = null;
        this.store = window.DxbTaskLog ? window.DxbTaskLog.local('tools') : null;
        this.initialize();
    }

    log(type, msg) {
        if (this.store) this.store.append(type, msg);
    }

    initialize() {
        this.elements.diagBtn.addEventListener('click', () => this.diagnose());
        this.elements.fixAllBtn.addEventListener('click', () => this.repairAll());
        this.elements.dlRefreshBtn.addEventListener('click', () => this.loadDownloads());
        this.elements.dlOpenSteamBtn.addEventListener('click', () => this.openSteamDownloads());
        this.elements.snackbarClose.addEventListener('click', () => this.hideSnackbar());
        if (this.store) this.store.mount(this.elements.log);
        if (this.elements.logClear) this.elements.logClear.addEventListener('click', () => this.store && this.store.clear());
        this.diagnose();
        this.loadDownloads();
    }

    showSnackbar(msg, type = 'info') {
        const sb = this.elements.snackbar;
        this.elements.snackbarMessage.textContent = msg;
        sb.className = `snackbar show ${type}`;
        clearTimeout(this._snackTimer);
        this._snackTimer = setTimeout(() => this.hideSnackbar(), 4200);
    }

    hideSnackbar() {
        this.elements.snackbar.className = 'snackbar';
    }

    static fmtSize(n) {
        n = Number(n) || 0;
        const u = ['B', 'KB', 'MB', 'GB', 'TB'];
        let i = 0;
        while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
        return `${i === 0 ? Math.round(n) : n.toFixed(2)} ${u[i]}`;
    }

    /* ---------- 诊断 / 修复 ---------- */

    async diagnose(silent = false) {
        this.elements.diagBtn.disabled = true;
        this.elements.diagList.innerHTML = '<div class="empty-hint">正在体检，请稍候…</div>';
        if (!silent) this.log('info', '开始 Steam 环境体检…');
        try {
            const r = await fetch('/api/steam/diagnose');
            const d = await r.json();
            if (!d.success) throw new Error(d.message || '诊断失败');
            this.diag = d;
            this.renderDiag(d);
            this.log(d.issues || d.warnings ? 'warn' : 'success',
                `体检完成：${d.summary}${d.steam_path ? '（' + d.steam_path + '）' : ''}`);
        } catch (e) {
            this.elements.diagList.innerHTML = `<div class="empty-hint">诊断失败：${e.message}</div>`;
            this.log('error', `诊断失败：${e.message}`);
            this.showSnackbar(`诊断失败：${e.message}`, 'error');
        } finally {
            this.elements.diagBtn.disabled = false;
        }
    }

    renderDiag(d) {
        const chip = this.elements.diagSummary;
        const cls = d.issues ? 'bad' : (d.warnings ? 'warn' : '');
        chip.innerHTML = `<span class="summary-chip ${cls}">${d.summary}</span>`;

        this.elements.diagList.innerHTML = '';
        (d.checks || []).forEach(c => {
            const row = document.createElement('div');
            row.className = 'tool-row';
            const dot = document.createElement('span');
            dot.className = `status-dot dot-${c.level === 'ok' ? 'ok' : c.level === 'warn' ? 'warn' : c.level === 'error' ? 'error' : 'info'}`;
            const name = document.createElement('span');
            name.className = 'tool-name';
            name.textContent = c.name;
            const detail = document.createElement('span');
            detail.className = 'tool-detail';
            detail.textContent = c.detail;
            row.append(dot, name, detail);
            this.elements.diagList.appendChild(row);
        });

        const bar = this.elements.diagFixBar;
        bar.innerHTML = '';
        const fixes = d.fixes || [];
        this.elements.fixAllBtn.disabled = fixes.length === 0;
        if (!fixes.length) return;
        fixes.forEach(f => {
            const b = document.createElement('button');
            b.className = 'btn btn-secondary';
            b.title = f.desc || '';
            b.innerHTML = `<span class="material-icons">build</span> ${f.name}`;
            b.addEventListener('click', () => this.repair([f.id], f.name));
            bar.appendChild(b);
        });
        const hint = document.createElement('div');
        hint.className = 'empty-hint';
        hint.textContent = '建议先完全退出 Steam 再执行修复，修复后重启 Steam。';
        bar.appendChild(hint);
    }

    async repairAll() {
        const fixes = (this.diag && this.diag.fixes) || [];
        if (!fixes.length) { this.showSnackbar('当前没有需要修复的项目。', 'info'); return; }
        await this.repair(fixes.map(f => f.id), `全部 ${fixes.length} 项`);
    }

    async repair(actions, label) {
        if (!actions.length) return;
        this.log('info', `执行修复：${label}`);
        this.showSnackbar('正在执行修复…', 'info');
        try {
            const r = await fetch('/api/steam/repair', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ actions }),
            });
            const d = await r.json();
            (d.results || []).forEach(x => this.log(x.success ? 'success' : 'error',
                `${x.action}：${x.message}`));
            this.showSnackbar(d.message || '修复完成。', d.success ? 'success' : 'warning');
        } catch (e) {
            this.log('error', `修复失败：${e.message}`);
            this.showSnackbar(`修复失败：${e.message}`, 'error');
        }
        await this.diagnose(true);
        await this.loadDownloads();
    }

    /* ---------- 下载管理 ---------- */

    async loadDownloads(silent = false) {
        if (!silent) this.elements.dlActive.innerHTML = '<div class="empty-hint">正在加载下载列表…</div>';
        try {
            const r = await fetch('/api/steam/downloads');
            const d = await r.json();
            if (!d.success) throw new Error(d.message || '读取失败');
            this.renderDownloads(d);
            if (!silent) this.log('info', `下载列表已刷新：进行中 ${d.active_total} 个，共 ${d.total} 个条目。`);
        } catch (e) {
            this.elements.dlActive.innerHTML = `<div class="empty-hint">读取下载列表失败：${e.message}</div>`;
            this.log('error', `读取下载列表失败：${e.message}`);
        }
    }

    renderDownloads(d) {
        const active = d.active || [];
        const done = d.done || [];

        this.elements.dlActive.innerHTML = '';
        if (!active.length) {
            const h = document.createElement('div');
            h.className = 'empty-hint';
            h.textContent = '当前没有正在下载或更新的任务。在「免费游戏」或「推荐」页点“安装”即可发起下载。';
            this.elements.dlActive.appendChild(h);
        } else {
            const t = document.createElement('div');
            t.className = 'sec-title';
            t.textContent = `进行中（${active.length}）`;
            this.elements.dlActive.appendChild(t);
            active.forEach(it => this.elements.dlActive.appendChild(this.buildRow(it, true)));
        }

        this.elements.dlDone.innerHTML = '';
        this.elements.dlDoneTitle.style.display = done.length ? 'block' : 'none';
        done.forEach(it => this.elements.dlDone.appendChild(this.buildRow(it, false)));
    }

    buildRow(it, isActive) {
        const row = document.createElement('div');
        row.className = 'dl-item';

        const main = document.createElement('div');
        main.className = 'dl-main';

        const nm = document.createElement('div');
        nm.className = 'dl-name';
        nm.textContent = `${it.name}  (${it.appid})`;

        const meta = document.createElement('div');
        meta.className = 'dl-meta';
        const parts = [it.state_text];
        if (it.bytes_total > 0) {
            parts.push(`${ToolsApp.fmtSize(it.bytes_done)} / ${ToolsApp.fmtSize(it.bytes_total)}`);
            parts.push(`${it.percent}%`);
        } else if (it.size_on_disk > 0) {
            parts.push(ToolsApp.fmtSize(it.size_on_disk));
        }
        if (it.in_downloading) parts.push('有下载缓存');
        meta.textContent = parts.join('  ·  ');

        main.append(nm, meta);
        if (isActive) {
            const bar = document.createElement('div');
            bar.className = 'dl-progress';
            const i = document.createElement('i');
            i.style.width = `${Math.max(2, Math.min(100, it.percent || 0))}%`;
            bar.appendChild(i);
            main.appendChild(bar);
        }
        row.appendChild(main);

        const acts = document.createElement('div');
        acts.className = 'dl-actions';

        const openBtn = document.createElement('button');
        openBtn.className = 'btn btn-text';
        openBtn.innerHTML = '<span class="material-icons">open_in_new</span> Steam';
        openBtn.title = '在 Steam 客户端里查看 / 管理这个任务';
        openBtn.addEventListener('click', () => this.openSteamDownloads());
        acts.appendChild(openBtn);

        if (it.active || it.in_downloading) {
            const del = document.createElement('button');
            del.className = 'btn btn-text';
            del.innerHTML = '<span class="material-icons">delete_outline</span> 移除';
            del.title = '删掉这个下载任务（半成品缓存 + 清单，清单会先备份）';
            del.addEventListener('click', () => this.discard(it));
            acts.appendChild(del);
        }

        row.appendChild(acts);
        return row;
    }

    async discard(it) {
        const ok = window.confirm(
            `确定移除下载任务？\n\n${it.name} (${it.appid})\n\n` +
            `会删除该任务的半成品下载缓存和 appmanifest 清单（清单会备份到 userdata/download_backup）。\n` +
            `已安装的游戏文件不会被删除。\n\n` +
            `注意：如果 Steam 正在下这个任务，建议先在 Steam 下载页点取消，再回来清理。`);
        if (!ok) return;
        try {
            const r = await fetch('/api/steam/downloads/discard', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ appid: it.appid }),
            });
            const d = await r.json();
            this.showSnackbar(d.message || (d.success ? '已移除。' : '移除失败。'), d.success ? 'success' : 'error');
            this.log(d.success ? 'success' : 'error', `${it.name}：${d.message || ''}`);
        } catch (e) {
            this.showSnackbar(`移除失败：${e.message}`, 'error');
            this.log('error', `移除失败：${e.message}`);
        }
        await this.loadDownloads(true);
    }

    async openSteamDownloads() {
        try {
            const r = await fetch('/api/steam/launch', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action: 'open_downloads' }),
            });
            const d = await r.json();
            this.showSnackbar(d.message || '已打开 Steam 下载页。', d.success ? 'success' : 'error');
            this.log(d.success ? 'info' : 'error', d.message || '');
        } catch (e) {
            this.showSnackbar(`打开 Steam 失败：${e.message}`, 'error');
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    window.toolsApp = new ToolsApp();
});
