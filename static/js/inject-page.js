(function () {
    'use strict';

    function $(id) { return document.getElementById(id); }

    function esc(s) {
        return String(s == null ? '' : s).replace(/[&<>"']/g, c => (
            { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    }

    function snackbar(msg, type) {
        const bar = $('snackbar'); const txt = $('snackbarMessage');
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

    function renderConflict(cf) {
        const box = $('conflictBox');
        if (!box) { return; }
        box.innerHTML = (cf && cf.ok === false && cf.message)
            ? '<div class="warn-box">内核冲突：' + esc(cf.message) + '</div>' : '';
    }

    function renderInjection(st) {
        const el = $('injectMsg');
        if (!el || !st) { return; }
        if (st.injected) {
            el.textContent = `已生效：Steam 正在运行，加载了 ${(st.modules || []).join('、')}。`;
        } else if (st.steam_running) {
            el.textContent = 'Steam 在运行，但没检测到 GreenLuma（隐身版 / 注入版都没生效）。';
        } else {
            el.textContent = 'Steam 当前未运行。下面点「启动」后再回来看。';
        }
        renderModules(st.module_details || [], st.steam_path || '');
    }

    function renderModules(list, steamPath) {
        const table = $('modTable');
        if (!table) { return; }
        if (!list.length) { table.style.display = 'none'; return; }
        table.style.display = '';
        const tb = table.querySelector('tbody');
        const root = String(steamPath || '').toLowerCase().replace(/[\\/]+$/, '');
        tb.innerHTML = list.map(m => {
            const p = String(m.path || '');
            const fromSteam = !!m.from_steam
                || (root && p.toLowerCase().startsWith(root + '\\') && p.toLowerCase().endsWith('user32.dll'));
            return `<tr>
                <td>${esc(m.module)}</td>
                <td>${esc(p)}</td>
                <td><span class="tag ${fromSteam ? 'tag-dxb' : 'tag-sys'}">${fromSteam ? '本程序' : '系统'}</span></td>
            </tr>`;
        }).join('');
    }

    async function launch(mode) {
        const el = $('launchMsg');
        const hints = {
            greenluma_stealth: '正在启动 Steam，并确认它是否加载了 Steam 目录下的 user32.dll（要盯十几秒）...',
            greenluma_inject: '正在用 DLLInjector.exe 无窗口注入启动 Steam（要盯十几秒，别关）...',
            normal: '正在启动 Steam...',
        };
        if (el) { el.textContent = hints[mode] || hints.normal; }
        const d = await api('/api/kernel/launch', { method: 'POST', body: JSON.stringify({ mode }) });
        if (d.conflict) { renderConflict(d.conflict); }
        if (d.injection) { renderInjection(d.injection); }
        if (el && d.message) { el.textContent = d.message; }
        snackbar(d.success ? '已启动' : '启动失败', d.success ? 'success' : 'error');
    }

    async function checkInjection(showToast) {
        const d = await api('/api/kernel/injection');
        if (!d.success) { snackbar(d.message || '检测失败', 'error'); return; }
        renderInjection(d);
        if (showToast) {
            snackbar(d.injected ? '已生效' : (d.steam_running ? 'Steam 在跑但没生效' : 'Steam 未运行'),
                     d.injected ? 'success' : 'error');
        }
    }

    document.addEventListener('DOMContentLoaded', () => {
        const ln = $('launchNormalBtn'); if (ln) { ln.addEventListener('click', () => launch('normal')); }
        const lg = $('launchGlBtn'); if (lg) { lg.addEventListener('click', () => launch('greenluma_stealth')); }
        const gi = $('launchGlInjectBtn'); if (gi) { gi.addEventListener('click', () => launch('greenluma_inject')); }
        const ci = $('checkInjectionBtn'); if (ci) { ci.addEventListener('click', () => checkInjection(true)); }
        const sc = $('snackbarClose'); if (sc) { sc.addEventListener('click', () => $('snackbar').classList.remove('show')); }

        api('/api/kernel/status').then(d => { if (d.success) { renderConflict(d.conflict); } });
        checkInjection(false);
        setInterval(() => { checkInjection(false); }, 20000);
    });
})();
