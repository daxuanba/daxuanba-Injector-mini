// --- 手搓页逻辑：官方源手搓 + 一键入库 + 下载 ---
class DxbCraftPage {
    constructor() {
        this.lua = '';
        this.filename = '';
        this.elements = {
            luaAppId: document.getElementById('luaAppId'),
            luaCraftBtn: document.getElementById('luaCraftBtn'),
            luaImportBtn: document.getElementById('luaImportBtn'),
            luaDownloadBtn: document.getElementById('luaDownloadBtn'),
            luaPreview: document.getElementById('luaPreview'),
            progressContainer: document.getElementById('progressContainer'),
            clearLogBtn: document.getElementById('clearLogBtn'),
            snackbar: document.getElementById('snackbar'),
            snackbarMessage: document.getElementById('snackbarMessage'),
            snackbarClose: document.getElementById('snackbarClose'),
        };
        this.bind();
    }

    bind() {
        this.elements.luaCraftBtn.addEventListener('click', () => this.craft());
        this.elements.luaImportBtn.addEventListener('click', () => this.importLua());
        this.elements.luaDownloadBtn.addEventListener('click', () => this.downloadLua());
        this.elements.clearLogBtn.addEventListener('click', () => {
            this.elements.progressContainer.innerHTML = '<div class="progress-placeholder"><span class="material-icons">info</span><p>等待任务开始...</p></div>';
        });
        this.elements.snackbarClose.addEventListener('click', () => this.hideSnackbar());
    }

    log(type, msg) {
        const box = this.elements.progressContainer;
        const ph = box.querySelector('.progress-placeholder');
        if (ph) box.innerHTML = '';
        const div = document.createElement('div');
        div.className = `log-entry ${type}`;
        div.textContent = `[${new Date().toLocaleTimeString()}] ${msg}`;
        box.appendChild(div);
        box.scrollTop = box.scrollHeight;
    }

    showSnackbar(message, type = 'info') {
        this.elements.snackbarMessage.textContent = message;
        this.elements.snackbar.className = `snackbar show ${type}`;
        setTimeout(() => this.hideSnackbar(), 5000);
    }
    hideSnackbar() { this.elements.snackbar.classList.remove('show'); }

    async craft() {
        const appid = this.elements.luaAppId.value.trim();
        if (!appid) { this.showSnackbar('请输入 AppID。', 'error'); return; }
        const btn = this.elements.luaCraftBtn;
        btn.disabled = true;
        const original = btn.innerHTML;
        btn.innerHTML = '<span class="material-icons spin">hourglass_top</span> 手搓中...';
        this.log('info', `开始手搓（仅官方源）：${appid}`);
        try {
            const resp = await fetch('/api/craft_lua', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ appid, include_manifests: true }),
            });
            const data = await resp.json();
            if (data.success) {
                this.lua = data.lua;
                this.filename = data.filename;
                this.elements.luaPreview.value = data.lua;
                this.elements.luaImportBtn.disabled = false;
                this.elements.luaDownloadBtn.disabled = false;
                const info = data.info || {};
                this.log('info', `手搓完成：${info.name || appid}，depot ${info.depots ? info.depots.length : 0} 个（官方源，无第三方密钥）`);
                this.showSnackbar(`手搓完成：${info.name || appid}`, 'success');
            } else {
                throw new Error(data.message || '手搓失败');
            }
        } catch (error) {
            this.log('error', `手搓出错: ${error.message}`);
            this.showSnackbar(`手搓出错: ${error.message}`, 'error');
        } finally {
            setTimeout(() => { btn.disabled = false; btn.innerHTML = original; }, 800);
        }
    }

    async importLua() {
        if (!this.lua) { this.showSnackbar('请先手搓生成 lua。', 'error'); return; }
        const btn = this.elements.luaImportBtn;
        btn.disabled = true;
        try {
            const resp = await fetch('/api/craft_import', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ lua: this.lua, filename: this.filename || 'crafted.lua' }),
            });
            const data = await resp.json();
            this.log(data.success ? 'info' : 'error', data.message || (data.success ? '入库完成。' : '入库失败。'));
            this.showSnackbar(data.message || (data.success ? '入库完成。' : '入库失败。'), data.success ? 'success' : 'error');
        } catch (error) {
            this.log('error', `入库出错: ${error.message}`);
            this.showSnackbar(`入库出错: ${error.message}`, 'error');
        } finally {
            setTimeout(() => { btn.disabled = false; }, 800);
        }
    }

    async downloadLua() {
        if (!this.lua) { this.showSnackbar('没有可下载的内容。', 'error'); return; }
        try {
            const resp = await fetch('/api/download_lua', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ lua: this.lua, filename: this.filename || 'crafted.lua' }),
            });
            if (!resp.ok) { this.showSnackbar('下载失败。', 'error'); return; }
            const blob = await resp.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = this.filename || 'crafted.lua';
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(url);
            this.showSnackbar('已开始下载 lua 文件。', 'success');
        } catch (error) {
            this.showSnackbar(`下载出错: ${error.message}`, 'error');
        }
    }
}

document.addEventListener('DOMContentLoaded', () => { new DxbCraftPage(); });
