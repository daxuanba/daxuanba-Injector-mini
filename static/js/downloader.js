/* 下载管理：三个内核的真实版本检测 + 自动下载安装 + 启动/注入检测。
   进度走 HTTP 轮询（不依赖 socket.io CDN，CDN 在国内可能被墙）。 */
(function () {
    'use strict';

    const ICONS = {
        opensteamtool: 'menu_book',
        steamtools: 'extension',
        greenluma: 'bolt',
    };
    const LABEL = {
        none: '未安装',
        latest: '已是最新',
        update: '可更新',
        unknown: '版本未知',
    };
    const STATE_CLASS = {
        none: 'state-no',
        latest: 'state-ok',
        update: 'state-up',
        unknown: '',
    };

    let kernels = {};
    let order = [];
    let steamPath = '';
    let pollTimer = null;
    // GreenLuma 两种形态：stealth = 隐身版 user32.dll（默认，不怕 Steam 更新），inject = DLLInjector 注入版
    let glMode = 'stealth';
    try {
        const saved = localStorage.getItem('dxb-gl-mode');
        if (saved === 'stealth' || saved === 'inject') { glMode = saved; }
    } catch (e) { /* localStorage 不可用就用默认 */ }

    function $(id) { return document.getElementById(id); }

    function snackbar(msg, type) {
        const bar = $('snackbar');
        const txt = $('snackbarMessage');
        if (!bar || !txt) { return; }
        txt.textContent = msg || '';
        bar.classList.add('show');
        bar.classList.toggle('error', type === 'error');
        clearTimeout(snackbar._t);
        snackbar._t = setTimeout(() => bar.classList.remove('show'), 3800);
    }

    async function api(url, opts) {
        const r = await fetch(url, Object.assign({ headers: { 'Content-Type': 'application/json' } }, opts || {}));
        try { return await r.json(); } catch (e) { return { success: false, message: '响应解析失败' }; }
    }

    // ---------------------------------------------------------------- 渲染
    function esc(s) {
        return String(s == null ? '' : s).replace(/[&<>"']/g, c => (
            { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    }

    function verCmp(a, b) {
        const pa = String(a || '').replace(/^v/i, '').split('.');
        const pb = String(b || '').replace(/^v/i, '').split('.');
        const n = Math.max(pa.length, pb.length);
        for (let i = 0; i < n; i++) {
            const x = parseInt(pa[i], 10) || 0;
            const y = parseInt(pb[i], 10) || 0;
            if (x !== y) { return x > y ? 1 : -1; }
        }
        return 0;
    }

    // 本地/远端都有才敢下结论；缺一边就老实说「版本未知」，不瞎报「可更新」
    function stateOf(localVer, remoteVer, installed) {
        if (!installed) { return 'none'; }
        if (!localVer || !remoteVer) { return 'unknown'; }
        return verCmp(localVer, remoteVer) < 0 ? 'update' : 'latest';
    }

    function glPick(s, mode) {
        const st = (mode === 'stealth') ? (s.stealth || {}) : (s.inject || {});
        const remote = (mode === 'stealth') ? (s.remote_stealth || '') : (s.remote_inject || '');
        return { installed: !!st.installed, ver: st.version || '', remote: remote, raw: st };
    }

    function renderKernels() {
        const box = $('kernelList');
        if (!box) { return; }
        if (!order.length) { box.innerHTML = '<div class="empty-hint">没取到内核列表。</div>'; return; }
        box.innerHTML = order.map(k => {
            const s = kernels[k] || {};
            const isGL = (k === 'greenluma');
            let state, chips, files, btnText, extra = '';

            if (isGL) {
                const cur = glPick(s, glMode);
                const other = glPick(s, glMode === 'stealth' ? 'inject' : 'stealth');
                state = stateOf(cur.ver, cur.remote, cur.installed);
                chips = `<span class="vchip">当前形态：<b>${glMode === 'stealth' ? '隐身版' : '注入版'}</b></span>
                         <span class="vchip">本地：<b>${cur.installed ? esc(cur.ver || '已安装') : '未安装'}</b></span>
                         <span class="vchip">该形态最新：<b>${cur.remote ? esc(cur.remote) : '未取到'}</b></span>`;
                if (other.installed) {
                    chips += `<span class="vchip">另有${glMode === 'stealth' ? '注入版' : '隐身版'}：<b>${esc(other.ver || '已装')}</b></span>`;
                }
                if (cur.raw && cur.raw.loaded) {
                    chips += '<span class="vchip state-ok">已确认生效</span>';
                }
                if (s.applist) {
                    chips += `<span class="vchip">AppList：<b>${s.applist}</b> 个</span>`;
                }
                files = cur.raw && cur.raw.files && cur.raw.files.length ? cur.raw.files : (s.files || []);
                btnText = cur.installed ? (state === 'update' ? '更新' : '重新安装') : '下载并安装';
                extra = `
                    <div class="k-tip">隐身版（推荐）：把改写过的 user32.dll 放进 Steam 主目录，启动 Steam 时自己加载。
不需要注入器、不需要管理员、没有任何窗口，也不怕 Steam 更新。
注入版：DLLInjector.exe 往 steam.exe 挂钩子，同样全程无窗口，但对 Steam 版本敏感（Steam 一更新就可能失效）。</div>`;
            } else {
                state = s.update_state || 'none';
                chips = `<span class="vchip"${s.remote_note ? ` title="${esc(s.remote_note)}"` : ''}>本地：<b>${s.version ? esc(s.version) : (s.installed ? '已安装' : '—')}</b></span>
                         <span class="vchip">下载源最新：<b>${s.remote_version ? esc(s.remote_version) : (s.remote_ok ? '—' : '未取到')}</b></span>`;
                files = s.files || [];
                btnText = s.installed ? (state === 'update' ? '更新' : '重新安装') : '下载并安装';
            }

            const stateChip = `<span class="vchip ${STATE_CLASS[state] || ''}">${LABEL[state] || state}</span>`;
            const fileTip = (files && files.length)
                ? `<div class="k-msg">已就位：${esc(files.slice(0, 6).join('、'))}</div>` : '';
            const localBtn = (k === 'steamtools')
                ? `<button class="btn btn-text k-local" data-kind="${k}">
                       <span class="material-icons">upload_file</span> 用本地安装包
                   </button>
                   <input type="file" class="k-file" data-kind="${k}" accept=".zip,.7z" style="display:none">`
                : '';
            const modeSeg = isGL
                ? `<div class="mode-seg" data-kind="greenluma">
                       <button data-mode="stealth" class="${glMode === 'stealth' ? 'on' : ''}">隐身版</button>
                       <button data-mode="inject" class="${glMode === 'inject' ? 'on' : ''}">注入版</button>
                   </div>` : '';
            const removeBtn = (isGL && glMode === 'stealth' && (s.stealth || {}).installed)
                ? `<button class="btn btn-text k-remove-gl">
                       <span class="material-icons">undo</span> 移除隐身版
                   </button>` : '';
            return `
            <div class="k-card" data-kind="${k}">
                <div class="k-icon"><span class="material-icons">${ICONS[k] || 'download'}</span></div>
                <div class="k-body">
                    <div class="k-title">${esc(s.name || k)}
                        <span class="k-sub">${esc(s.short || '')}</span>${stateChip}
                    </div>
                    <div class="k-desc">${esc(s.desc || '')}</div>
                    <div class="k-vers">${chips}</div>
                    ${extra}
                    ${fileTip}
                    <div class="k-actions">
                        ${modeSeg}
                        <button class="btn btn-primary k-install" data-kind="${k}">
                            <span class="material-icons">download</span> ${btnText}
                        </button>
                        ${removeBtn}
                        ${localBtn}
                    </div>
                    <div class="k-progress" id="prog-${k}"><i></i></div>
                    <div class="k-msg" id="msg-${k}"></div>
                </div>
            </div>`;
        }).join('');

        box.querySelectorAll('.k-install').forEach(b => {
            b.addEventListener('click', () => install(b.dataset.kind));
        });
        box.querySelectorAll('.mode-seg button').forEach(b => {
            b.addEventListener('click', () => {
                glMode = b.dataset.mode;
                try { localStorage.setItem('dxb-gl-mode', glMode); } catch (e) { /* 忽略 */ }
                renderKernels();
            });
        });
        box.querySelectorAll('.k-remove-gl').forEach(b => {
            b.addEventListener('click', removeGreenLumaStealth);
        });
        box.querySelectorAll('.k-local').forEach(b => {
            b.addEventListener('click', () => {
                const inp = box.querySelector(`.k-file[data-kind="${b.dataset.kind}"]`);
                if (inp) { inp.click(); }
            });
        });
        box.querySelectorAll('.k-file').forEach(inp => {
            inp.addEventListener('change', () => {
                if (inp.files && inp.files[0]) { uploadLocal(inp.dataset.kind, inp.files[0]); }
                inp.value = '';
            });
        });
    }

    function setProgress(kind, pct, msg, show) {
        const bar = $(`prog-${kind}`);
        const m = $(`msg-${kind}`);
        if (bar) {
            bar.classList.toggle('show', show !== false);
            const i = bar.querySelector('i');
            if (i) { i.style.width = Math.max(0, Math.min(100, pct || 0)) + '%'; }
        }
        if (m && msg != null) { m.textContent = msg; }
    }

    // ---------------------------------------------------------------- 数据
    async function loadStatus(showToast) {
        const d = await api('/api/kernel/status');
        if (!d.success) {
            snackbar(d.message || '检测失败', 'error');
            return;
        }
        kernels = d.kernels || {};
        order = d.order || Object.keys(kernels);
        steamPath = d.steam_path || '';
        const chip = $('steamPathChip');
        if (chip) {
            chip.textContent = steamPath ? ('Steam：' + steamPath) : '未检测到 Steam 目录';
        }
        renderKernels();
        if (d.injection) { renderInjection(d.injection); }
        renderConflict(d.conflict);
        if (showToast) { snackbar('已重新检测', 'success'); }
    }

    function renderConflict(cf) {
        const box = $('conflictBox');
        if (!box) { return; }
        if (cf && cf.ok === false && cf.message) {
            box.innerHTML = '<div class="warn-box">内核冲突：' + esc(cf.message) + '</div>';
        } else {
            box.innerHTML = '';
        }
    }

    function renderInjection(st) {
        const el = $('injectMsg');
        if (!el) { return; }
        if (st.injected) {
            el.textContent = `已生效：Steam 正在运行，加载了 ${st.modules.join('、')}。`;
        } else if (st.steam_running) {
            el.textContent = 'Steam 在运行，但没检测到 GreenLuma（隐身版 / 注入版都没生效）。';
        } else {
            el.textContent = 'Steam 当前未运行。';
        }
    }

    // ---------------------------------------------------------------- 安装
    async function install(kind) {
        const body = { kind: kind, force: true };
        if (kind === 'greenluma') { body.mode = glMode; }
        setProgress(kind, 0, '正在准备...', true);
        const d = await api('/api/kernel/install', {
            method: 'POST', body: JSON.stringify(body)
        });
        if (!d.success) {
            setProgress(kind, 0, d.message || '发起失败', true);
            if (d.need_local) {
                const box = $('kernelList');
                const inp = box && box.querySelector(`.k-file[data-kind="${kind}"]`);
                if (inp) { inp.click(); }
            }
            snackbar(d.message || '发起失败', 'error');
            return;
        }
        snackbar(d.message || '已开始下载', 'success');
        startPolling(kind);
    }

    async function removeGreenLumaStealth() {
        if (!confirm('确定把 GreenLuma 隐身版（Steam 主目录里的 user32.dll）移除吗？\n\n'
                     + '如果之前已有同名文件会被自动还原。移除后重启 Steam 生效。')) {
            return;
        }
        const d = await api('/api/kernel/uninstall', {
            method: 'POST', body: JSON.stringify({ kind: 'greenluma', mode: 'stealth' })
        });
        snackbar(d.message || (d.success ? '已移除' : '移除失败'), d.success ? 'success' : 'error');
        await loadStatus(false);
        const el = $('injectMsg');
        if (el && d.message) { el.textContent = d.message; }
    }

    async function uploadLocal(kind, file) {
        const fd = new FormData();
        fd.append('kind', kind);
        fd.append('file', file, file.name);
        setProgress(kind, 0, '正在上传本地包...', true);
        try {
            const r = await fetch('/api/kernel/install_local', { method: 'POST', body: fd });
            const d = await r.json();
            if (!d.success) { snackbar(d.message || '上传失败', 'error'); return; }
            snackbar(d.message || '已开始安装', 'success');
            startPolling(kind);
        } catch (e) {
            snackbar('上传失败：' + e.message, 'error');
        }
    }

    function startPolling(kind) {
        stopPolling();
        let ticks = 0;
        pollTimer = setInterval(async () => {
            ticks += 1;
            const d = await api('/api/kernel/progress');
            const p = (d.progress || {})[kind];
            if (p) {
                setProgress(kind, p.percent, p.message, true);
                if (p.running === false) {
                    stopPolling();
                    await loadStatus(false);
                    setProgress(kind, p.percent, p.message, true);
                }
            } else if (ticks > 240) {
                stopPolling();
            }
        }, 900);
    }

    function stopPolling() {
        if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
    }

    // ---------------------------------------------------------------- 网络
    function dotClass(ok) { return ok ? 'dot-ok' : 'dot-bad'; }

    async function selftest() {
        const box = $('netResults');
        const btn = $('selftestBtn');
        if (box) { box.innerHTML = '<div class="net-row"><span class="dot dot-wait"></span><span class="net-info">正在实测直连...</span></div>'; }
        if (btn) { btn.disabled = true; }
        try {
            const d = await api('/api/net/selftest?mode=direct');
            if (!d.success) { snackbar(d.message || '测试失败', 'error'); return; }
            renderNet(d);
        } finally {
            if (btn) { btn.disabled = false; }
        }
    }

    function renderNet(d) {
        const box = $('netResults');
        if (!box) { return; }
        const rows = (d.results || []).map(r => `
            <div class="net-row">
                <span class="dot ${dotClass(r.ok)}"></span>
                <span class="net-name">${esc(r.name)}</span>
                <span class="net-info">${r.ok ? ('正常 · ' + r.ms + 'ms') : ('不通 · ' + esc(r.error || '失败'))}</span>
            </div>`).join('');
        const allOk = d.ok_count === d.total;
        const tip = allOk
            ? '<div class="hint-box" style="margin-top:10px;">直连全通，<b>不需要加速</b>。</div>'
            : `<div class="hint-box" style="margin-top:10px;">直连 ${d.ok_count}/${d.total} 通。
               不通的域名就是卡住你的地方（国内最常见是 Steam 社区 + 图片 CDN）。
               去「工具箱 → 网络加速」勾上对应分类，或填一个代理更彻底。</div>`;
        box.innerHTML = rows + tip;
    }

    async function loadProxy() {
        const d = await api('/api/net/proxy');
        if (d.success && $('proxyInput')) { $('proxyInput').value = d.proxy || ''; }
    }

    async function saveProxy() {
        const v = ($('proxyInput') && $('proxyInput').value || '').trim();
        const d = await api('/api/net/proxy', { method: 'POST', body: JSON.stringify({ proxy: v }) });
        snackbar(d.message || (d.success ? '已保存' : '保存失败'), d.success ? 'success' : 'error');
    }

    // ---------------------------------------------------------------- 启动
    async function launch(mode) {
        const el = $('injectMsg');
        const hints = {
            greenluma_stealth: '正在启动 Steam，并确认它是否加载了 Steam 目录下的 user32.dll（要盯十几秒）...',
            greenluma_inject: '正在用 DLLInjector.exe 无窗口注入启动 Steam（要盯十几秒，别关）...',
            normal: '正在启动 Steam...',
        };
        if (el) { el.textContent = hints[mode] || hints.normal; }
        let d;
        try {
            d = await api('/api/kernel/launch', { method: 'POST', body: JSON.stringify({ mode: mode }) });
        } catch (e) {
            if (el) { el.textContent = '请求失败：' + e.message; }
            snackbar('启动失败', 'error');
            return;
        }
        if (d.conflict) { renderConflict(d.conflict); }
        if (d.injection) { renderInjection(d.injection); }
        // 诊断信息（含 GreenLuma 日志失败行）优先展示，别被 renderInjection 覆盖掉
        if (el && d.message) { el.textContent = d.message; }
        snackbar(d.success ? '已启动' : '启动失败', d.success ? 'success' : 'error');
    }

    async function checkInjection() {
        const d = await api('/api/kernel/injection');
        if (!d.success) { snackbar(d.message || '检测失败', 'error'); return; }
        renderInjection(d);
        snackbar(d.injected ? '已注入' : (d.steam_running ? 'Steam 在跑但没注入' : 'Steam 未运行'),
                  d.injected ? 'success' : 'error');
    }

    // ---------------------------------------------------------------- 绑定
    document.addEventListener('DOMContentLoaded', () => {
        const refresh = $('refreshKernelsBtn');
        if (refresh) { refresh.addEventListener('click', () => loadStatus(true)); }
        const st = $('selftestBtn');
        if (st) { st.addEventListener('click', selftest); }
        const sp = $('saveProxyBtn');
        if (sp) { sp.addEventListener('click', saveProxy); }
        const ln = $('launchNormalBtn');
        if (ln) { ln.addEventListener('click', () => launch('normal')); }
        const lg = $('launchGlBtn');
        if (lg) { lg.addEventListener('click', () => launch('greenluma_stealth')); }
        const gli = $('launchGlInjectBtn');
        if (gli) { gli.addEventListener('click', () => launch('greenluma_inject')); }
        const ci = $('checkInjectionBtn');
        if (ci) { ci.addEventListener('click', checkInjection); }
        const sc = $('snackbarClose');
        if (sc) { sc.addEventListener('click', () => $('snackbar').classList.remove('show')); }

        loadProxy();
        loadStatus(false);
        setInterval(() => { api('/api/kernel/injection').then(d => { if (d.success) { renderInjection(d); } }); }, 20000);
    });
})();
