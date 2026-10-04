// 外链统一出口 —— 全站共用。
//
// 为什么不能用 window.open(url, '_blank')：
// 内嵌 WebView2（pywebview edgechromium）没有真正的多窗口，
// window.open / <a target="_blank"> 会**在当前主窗口**导航过去。
// 一旦点到，主窗口就被替换成 Steam 商店页 —— 顶部标签栏、侧边路由全丢，
// 用户看到的就是「点不动、卡死、F12 没反应、连关闭都关不掉」。
//
// 正确做法：外链交给系统默认浏览器，主窗口永远只显示本地页面。
if (typeof window.openExternal !== 'function') {
    window.openExternal = function (url) {
        const u = String(url || '').trim();
        if (!/^https?:\/\//i.test(u)) {
            return;
        }
        try {
            fetch('/api/open-external', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url: u })
            }).catch(() => { });
        } catch (e) {
            console.warn('openExternal failed:', e);
        }
    };
}
