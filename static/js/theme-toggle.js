
// --- 页面内确认框（替代原生 confirm，避免 QT 原生弹窗） ---
function dxbConfirm(message) {
    return new Promise((resolve) => {
        const overlay = document.createElement('div');
        overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.55);z-index:99999;display:flex;align-items:center;justify-content:center;';
        overlay.innerHTML = `
            <div style="background:var(--md-sys-color-surface-container,#1a1a1a);color:var(--md-sys-color-on-surface,#f3f3f3);
                        border:1px solid var(--dx-card-border,#2a2a2a);border-radius:14px;padding:22px 26px;max-width:360px;width:86%;
                        box-shadow:0 12px 40px rgba(0,0,0,0.5);font-size:14px;line-height:1.6;">
                <div style="margin-bottom:18px;">${message}</div>
                <div style="display:flex;gap:10px;justify-content:flex-end;">
                    <button data-act="cancel" style="padding:8px 18px;border-radius:10px;border:1px solid var(--dx-card-border,#2a2a2a);
                            background:transparent;color:inherit;cursor:pointer;">取消</button>
                    <button data-act="ok" style="padding:8px 18px;border-radius:10px;border:none;background:var(--dx-yellow,#f1c40f);
                            color:#111;font-weight:600;cursor:pointer;">确定</button>
                </div>
            </div>`;
        const done = (v) => { overlay.remove(); resolve(v); };
        overlay.addEventListener('click', (e) => {
            const act = e.target.dataset && e.target.dataset.act;
            if (act === 'ok') done(true);
            else if (act === 'cancel' || e.target === overlay) done(false);
        });
        document.body.appendChild(overlay);
    });
}
// --- START OF FILE static/js/theme-toggle.js (MODIFIED for Shutdown) ---
document.addEventListener('DOMContentLoaded', () => {
    const themeToggleBtn = document.getElementById('themeToggleBtn');
    const shutdownBtn = document.getElementById('shutdownBtn');

    // --- Theme Toggle Logic ---
    if (themeToggleBtn) {
        const body = document.body;
        const root = document.documentElement;
        const themeKey = 'dxb-theme-preference';
        const icon = themeToggleBtn.querySelector('.material-icons');

        const updateIcon = (theme) => {
            if (theme === 'dark') {
                icon.textContent = 'light_mode';
                themeToggleBtn.setAttribute('title', '切换到亮色模式');
            } else {
                icon.textContent = 'dark_mode';
                themeToggleBtn.setAttribute('title', '切换到暗色模式');
            }
        };

        const applyTheme = (theme) => {
            if (theme === 'dark') {
                body.classList.add('dark-theme');
                root.classList.add('dxb-dark');
                root.classList.remove('dxb-light');
            } else {
                body.classList.remove('dark-theme');
                root.classList.add('dxb-light');
                root.classList.remove('dxb-dark');
            }
            updateIcon(theme);
        };

        const currentTheme = localStorage.getItem(themeKey) || 'dark';
        applyTheme(currentTheme);

        themeToggleBtn.addEventListener('click', () => {
            const isDark = body.classList.toggle('dark-theme');
            const newTheme = isDark ? 'dark' : 'light';
            if (newTheme === 'dark') {
                root.classList.add('dxb-dark');
                root.classList.remove('dxb-light');
            } else {
                root.classList.add('dxb-light');
                root.classList.remove('dxb-dark');
            }
            localStorage.setItem(themeKey, newTheme);
            updateIcon(newTheme);
        });
    }

    // --- Shutdown Logic ---
    if (shutdownBtn) {
        shutdownBtn.addEventListener('click', () => {
            dxbConfirm('确定要关闭应用吗？将同时关闭网页和后台程序。').then((ok) => {
                if (!ok) return;
                // Inform the user
                document.body.innerHTML = `
                    <div class="dxb-shutdown">
                        <h1>正在关闭应用...</h1>
                        <p>您可以安全地关闭此浏览器标签页。</p>
                    </div>`;

                    // Send shutdown request to the server
                    fetch('/api/shutdown', { method: 'POST' })
                        .catch(error => {
                            console.error('无法连接到服务器以执行关闭命令:', error);
                        });
            });
        });
    }
});