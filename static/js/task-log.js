// --- 任务日志跨页持久化 ---
// 任务在后端进程里跑，切换页面（整页跳转）不该丢掉日志与状态。
//   * 服务端 /api/task_status 保存了完整的 progress 缓冲 → 权威数据源
//   * localStorage 存一份快照 → 回到页面时立刻有内容，不用等网络
//   * socket 只作为“有新日志了”的触发器，内容始终从服务端同步 → 不会重复
(function () {
    const LS_KEY = 'dxb_task_log_v1';
    const LS_STATUS = 'dxb_task_status_v1';
    const MAX_LOCAL = 400;

    const state = {
        container: null,
        serverCount: 0,     // 已经从服务端渲染过的条数
        localCount: 0,      // 本地追加过（不来自服务端）的条数
        status: 'idle',
        result: null,
        timer: null,
        syncing: false,
        pending: false,
        onStatus: null,
        mounted: false,
    };

    function placeholderHTML() {
        return '<div class="progress-placeholder"><span class="material-icons">info</span><p>等待任务开始...</p></div>';
    }

    function box() {
        return state.container || document.getElementById('progressContainer');
    }

    function makeNode(type, message) {
        const div = document.createElement('div');
        div.className = `log-entry ${type || 'info'}`;
        div.textContent = `[${new Date().toLocaleTimeString()}] ${message}`;
        return div;
    }

    function clearPlaceholder(el) {
        const ph = el.querySelector('.progress-placeholder');
        if (ph) el.innerHTML = '';
    }

    function appendNode(type, message, scroll = true) {
        const el = box();
        if (!el) return;
        clearPlaceholder(el);
        el.appendChild(makeNode(type, message));
        if (scroll) el.scrollTop = el.scrollHeight;
    }

    function saveLocal(entries) {
        try {
            localStorage.setItem(LS_KEY, JSON.stringify(entries.slice(-MAX_LOCAL)));
        } catch (e) { /* ignore */ }
    }

    function loadLocal() {
        try {
            const raw = localStorage.getItem(LS_KEY);
            const arr = raw ? JSON.parse(raw) : [];
            return Array.isArray(arr) ? arr : [];
        } catch (e) { return []; }
    }

    /** 用快照立即铺满日志（无网络延迟） */
    function renderSnapshot() {
        const el = box();
        if (!el) return;
        const entries = loadLocal().filter(e => e && e.message);
        const status = (function () {
            try { return localStorage.getItem(LS_STATUS) || 'idle'; } catch (e) { return 'idle'; }
        })();
        if (!entries.length) {
            if (status !== 'running') el.innerHTML = placeholderHTML();
            return;
        }
        el.innerHTML = '';
        entries.forEach(e => el.appendChild(makeNode(e.type, e.message)));
        el.scrollTop = el.scrollHeight;
        state.serverCount = entries.length;
        state.status = status;
    }

    /** 从服务端拉权威日志，只追加新增部分 */
    async function sync() {
        if (state.syncing) { state.pending = true; return; }
        const el = box();
        if (!el) return;
        state.syncing = true;
        try {
            const r = await fetch('/api/task_status');
            const d = await r.json();
            const list = Array.isArray(d.progress) ? d.progress : [];
            // 服务端缓冲比已渲染的少 → 说明开始了新任务或服务重开，整体重置
            if (list.length < state.serverCount) {
                el.innerHTML = '';
                state.serverCount = 0;
                if (!list.length) el.innerHTML = placeholderHTML();
            }
            for (let i = state.serverCount; i < list.length; i++) {
                appendNode(list[i].type, list[i].message);
            }
            state.serverCount = list.length;
            state.result = d.result;
            const changed = state.status !== d.status;
            state.status = d.status;
            saveLocal(list);
            try { localStorage.setItem(LS_STATUS, d.status); } catch (e) { /* ignore */ }
            if (changed && typeof state.onStatus === 'function') state.onStatus(d.status, d.result);
            if (typeof state.onStatus === 'function') state.onStatus(d.status, d.result, changed);
        } catch (e) { /* 网络抖动忽略 */ }
        finally {
            state.syncing = false;
            if (state.pending) { state.pending = false; sync(); }
        }
    }

    /** socket 收到新日志 → 稍后同步（合并抖动） */
    function triggerSync(delay = 200) {
        clearTimeout(state._t);
        state._t = setTimeout(sync, delay);
    }

    function startPolling(interval = 1500) {
        clearInterval(state.timer);
        state.timer = setInterval(sync, interval);
    }

    function stopPolling() {
        clearInterval(state.timer);
        state.timer = null;
    }

    const DxbTaskLog = {
        state,
        mount(container, onStatus) {
            state.container = container || document.getElementById('progressContainer');
            state.onStatus = typeof onStatus === 'function' ? onStatus : null;
            state.mounted = true;
            renderSnapshot();
            sync();
            startPolling(1600);
        },
        /** 页面本地产生的日志（不来自服务端）；同时写快照，切页回来还在 */
        appendLocal(type, message) {
            appendNode(type, message);
            const entries = loadLocal();
            entries.push({ type: type || 'info', message });
            saveLocal(entries);
            state.localCount++;
        },
        /** 清空（新任务开始时调用） */
        clear() {
            state.serverCount = 0;
            state.localCount = 0;
            try { localStorage.removeItem(LS_KEY); localStorage.setItem(LS_STATUS, 'idle'); } catch (e) { /* ignore */ }
            const el = box();
            if (el) el.innerHTML = placeholderHTML();
        },
        triggerSync,
        sync,
        startPolling,
        stopPolling,
        get active() { return state.status === 'running'; },

        /** 纯本地日志（不走服务端任务缓冲，例如“手搓”页），同样写快照，切页回来不丢 */
        local(namespace) {
            const key = `dxb_local_log_${namespace}`;
            let el = null;
            const read = () => {
                try {
                    const arr = JSON.parse(localStorage.getItem(key) || '[]');
                    return Array.isArray(arr) ? arr : [];
                } catch (e) { return []; }
            };
            const write = (arr) => {
                try { localStorage.setItem(key, JSON.stringify(arr.slice(-MAX_LOCAL))); } catch (e) { /* ignore */ }
            };
            return {
                mount(container) {
                    el = container || document.getElementById('progressContainer');
                    if (!el) return;
                    const arr = read();
                    if (!arr.length) { el.innerHTML = placeholderHTML(); return; }
                    el.innerHTML = '';
                    arr.forEach(e => el.appendChild(makeNode(e.type, e.message)));
                    el.scrollTop = el.scrollHeight;
                },
                append(type, message) {
                    if (!el) el = document.getElementById('progressContainer');
                    if (!el) return;
                    clearPlaceholder(el);
                    el.appendChild(makeNode(type, message));
                    el.scrollTop = el.scrollHeight;
                    const arr = read();
                    arr.push({ type: type || 'info', message });
                    write(arr);
                },
                clear() {
                    if (!el) el = document.getElementById('progressContainer');
                    write([]);
                    if (el) el.innerHTML = placeholderHTML();
                },
            };
        },
    };

    window.DxbTaskLog = DxbTaskLog;
})();
