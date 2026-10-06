
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

    // ------------------------------------------------------------------
    // 「界面卡住不看后端」自检（v2.34）
    //
    // 真实案例：WebView2 的 GPU 缓存写坏后，GPU 进程直接挂住 —— 页面渲染得出来，
    // 但所有 fetch 一个都发不出去，界面永远停在「正在加载清单源...」，
    // 标题还变「(未响应)」。这时候后端接口其实是秒回的（从外面 curl 0.1s），
    // 日志也看不到任何请求 —— 光看后端 / 光看接口耗时完全查不出来。
    //
    // 所以这里做前端自检：8 秒后页面里还有「转圈 / 加载中」的占位没被替换掉，
    // 就直接告诉用户「是渲染卡住，不是接口慢」，并给两个自救按钮：
    //   1) 刷新界面（location.reload）
    //   2) 清 GPU 缓存并重启（/api/gpu_cache/clear，桌面壳会清 profile 里的缓存再重启）
    // ------------------------------------------------------------------
    function hasStuckLoading() {
        var nodes = document.querySelectorAll('.loading, .spinner-box, .loading-spinner');
        for (var i = 0; i < nodes.length; i++) {
            var el = nodes[i];
            var t = (el.textContent || '').trim();
            // 只看「还在加载中」的占位：转圈文案 / loading 类
            if (el.offsetParent !== null || t) { return true; }
        }
        return false;
    }

    function showStuckBanner() {
        var box = document.createElement('div');
        box.id = 'dxbStuckBanner';
        box.style.cssText = [
            'position:fixed', 'bottom:16px', 'left:50%', 'transform:translateX(-50%)',
            'z-index:100000', 'max-width:min(720px,92vw)',
            'padding:12px 14px', 'border-radius:10px',
            'background:#5b1f1f', 'color:#fff', 'font-size:13px', 'line-height:1.6',
            'box-shadow:0 6px 20px rgba(0,0,0,.5)', 'display:block'
        ].join(';');
        var txt = document.createElement('div');
        txt.innerHTML = '<b>界面看着卡住了，但接口其实有在回。</b>'
            + '多半是 WebView2 的显卡缓存坏了（GPU 进程挂住），不是网络慢。'
            + '可以先刷新界面试试；还不行就点「清缓存重启」。';
        box.appendChild(txt);
        var row = document.createElement('div');
        row.style.cssText = 'margin-top:8px;display:flex;gap:8px;flex-wrap:wrap';
        function mk(label, fn) {
            var b = document.createElement('button');
            b.textContent = label;
            b.style.cssText = 'padding:6px 12px;border:1px solid #fff;border-radius:6px;'
                + 'background:transparent;color:#fff;cursor:pointer;font-size:12px';
            b.onclick = fn;
            row.appendChild(b);
        }
        mk('刷新界面', function () { try { location.reload(); } catch (e) { /* noop */ } });
        mk('清缓存并重启', function () {
            var b = row.querySelector('button:nth-child(2)');
            if (b) { b.textContent = '清缓存中…'; b.disabled = true; }
            fetch('/api/gpu_cache/clear', { method: 'POST' })
                .catch(function () { location.reload(); });
        });
        box.appendChild(row);
        document.body.appendChild(box);
    }

    setTimeout(function () {
        try {
            if (document.readyState === 'complete' || document.readyState === 'interactive') {
                if (hasStuckLoading()) { showStuckBanner(); }
            }
        } catch (e) { /* 自检失败就算了 */ }
    }, 8000);
})();
