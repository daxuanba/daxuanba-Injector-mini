// 外链统一出口 —— 全站共用。
//
// 为什么不能用 window.open(url, '_blank')：
// 内嵌 WebView2（pywebview edgechromium）没有真正的多窗口，
// window.open / <a target="_blank"> 会**在当前主窗口**导航过去。
// 一旦点到，主窗口就被替换成 Steam 商店页 —— 顶部标签栏、侧边路由全丢，
// 用户看到的就是「点不动、卡死」。
//
// 正确做法（v2.27）：
//   1. 站内链接（相对路径 /xxx、# 锚点、javascript:）**一律放行**，主窗口正常导航；
//   2. 真正的 http(s) 外链 → 默认**在应用内新开一个窗口**（仍是本程序，不跳浏览器）；
//   3. 只有显式标 data-external="browser" 的按钮才走系统浏览器。
//
// 注意 v2.26 的 bug：这里曾经用「href 里不含 127.0.0.1」来判定外链，
// 结果站内相对链接 /manager、/free 全被当成外链.preventDefault + 丢系统浏览器，
// 表现就是「点侧栏没反应、还默默弹出一个浏览器窗口」。
(function () {
    function isAbsHttp(u) {
        return /^(https?:)?\/\//i.test(String(u || '').trim());
    }
    function post(url, inApp) {
        try {
            fetch('/api/open-external', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url: url, in_app: !!inApp })
            }).catch(function () { });
        } catch (e) {
            console.warn('openExternal failed:', e);
        }
    }
    window.openExternal = function (url, inApp) {
        var u = String(url || '').trim();
        if (!isAbsHttp(u)) {
            return;
        }
        post(u, inApp);
    };
    // 应用内新窗口（默认）
    window.openInApp = function (url) { post(url, true); };
    // 系统浏览器（显式）
    window.openInSystem = function (url) { post(url, false); };

    function install() {
        if (document.documentElement.getAttribute('data-dxb-linkguard')) {
            return;
        }
        document.documentElement.setAttribute('data-dxb-linkguard', '1');
        document.addEventListener('click', function (ev) {
            var a = ev.target && ev.target.closest ? ev.target.closest('a[href]') : null;
            if (!a) { return; }
            var href = (a.getAttribute('href') || '').trim();
            if (!href || href.charAt(0) === '#') { return; }
            if (href.indexOf('javascript:') === 0 || href.indexOf('mailto:') === 0) { return; }
            // 站内相对 / 绝对本地路径 → 让 WebView2 自己正常导航
            if (!isAbsHttp(href)) { return; }
            var d = a.dataset || {};
            if (d.external === 'browser') {
                ev.preventDefault();
                post(href, false);          // 明确要求：系统浏览器
                return;
            }
            ev.preventDefault();
            post(href, true);               // 默认：应用内打开
        }, true);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', install);
    } else {
        install();
    }
})();
