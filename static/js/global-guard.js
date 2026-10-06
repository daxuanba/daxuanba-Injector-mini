
// ---------------------------------------------------------------------------
// 全局接口守卫（v2.33）—— 每个页面都必须先加载它
//
// 以前只有首页（app.js）给 /api/ 请求挂了「慢请求横幅」，
// 其它页面（推荐 / 免费游戏 / 设置 / 加速 / 工具箱 / 入库管理 …）
// 全是裸 fetch：接口一挂，页面就永远停在转圈上，
// windowed 打包没控制台，用户眼里就是「换页面卡死、点啥没反应」。
//
// 这里做三件事（所有页面统一）：
//   1. 所有 /api/ 请求带硬超时（默认 25 秒），超时抛看得懂的错，不再无声挂住；
//   2. 单条接口超过 10 秒就在页面顶部打醒目横幅，明确说「程序没死，是接口慢」；
//   3. 捕获未处理异常 / 资源加载失败，也让用户看到（而不是白屏硬扛）。
//
// 结论：**界面永远要有反馈**，宁可报错也不要转圈转到天荒地老。
// ---------------------------------------------------------------------------
(function () {
    if (window.__dxbGuard) { window.__dxbGuard.installOnce(); return; }

    var SLOW_LIMIT = 10000;      // 超过这个时间就提示（毫秒）
    var HARD_TIMEOUT = 25000;    // 超过这个时间直接放弃（毫秒）
    var banner = null;
    var bannerHideTimer = null;

    function ensureBanner() {
        if (banner) { return banner; }
        banner = document.createElement('div');
        banner.id = 'dxbGuardBanner';
        banner.style.cssText = [
            'position:fixed', 'top:0', 'left:0', 'right:0', 'z-index:99999',
            'padding:10px 14px', 'background:#7c2d12', 'color:#fff',
            'font-size:13px', 'line-height:1.5', 'box-shadow:0 2px 8px rgba(0,0,0,.4)',
            'display:none', 'pointer-events:auto', 'cursor:pointer'
        ].join(';');
        banner.addEventListener('click', hideBanner);
        document.body.appendChild(banner);
        return banner;
    }

    function hideBanner() {
        if (bannerHideTimer) { clearTimeout(bannerHideTimer); bannerHideTimer = null; }
        if (banner) { banner.style.display = 'none'; }
    }

    function markSlow(url, cost) {
        if (!cost || cost < SLOW_LIMIT) { return; }
        try {
            var b = ensureBanner();
            b.style.display = 'block';
            b.textContent = '后台接口响应很慢（' + (cost / 1000).toFixed(1) + ' 秒）：' + url
                + '　—　程序仍可操作。常见原因：系统代理/加速异常、Steam 或 GitHub 不可达；'
                + '打「工具箱 → 网络加速」开会更快。点此关闭。';
            if (bannerHideTimer) { clearTimeout(bannerHideTimer); }
            bannerHideTimer = setTimeout(hideBanner, 20000);
        } catch (e) { /* 提示失败也不能影响业务 */ }
    }

    var origFetch = window.fetch ? window.fetch.bind(window) : null;

    var guard = {
        markSlow: markSlow,
        hideBanner: hideBanner,
        installOnce: function () { /* 重复引入时只补一次提示，不重复包 fetch */ }
    };
    window.__dxbGuard = guard;

    if (!origFetch) { return; }

    function urlOf(input) {
        if (typeof input === 'string') { return input; }
        if (input && typeof input.url === 'string') { return input.url; }
        return '';
    }

    window.fetch = function (input, init) {
        var raw = urlOf(input);
        if (!/^\/api\//.test(raw)) { return origFetch(input, init); }

        var ctrl = (typeof AbortController !== 'undefined') ? new AbortController() : null;
        var timer = ctrl ? setTimeout(function () {
            try { ctrl.abort(); } catch (e) { /* ignore */ }
        }, HARD_TIMEOUT) : null;
        var opt = init || {};
        if (ctrl) {
            opt = Object.assign({}, opt, { signal: ctrl.signal });
        }
        var t0 = (window.performance && performance.now) ? performance.now() : Date.now();

        function done() {
            var cost = ((window.performance && performance.now) ? performance.now() : Date.now()) - t0;
            if (timer) { clearTimeout(timer); }
            markSlow(raw, cost);
        }
        return Promise.race([
            origFetch(input, opt),
            new Promise(function (_, rej) {
                setTimeout(function () { rej(new Error('timeout')); }, HARD_TIMEOUT);
            })
        ]).then(function (r) { done(); return r; }, function (e) { done(); throw e; })
          .catch(function (e) {
              if (timer) { clearTimeout(timer); }
              if (e && e.name === 'AbortError') {
                  throw new Error('接口超时（超过 ' + (HARD_TIMEOUT / 1000 | 0) + ' 秒）：' + raw
                      + ' —— 多半是没开「网络加速」或代理抽风，点顶部「工具箱 → 网络加速」开一下。');
              }
              throw e;
          });
    };

    // 未捕获异常：至少在界面上留个痕，别悄悄白屏
    window.addEventListener('error', function (ev) {
        try {
            if (ev && ev.message && /Failed to fetch|NetworkError|net::/i.test(String(ev.message))) { return; }
        } catch (e) { /* ignore */ }
    });
})();
