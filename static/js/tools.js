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
            accelScanBtn: document.getElementById('accelScanBtn'),
            accelApplyBtn: document.getElementById('accelApplyBtn'),
            accelRestoreBtn: document.getElementById('accelRestoreBtn'),
            accelSummary: document.getElementById('accelSummary'),
            accelAdminBar: document.getElementById('accelAdminBar'),
            accelList: document.getElementById('accelList'),
            log: document.getElementById('toolsLog'),
            logClear: document.getElementById('toolsLogClear'),
            snackbar: document.getElementById('snackbar'),
            snackbarMessage: document.getElementById('snackbarMessage'),
            snackbarClose: document.getElementById('snackbarClose'),
        };
        this.diag = null;
        this.accel = null;        // 最近一次测速结果
        this.accelStatus = null;  // hosts 加速块状态
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
        this.elements.accelScanBtn.addEventListener('click', () => this.accelScan());
        this.elements.accelApplyBtn.addEventListener('click', () => this.accelApply());
        this.elements.accelRestoreBtn.addEventListener('click', () => this.accelRestore());
        if (this.store) this.store.mount(this.elements.log);
        if (this.elements.logClear) this.elements.logClear.addEventListener('click', () => this.store && this.store.clear());
        this.loadAccelStatus();
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

    /* ---------- Steam 加速（hosts 优选） ---------- */

    static latClass(ms) {
        if (ms == null) return 'bad';
        if (ms <= 80) return 'good';
        if (ms <= 200) return 'mid';
        return 'bad';
    }

    async loadAccelStatus() {
        try {
            const r = await fetch('/api/steam/accel/status');
            const d = await r.json();
            if (!d.success) throw new Error(d.message || '读取失败');
            this.accelStatus = d;
            this.renderAccelSummary(d);
        } catch (e) {
            this.elements.accelSummary.innerHTML = '<span class="summary-chip bad">加速状态读取失败</span>';
        }
    }

    renderAccelSummary(s) {
        this.elements.accelSummary.innerHTML =
            `<span class="summary-chip ${s.enabled ? '' : 'warn'}">` +
            `${s.enabled ? `加速已开启（${s.count} 个域名）` : '加速未开启'}</span>`;

        const bar = this.elements.accelAdminBar;
        bar.innerHTML = '';

        // 本机已有本地反代型加速器（Steam 社区 302 / Steam++ / Watt Toolkit）时会互相覆盖
        const la = s.local_accel;
        if (la && la.active) {
            const w = document.createElement('div');
            w.className = 'accel-warn';
            const ic = document.createElement('span');
            ic.className = 'material-icons';
            ic.textContent = 'report_problem';
            const tx = document.createElement('span');
            const who = `${la.process || '本地加速器'}${la.pid ? `（PID ${la.pid}）` : ''}`;
            tx.textContent =
                `检测到 ${who} 正在接管 Steam 域名（${(la.domains || []).length} 个解析到 127.0.0.1）。` +
                '它和这里的 hosts 优选是互相覆盖的两套方案，建议二选一：' +
                '要么关掉它、用本工具；要么继续用它、不要开这里的加速。';
            w.append(ic, tx);
            bar.appendChild(w);
        }

        if (!s.writable) {
            const w = document.createElement('div');
            w.className = 'accel-warn';
            const ic = document.createElement('span');
            ic.className = 'material-icons';
            ic.textContent = 'admin_panel_settings';
            const tx = document.createElement('span');
            tx.textContent = '写 hosts 需要管理员权限，当前不是管理员，加速 / 还原会失败。';
            const b = document.createElement('button');
            b.className = 'btn btn-primary';
            b.innerHTML = '<span class="material-icons">rocket_launch</span> 以管理员身份重启';
            b.addEventListener('click', () => this.restartElevated());
            w.append(ic, tx, b);
            bar.appendChild(w);
        }
    }

    async accelScan() {
        this.elements.accelScanBtn.disabled = true;
        this.elements.accelList.innerHTML =
            '<div class="empty-hint">正在并发解析 + 实测各域名候选 IP，大约 5~15 秒…</div>';
        this.log('info', '开始测速选优：多源 DoH 解析 + TCP/TLS/HTTP 三段实测…');
        try {
            const r = await fetch('/api/steam/accel/scan', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({}),
            });
            const d = await r.json();
            if (!d.success) throw new Error(d.message || '测速失败');
            this.accel = d;
            this.renderAccelScan(d);
            const total = (d.domains || []).length;
            const ok = (d.domains || []).filter(x => x.best).length;
            this.log(ok ? 'success' : 'warn', `测速完成：${ok}/${total} 个域名找到可用 IP。`);
        } catch (e) {
            this.elements.accelList.innerHTML = `<div class="empty-hint">测速失败：${e.message}</div>`;
            this.log('error', `测速失败：${e.message}`);
            this.showSnackbar(`测速失败：${e.message}`, 'error');
        } finally {
            this.elements.accelScanBtn.disabled = false;
        }
    }

    renderAccelScan(d) {
        const list = this.elements.accelList;
        const applied = d.applied || {};
        list.innerHTML = '';
        (d.domains || []).forEach(row => {
            const el = document.createElement('div');
            el.className = 'accel-row';

            const cb = document.createElement('input');
            cb.type = 'checkbox';
            cb.disabled = !row.best;
            cb.checked = !!row.best;
            cb.dataset.domain = row.domain;
            if (row.best) cb.dataset.ip = row.best.ip;
            el.appendChild(cb);

            const dom = document.createElement('span');
            dom.className = 'accel-domain';
            dom.textContent = row.domain;
            el.appendChild(dom);

            const grp = document.createElement('span');
            grp.className = 'accel-group';
            grp.textContent = row.group;
            el.appendChild(grp);

            if (row.best) {
                const ip = document.createElement('span');
                ip.className = 'accel-ip';
                ip.textContent = row.best.ip;
                const lat = document.createElement('span');
                lat.className = `accel-lat ${ToolsApp.latClass(row.best.total_ms)}`;
                lat.textContent = `${Math.round(row.best.total_ms)} ms`;
                el.append(ip, lat);
            } else {
                const bad = document.createElement('span');
                bad.className = 'accel-lat bad';
                bad.textContent = row.poisoned ? '解析被污染' : '无可用 IP';
                el.appendChild(bad);
            }

            const meta = document.createElement('span');
            meta.className = 'accel-meta';
            const cands = row.candidates || [];
            const okN = cands.filter(c => c.ok).length;
            const bits = [`候选 ${cands.length} 个 / 可用 ${okN} 个`];
            if (row.reason) bits.push(row.reason);
            bits.push(applied[row.domain] ? `当前 hosts：${applied[row.domain]}` : '当前 hosts：未加速');
            meta.textContent = bits.join('  ·  ');
            el.appendChild(meta);

            list.appendChild(el);
        });
    }

    async accelApply() {
        const entries = [];
        this.elements.accelList.querySelectorAll('input[type=checkbox]').forEach(cb => {
            if (cb.checked && cb.dataset.ip) entries.push({ domain: cb.dataset.domain, ip: cb.dataset.ip });
        });
        if (!entries.length) {
            this.showSnackbar('没有可加速的条目，请先「测速选优」。', 'warning');
            return;
        }
        const la = (this.accelStatus && this.accelStatus.local_accel) ||
                   (this.accel && this.accel.local_accel);
        if (la && la.active) {
            const who = `${la.process || '本地加速器'}${la.pid ? `（PID ${la.pid}）` : ''}`;
            if (!window.confirm(`检测到 ${who} 正在接管 Steam 域名。\n\n` +
                `写 hosts 会覆盖它的效果（两套方案互相冲突）。\n\n` +
                `建议先关掉它再加速。确定仍要继续？`)) return;
        }
        this.elements.accelApplyBtn.disabled = true;
        this.log('info', `写入加速：${entries.length} 个域名…`);
        try {
            const r = await fetch('/api/steam/accel/apply', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ entries }),
            });
            const d = await r.json();
            this.log(d.success ? 'success' : 'error', d.message || '');
            this.showSnackbar(d.message || (d.success ? '加速已开启。' : '加速失败。'),
                d.success ? 'success' : 'error');
        } catch (e) {
            this.log('error', `写入加速失败：${e.message}`);
            this.showSnackbar(`写入加速失败：${e.message}`, 'error');
        } finally {
            this.elements.accelApplyBtn.disabled = false;
        }
        await this.loadAccelStatus();
        await this.refreshAccelRows();
    }

    async accelRestore() {
        if (!window.confirm('移除 hosts 里的「大轩巴 Steam 加速」记录？\n\n会先自动备份 hosts，随时可以再加速回来。')) return;
        this.elements.accelRestoreBtn.disabled = true;
        try {
            const r = await fetch('/api/steam/accel/restore', { method: 'POST' });
            const d = await r.json();
            this.log(d.success ? 'success' : 'error', d.message || '');
            this.showSnackbar(d.message || (d.success ? '已还原。' : '还原失败。'),
                d.success ? 'success' : 'error');
        } catch (e) {
            this.log('error', `还原失败：${e.message}`);
            this.showSnackbar(`还原失败：${e.message}`, 'error');
        } finally {
            this.elements.accelRestoreBtn.disabled = false;
        }
        await this.loadAccelStatus();
        await this.refreshAccelRows();
    }

    async refreshAccelRows() {
        if (!this.accel) return;
        try {
            const r = await fetch('/api/steam/accel/status');
            const d = await r.json();
            if (d.success) {
                this.accel.applied = d.applied;
                this.renderAccelScan(this.accel);
            }
        } catch (e) { /* 忽略 */ }
    }

    async restartElevated() {
        if (!window.confirm('将以管理员身份重启本程序（会弹出 UAC 授权窗口）。\n\n' +
            '当前窗口会关闭，请在新窗口里重新点「一键加速」。\n\n继续？')) return;
        this.log('info', '请求以管理员身份重启…');
        try {
            const r = await fetch('/api/app/restart_elevated', { method: 'POST' });
            const d = await r.json();
            this.showSnackbar(d.message || '', d.success ? 'info' : 'warning');
            this.log(d.success ? 'info' : 'warn', d.message || '');
        } catch (e) {
            // 程序正在退出，连接被中断属正常现象
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    window.toolsApp = new ToolsApp();
});
