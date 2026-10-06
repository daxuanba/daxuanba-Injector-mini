/* 大轩巴入库器mini · 加速页 */
(function () {
    'use strict';

    var $ = function (id) { return document.getElementById(id); };

    function api(path, method, body, ms) {
        /* v2.33：页面初始化里的请求一律带硬超时。
           以前加速页一进来就 refresh()，接口一慢整页停在旧帧（用户看到「卡死」），
           而且慢请求还会占着后端线程，连点其它按钮都没反应。 */
        var timeout = ms || 12000;
        var ctrl = (typeof AbortController !== 'undefined') ? new AbortController() : null;
        var timer = ctrl ? setTimeout(function () { try { ctrl.abort(); } catch (e) { } }, timeout) : null;
        var opt = {
            method: method || 'GET',
            headers: body ? {'Content-Type': 'application/json'} : {}
        };
        if (body) opt.body = JSON.stringify(body);
        if (ctrl) opt.signal = ctrl.signal;
        return Promise.race([
            fetch(path, opt).then(function (r) { return r.json(); }),
            new Promise(function (_, rej) {
                setTimeout(function () { rej(new Error('超时（' + (timeout / 1000 | 0) + ' 秒）')); }, timeout);
            })
        ]).catch(function (e) {
            if (timer) clearTimeout(timer);
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

    /* v2.33：状态渲染独立出来 —— 接口慢/失败也要把界面点亮（显示「未启动」+ 开始按钮），
       绝不能停在「转圈」上让人以为卡死。 */
    function paint(running, sub, sysProxy, note) {
        var dot = $('accelDot'), title = $('accelTitle'), subEl = $('accelSub');
        if (dot) dot.className = 'accel-dot' + (running ? ' on' : '');
        if (title) title.textContent = running ? '加速中' : '未启动';
        if (subEl) {
            var bits = [];
            if (sub && sub.nodes) bits.push('已载入 ' + sub.nodes + ' 个节点');
            else bits.push('尚未配置订阅');
            if (sysProxy && sysProxy.enabled) bits.push('系统代理已开');
            if (note) bits.push(note);
            subEl.textContent = bits.join(' · ');
        }
        if ($('accelStartBtn')) $('accelStartBtn').style.display = running ? 'none' : '';
        if ($('accelStopBtn')) $('accelStopBtn').style.display = running ? '' : 'none';
    }

    function refresh() {
        /* fast=1：首屏只要「跑没跑」这类毫秒级字段，节点列表交给后面补。 */
        return api('/api/accel/status?fast=1', 'GET', null, 8000).then(function (r) {
            if (!r || !r.success) {
                paint(false, null, null, r && r.message ? r.message : '状态获取失败');
                return r;
            }
            paint(!!r.running, r.sub, r.system_proxy);
            if (r.running) loadNodes();
            /* 后台再补一次完整状态（版本 / 当前节点），最多错开 0.5 秒，
               别在首屏同一帧再把后端线程占住。 */
            setTimeout(function () {
                api('/api/accel/status', 'GET', null, 8000).then(function (r2) {
                    if (!r2 || !r2.success) return;
                    paint(!!r2.running, r2.sub, r2.system_proxy);
                    if (r2.running) loadNodes();
                });
            }, 500);
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
