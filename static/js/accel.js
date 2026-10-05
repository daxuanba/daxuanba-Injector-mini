/* 大轩巴入库器mini · 加速页 */
(function () {
    'use strict';

    var $ = function (id) { return document.getElementById(id); };

    function api(path, method, body) {
        return fetch(path, {
            method: method || 'GET',
            headers: body ? {'Content-Type': 'application/json'} : {},
            body: body ? JSON.stringify(body) : null
        }).then(function (r) { return r.json(); }).catch(function (e) {
            return {success: false, message: '请求失败：' + e};
        });
    }

    function msg(elId, text, ok) {
        var el = $(elId);
        if (!el) return;
        el.textContent = text || '';
        el.style.color = ok === false ? '#ff6b6b' : (ok ? '#4ade80' : '');
    }

    function setBusy(btn, busy, text) {
        if (!btn) return;
        btn.disabled = !!busy;
        if (btn.querySelector('.material-icons')) {
            btn.querySelector('.material-icons').textContent = busy ? 'hourglass_empty' : (text || btn.textContent.trim().replace(/^\S+\s*/, ''));
        }
    }

    function refresh() {
        return api('/api/accel/status').then(function (r) {
            if (!r || !r.success) return;
            var running = !!r.running;
            var dot = $('accelDot'), title = $('accelTitle'), sub = $('accelSub');
            if (dot) dot.className = 'accel-dot' + (running ? ' on' : '');
            if (title) title.textContent = running ? '加速中' : '未启动';
            if (sub) {
                var bits = [];
                if (r.sub && r.sub.nodes) bits.push('已载入 ' + r.sub.nodes + ' 个节点');
                else bits.push('尚未配置订阅');
                if (r.system_proxy && r.system_proxy.enabled) bits.push('系统代理已开');
                sub.textContent = bits.join(' · ');
            }
            if ($('accelStartBtn')) $('accelStartBtn').style.display = running ? 'none' : '';
            if ($('accelStopBtn')) $('accelStopBtn').style.display = running ? '' : 'none';
            if (running) loadNodes();
            return r;
        });
    }

    function loadNodes() {
        return api('/api/accel/nodes').then(function (r) {
            var box = $('accelNodes');
            if (!box) return;
            if (!r || !r.ok || !r.nodes) {
                box.innerHTML = '<div class="accel-empty">' +
                    ((r && r.message) ? r.message : '暂没有节点') + '</div>';
                return;
            }
            box.innerHTML = r.nodes.map(function (n) {
                return '<button class="accel-node' + (n.name === r.current ? ' active' : '') +
                    '" data-name="' + String(n.name).replace(/"/g, '&quot;') + '">' +
                    '<span class="material-icons">public</span>' +
                    '<span class="accel-node-name">' + n.name + '</span>' +
                    (n.now ? '<span class="accel-node-now">' + n.now + '</span>' : '') +
                    '</button>';
            }).join('');
            var btns = box.querySelectorAll('.accel-node');
            for (var i = 0; i < btns.length; i++) {
                btns[i].addEventListener('click', function () {
                    api('/api/accel/select', 'POST', {name: this.getAttribute('data-name')})
                        .then(function (x) { msg('accelMsg', (x && x.message) || '已切换', !!(x && x.ok)); refresh(); });
                });
            }
        });
    }

    function bind(id, handler) {
        var el = $(id);
        if (el) el.addEventListener('click', handler);
    }

    document.addEventListener('DOMContentLoaded', function () {
        refresh();

        bind('accelStartBtn', function () {
            setBusy(this, true);
            msg('accelMsg', '正在启动…');
            api('/api/accel/start', 'POST').then(function (r) {
                msg('accelMsg', (r && r.message) || '已启动', !!(r && r.ok));
                setBusy(document.getElementById('accelStartBtn'), false);
                refresh();
            });
        });

        bind('accelStopBtn', function () {
            api('/api/accel/stop', 'POST').then(function (r) {
                msg('accelMsg', (r && r.message) || '已停止', !!(r && r.ok));
                refresh();
            });
        });

        bind('accelEnsureBtn', function () {
            var b = this; b.disabled = true;
            msg('accelMsg', '正在下载加速内核（约 60MB）…');
            api('/api/accel/ensure', 'POST').then(function (r) {
                msg('accelMsg', (r && r.message) || '内核已就绪', !!(r && r.ok));
                b.disabled = false; refresh();
            });
        });

        bind('accelSubBtn', function () {
            var url = ($('accelSubInput') || {}).value || '';
            if (!url.trim()) { msg('accelSubMsg', '先粘贴订阅链接', false); return; }
            msg('accelSubMsg', '正在拉取订阅…');
            api('/api/accel/sub', 'POST', {url: url}).then(function (r) {
                var m = (r && r.message) || '';
                if (r && r.ok) m += '（' + (r.nodes || 0) + ' 个节点）';
                msg('accelSubMsg', m, !!(r && r.ok));
                if (r && r.ok) refresh();
            });
        });

        bind('accelDelayBtn', function () {
            msg('accelMsg', '正在测延迟…');
            api('/api/accel/delay', 'POST').then(function (r) {
                if (!r || !r.ok) { msg('accelMsg', (r && r.message) || '测延迟失败', false); return; }
                var best = (r.nodes || []).slice(0, 5).map(function (n) {
                    return n.name + ' ' + n.delay + 'ms';
                }).join('\n');
                msg('accelMsg', best ? ('最快：\n' + best) : '全部超时', true);
            });
        });

        bind('accelSysOnBtn', function () {
            api('/api/accel/sysproxy', 'POST', {enable: true}).then(function (r) {
                msg('accelSysMsg', (r && r.message) || '系统代理已开', !!(r && r.ok));
                refresh();
            });
        });

        bind('accelSysOffBtn', function () {
            api('/api/accel/sysproxy', 'POST', {enable: false}).then(function (r) {
                msg('accelSysMsg', (r && r.message) || '系统代理已关', !!(r && r.ok));
                refresh();
            });
        });

        bind('accelDlBtn', function () {
            var b = this; b.disabled = true;
            msg('accelDlMsg', '正在打包（含主程序 + 加速内核，约 100MB）…');
            fetch('/api/installer').then(function (r) {
                if (!r.ok) {
                    r.json().then(function (j) {
                        msg('accelDlMsg', (j && j.message) || '打包失败', false);
                        b.disabled = false;
                    });
                    return;
                }
                return r.blob().then(function (blob) {
                    var a = document.createElement('a');
                    a.href = URL.createObjectURL(blob);
                    a.download = '大轩巴入库器mini-完整包.zip';
                    document.body.appendChild(a); a.click();
                    document.body.removeChild(a);
                    setTimeout(function () { URL.revokeObjectURL(a.href); }, 30000);
                    msg('accelDlMsg', '完整包已生成，请查看浏览器下载列表', true);
                    b.disabled = false;
                });
            });
        });
    });
})();
