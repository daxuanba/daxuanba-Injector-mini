class SettingsManager {
    constructor() {
        this.elements = {
            githubToken: document.getElementById('githubToken'),
            steamPath: document.getElementById('steamPath'),
            steamPathStatus: document.getElementById('steamPathStatus'),
            debugMode: document.getElementById('debugMode'),
            loggingFiles: document.getElementById('loggingFiles'),
            disableLogging: document.getElementById('disableLogging'),
            saveBtn: document.getElementById('saveConfig'),
            resetBtn: document.getElementById('resetConfig'),
            snackbar: document.getElementById('snackbar'),
            snackbarMessage: document.getElementById('snackbarMessage'),
            snackbarClose: document.getElementById('snackbarClose'),
            toggleTokenBtn: document.getElementById('toggleTokenBtn'),
            tokenVisibilityIcon: document.getElementById('tokenVisibilityIcon'),
            toggleConsoleBtn: document.getElementById('toggleConsoleBtn'),
            showConsoleOnStartup: document.getElementById('showConsoleOnStartup'),
            forceUnlockerRadios: document.querySelectorAll('input[name="forceUnlocker"]'),
            autoInstallUnlocker: document.getElementById('autoInstallUnlocker'),
            unlockerPrefRadios: document.querySelectorAll('input[name="unlockerPref"]'),
            greenlumaRepo: document.getElementById('greenlumaRepo'),
            steamtoolsRepo: document.getElementById('steamtoolsRepo'),
            ostStatus: document.getElementById('ostStatus'),
            opensteamtoolRepo: document.getElementById('opensteamtoolRepo'),
            ostInstallBtn: document.getElementById('ostInstallBtn'),
            stoolsStatus: document.getElementById('stoolsStatus'),
            stoolsInstallBtn: document.getElementById('stoolsInstallBtn'),
            glumaStatus: document.getElementById('glumaStatus'),
            glumaInstallBtn: document.getElementById('glumaInstallBtn'),
            glumaRecheckBtn: document.getElementById('glumaRecheckBtn'),
            glumaOfficialBtn: document.getElementById('glumaOfficialBtn'),
            nativeStatus: document.getElementById('nativeStatus'),
            useNativeBtn: document.getElementById('useNativeBtn'),
            updateSummary: document.getElementById('updateSummary'),
            checkUpdatesBtn: document.getElementById('checkUpdatesBtn'),
            addGithubRepoBtn: document.getElementById('addGithubRepoBtn'),
            addZipRepoBtn: document.getElementById('addZipRepoBtn'),
            githubReposList: document.getElementById('githubReposList'),
            zipReposList: document.getElementById('zipReposList'),
            addRepoModal: document.getElementById('addRepoModal'),
            repoModalTitle: document.getElementById('repoModalTitle'),
            repoName: document.getElementById('repoName'),
            repoPath: document.getElementById('repoPath'),
            repoUrl: document.getElementById('repoUrl'),
            repoPathGroup: document.getElementById('repoPathGroup'),
            repoUrlGroup: document.getElementById('repoUrlGroup'),
            cancelRepoBtn: document.getElementById('cancelRepoBtn'),
            saveRepoBtn: document.getElementById('saveRepoBtn'),
            updateModal: document.getElementById('updateModal'),
            updateInfo: document.getElementById('updateInfo'),
            updateChangelog: document.getElementById('updateChangelog'),
            downloadUpdateBtn: document.getElementById('downloadUpdateBtn'),
            laterUpdateBtn: document.getElementById('laterUpdateBtn'),
            ignoreUpdateBtn: document.getElementById('ignoreUpdateBtn'),
        };
        
        this.currentRepoType = 'github';
        this.customRepos = { github: [], zip: [] };
        
        this.initialize();
    }

    initialize() {
        this.loadConfig();
        this.elements.saveBtn.addEventListener('click', () => this.saveConfig());
        this.elements.resetBtn.addEventListener('click', () => this.resetConfig());
        this.elements.snackbarClose.addEventListener('click', () => this.hideSnackbar());
        this.elements.steamPath.addEventListener('input', () => this.validateSteamPath(false));
        this.elements.toggleTokenBtn.addEventListener('click', () => this.toggleTokenVisibility());
        
        if (this.elements.toggleConsoleBtn) {
            this.elements.toggleConsoleBtn.addEventListener('click', () => this.toggleConsole());
        }

        this.elements.checkUpdatesBtn.addEventListener('click', () => this.checkAllUpdates());
        this.elements.addGithubRepoBtn.addEventListener('click', () => this.showAddRepoModal('github'));
        this.elements.addZipRepoBtn.addEventListener('click', () => this.showAddRepoModal('zip'));
        
        this.elements.saveRepoBtn.addEventListener('click', () => this.saveRepo());
        this.elements.cancelRepoBtn.addEventListener('click', () => this.hideAddRepoModal());
        
        this.elements.laterUpdateBtn.addEventListener('click', () => this.hideUpdateModal());
        this.elements.downloadUpdateBtn.addEventListener('click', () => this.downloadUpdate());
        this.elements.ignoreUpdateBtn.addEventListener('click', () => this.ignoreUpdate());
        
        this.elements.addRepoModal.addEventListener('click', (e) => {
            if (e.target === this.elements.addRepoModal) this.hideAddRepoModal();
        });
        this.elements.updateModal.addEventListener('click', (e) => {
            if (e.target === this.elements.updateModal) this.hideUpdateModal();
        });

        this.setupCategoryTabs();

        if (this.elements.ostInstallBtn) this.elements.ostInstallBtn.addEventListener('click', () => this.installDependency('opensteamtool'));
        if (this.elements.stoolsInstallBtn) this.elements.stoolsInstallBtn.addEventListener('click', () => this.installDependency('steamtools'));
        if (this.elements.glumaInstallBtn) this.elements.glumaInstallBtn.addEventListener('click', () => this.installDependency('greenluma'));
        if (this.elements.glumaRecheckBtn) this.elements.glumaRecheckBtn.addEventListener('click', () => {
            this.loadDependencyStatus();
            this.showSnackbar('已重新检测三个内核的安装状态。', 'info');
        });
        if (this.elements.glumaOfficialBtn) this.elements.glumaOfficialBtn.addEventListener('click', () => this.openExternal(
            'https://cs.rin.ru/forum/viewtopic.php?f=10&t=103709'));
        if (this.elements.useNativeBtn) this.elements.useNativeBtn.addEventListener('click', async () => {
            const r = await fetch('/api/config/update', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ force_unlocker_type: 'native' })
            });
            const d = await r.json();
            this.showSnackbar(d.success ? '已把入库方式设为「自研入库」，回首页直接入库即可'
                                         : (d.message || '设置失败'), d.success ? 'success' : 'error');
        });

        this.loadDependencyStatus();
        this.checkAllUpdates();
    }

    setupCategoryTabs() {
        const tabs = document.querySelectorAll('.tab-btn');
        const cards = document.querySelectorAll('.card[data-category]');
        const showCat = (cat) => {
            tabs.forEach(t => t.classList.toggle('active', t.dataset.cat === cat));
            cards.forEach(c => c.classList.toggle('settings-category-hidden', c.dataset.category !== cat));
        };
        tabs.forEach(t => t.addEventListener('click', () => showCat(t.dataset.cat)));
        showCat('github');
    }

    async toggleConsole() {
        try {
            const response = await fetch('/api/console/toggle', { method: 'POST' });
            const data = await response.json();
            this.showSnackbar(data.message, data.success ? 'success' : 'error');
        } catch (error) {
            this.showSnackbar(`请求切换控制台时出错: ${error.message}`, 'error');
        }
    }

    toggleTokenVisibility() {
        const tokenInput = this.elements.githubToken;
        const icon = this.elements.tokenVisibilityIcon;

        if (tokenInput.type === 'password') {
            tokenInput.type = 'text';
            icon.textContent = 'visibility_off';
            tokenInput.classList.add('token-visible');
        } else {
            tokenInput.type = 'password';
            icon.textContent = 'visibility';
            tokenInput.classList.remove('token-visible');
        }
    }
    
    validateSteamPath(isAuto) {
        const path = this.elements.steamPath.value.trim();
        const statusEl = this.elements.steamPathStatus;
        const iconEl = statusEl.querySelector('.status-icon');
        const textEl = statusEl.querySelector('.status-text');

        if (!path) {
            statusEl.style.display = 'none';
            return;
        }

        statusEl.style.display = 'flex';

        if (isAuto) {
            statusEl.className = 'status-indicator success';
            iconEl.textContent = 'check_circle';
            textEl.textContent = '已自动识别Steam路径';
        } else {
            if (path.toLowerCase().includes('steam')) {
                statusEl.className = 'status-indicator success';
                iconEl.textContent = 'task_alt';
                textEl.textContent = '看起来路径正确';
            } else {
                statusEl.className = 'status-indicator warning';
                iconEl.textContent = 'warning';
                textEl.textContent = '路径可能不正确，请确认';
            }
        }
    }

    async checkForUpdates() {
        const btn = this.elements.checkUpdatesBtn;
        const originalContent = btn.innerHTML;
        
        btn.disabled = true;
        btn.innerHTML = '<span class="material-icons spin">hourglass_top</span> 检查中...';
        
        try {
            const response = await fetch('/api/check_updates', { method: 'POST' });
            const data = await response.json();
            
            if (data.success) {
                if (data.has_update) {
                    this.showUpdateModal(data.update_info);
                } else {
                    this.showSnackbar('当前已是最新版本！', 'success');
                }
            } else {
                this.showSnackbar(`检查更新失败: ${data.message}`, 'error');
            }
        } catch (error) {
            this.showSnackbar(`检查更新时出错: ${error.message}`, 'error');
        } finally {
            setTimeout(() => {
                btn.disabled = false;
                btn.innerHTML = originalContent;
            }, 1000);
        }
    }

    showUpdateModal(updateInfo) {
        const infoHtml = `
            <div class="update-info-item">
                <span class="update-info-label">当前版本:</span>
                <span class="update-info-value version">${updateInfo.current_version}</span>
            </div>
            <div class="update-info-item">
                <span class="update-info-label">最新版本:</span>
                <span class="update-info-value version">${updateInfo.latest_version}</span>
            </div>
            <div class="update-info-item">
                <span class="update-info-label">发布时间:</span>
                <span class="update-info-value">${new Date(updateInfo.published_at).toLocaleString('zh-CN')}</span>
            </div>
        `;
        this.elements.updateInfo.innerHTML = infoHtml;
        
        this.elements.updateChangelog.textContent = updateInfo.release_body || '暂无更新日志';
        
        this.elements.updateModal.dataset.updateUrl = updateInfo.release_url;
        this.elements.updateModal.dataset.latestVersion = updateInfo.latest_version;
        
        this.elements.updateModal.classList.add('show');
    }

    hideUpdateModal() {
        this.elements.updateModal.classList.remove('show');
    }

    downloadUpdate() {
        const btn = this.elements.downloadUpdateBtn;
        const original = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = '<span class="material-icons spin">hourglass_top</span> 正在更新...';
        fetch('/api/auto_update', { method: 'POST' })
            .then(r => r.json())
            .then(data => {
                if (data.success && data.has_update) {
                    this.showSnackbar('已下载更新安装包，即将自动安装...', 'success');
                } else if (data.success && !data.has_update) {
                    this.showSnackbar('当前已是最新版本。', 'info');
                } else {
                    this.showSnackbar(`更新失败: ${data.message}`, 'error');
                }
            })
            .catch(e => this.showSnackbar(`更新出错: ${e.message}`, 'error'))
            .finally(() => { setTimeout(() => { btn.disabled = false; btn.innerHTML = original; }, 1200); this.hideUpdateModal(); });
    }

    ignoreUpdate() {
        const latestVersion = this.elements.updateModal.dataset.latestVersion;
        if (latestVersion) {
            localStorage.setItem('ignoredVersion', latestVersion);
            this.showSnackbar(`已忽略版本 ${latestVersion}`, 'info');
        }
        this.hideUpdateModal();
    }

    async loadDependencyStatus() {
        try {
            /* v2.33：默认 remote=0 —— 只报本地装没装、什么版本，
               不去 GitHub 问「有没有新版」（那要 2 秒以上，进设置页就卡一下）。
               「检查更新」按钮（下面 remote=1）才真的去问远端。 */
            const ctrl = (typeof AbortController !== 'undefined') ? new AbortController() : null;
            const response = await fetch('/api/kernel/status?remote=0',
                ctrl ? { signal: ctrl.signal } : undefined);
            if (ctrl) {
                clearTimeout(this._kernelAbortTimer);
                this._kernelAbortTimer = setTimeout(() => {
                    try { ctrl.abort(); } catch (e) { /* ignore */ }
                }, 10000);
            }
            const data = await response.json();
            if (!data.success) return;
            const STATE_TXT = { none: '未安装', install: '可安装', latest: '已是最新',
                                update: '可更新', unknown: '版本未知' };
            const verCmp = (a, b) => {
                const pa = String(a || '').replace(/^v/i, '').split('.');
                const pb = String(b || '').replace(/^v/i, '').split('.');
                const n = Math.max(pa.length, pb.length);
                for (let i = 0; i < n; i++) {
                    const x = parseInt(pa[i], 10) || 0, y = parseInt(pb[i], 10) || 0;
                    if (x !== y) return x > y ? 1 : -1;
                }
                return 0;
            };
            const render = (el, kind) => {
                if (!el) return;
                const st = (data.kernels || {})[kind] || {};
                if (st.builtin) {
                    el.innerHTML = `<span class="status-dot ok"></span><span class="status-text">内置免安装`
                        + `${st.version ? ' v' + st.version : ''}</span>`;
                    el.title = st.note || '';
                    return;
                }
                const cls = st.update_state === 'update' ? 'warn' : (st.installed ? 'ok' : '');
                const local = st.version || (st.installed ? '已安装' : '未安装');
                const remote = st.remote_version ? `　·　最新 ${st.remote_version}` : '　·　最新未取到';
                const state = st.update_state ? `　·　${STATE_TXT[st.update_state] || ''}` : '';
                el.innerHTML = `<span class="status-dot ${cls}"></span>`
                    + `<span class="status-text">${local}${remote}${state}</span>`;
                el.title = (st.remote_note || '') + (st.files && st.files.length ? ('\n已就位：' + st.files.join('、')) : '');
            };
            render(this.elements.ostStatus, 'opensteamtool');
            render(this.elements.stoolsStatus, 'steamtools');
            render(this.elements.glumaStatus, 'greenluma');
            if (this.elements.nativeStatus) render(this.elements.nativeStatus, 'native');
            this._kernelPollTimer && clearInterval(this._kernelPollTimer);
            if (this._kInstalling) {
                this._kernelPollTimer = setInterval(() => this._pollKernelProgress(), 900);
            }
        } catch (e) {
            console.error('加载内核状态失败', e);
        }
    }

    async _pollKernelProgress() {
        const kind = this._kInstalling;
        if (!kind) { clearInterval(this._kernelPollTimer); return; }
        try {
            const r = await fetch('/api/kernel/progress');
            const d = await r.json();
            const p = ((d.progress || {})[kind]) || {};
            const bar = document.getElementById(`kprog-${kind}`);
            const msg = document.getElementById(`kmsg-${kind}`);
            if (bar) {
                bar.classList.add('show');
                const i = bar.querySelector('i');
                if (i) i.style.width = Math.max(0, Math.min(100, p.percent || 0)) + '%';
            }
            if (msg && p.message != null) { msg.textContent = p.message; }
            if (p.running === false) {
                clearInterval(this._kernelPollTimer);
                this._kInstalling = null;
                setTimeout(() => this.loadDependencyStatus(), 600);
            }
        } catch (e) { /* ignore */ }
    }

    async installDependency(kind) {
        const btnMap = {
            opensteamtool: this.elements.ostInstallBtn,
            steamtools: this.elements.stoolsInstallBtn,
            greenluma: this.elements.glumaInstallBtn,
        };
        const btn = btnMap[kind];
        if (!btn) return;
        const original = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = '<span class="material-icons spin">hourglass_top</span> 下载中...';
        this._kInstalling = kind;
        try {
            const response = await fetch('/api/kernel/install', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ kind, force: true })
            });
            const data = await response.json();
            if (data.success) {
                this.showSnackbar(data.message, 'info');
                this._pollKernelProgress();
            } else {
                this.showSnackbar(`安装失败: ${data.message}`, 'error');
                this._kInstalling = null;
            }
        } catch (e) {
            this.showSnackbar(`安装出错: ${e.message}`, 'error');
            this._kInstalling = null;
        } finally {
            setTimeout(() => { btn.disabled = false; btn.innerHTML = original; }, 2500);
        }
    }

    async checkAllUpdates() {
        const btn = this.elements.checkUpdatesBtn;
        if (btn) { btn.disabled = true; }
        if (this.elements.updateSummary) { this.elements.updateSummary.textContent = '正在去上游查最新版本…'; }
        try {
            const r = await fetch('/api/updates/check');
            const d = await r.json();
            if (!d.success) { this.showSnackbar(d.message || '检查失败', 'error'); return; }
            const app = d.app || {}, ks = d.kernels || {};
            const parts = [`应用：${app.has_update ? `${app.local} → ${app.remote} 可更新`
                : (app.ok ? `${app.local} 已是最新` : '版本未取到')}`];
            Object.keys(ks).forEach(k => {
                const v = ks[k] || {};
                const nm = ({ opensteamtool: 'OpenSteamTool', steamtools: 'SteamTools',
                              greenluma: 'GreenLuma', native: '自研入库' })[k] || k;
                if (v.builtin) { parts.push(`${nm}：内置免安装`); return; }
                if (!v.ok) { parts.push(`${nm}：未取到`); return; }
                if (!v.installed) { parts.push(`${nm}：未安装（最新 ${v.remote}）`); return; }
                parts.push(`${nm}：${v.local} → ${v.remote} ${v.has_update ? '可更新' : '已是最新'}`);
            });
            if (this.elements.updateSummary) { this.elements.updateSummary.textContent = parts.join('　|　'); }
            const anyUpd = app.has_update || Object.values(ks).some(v => v && v.has_update);
            this.showSnackbar(anyUpd ? '有可更新的内容' : '全部已是最新', anyUpd ? 'info' : 'success');
            this.loadDependencyStatus();
        } catch (e) {
            this.showSnackbar(`检查更新出错: ${e.message}`, 'error');
        } finally {
            if (btn) { btn.disabled = false; }
        }
    }

    async openExternal(url) {
        try {
            const r = await fetch('/api/app/open_url', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url }),
            });
            const d = await r.json();
            this.showSnackbar(d.message || '', d.success ? 'info' : 'error');
        } catch (e) {
            this.showSnackbar(`打开失败: ${e.message}`, 'error');
        }
    }

    showAddRepoModal(type) {
        this.currentRepoType = type;
        
        if (type === 'github') {
            this.elements.repoModalTitle.textContent = '添加GitHub仓库';
            this.elements.repoPathGroup.style.display = 'block';
            this.elements.repoUrlGroup.style.display = 'none';
            this.elements.repoPath.placeholder = '例如：username/repository';
        } else {
            this.elements.repoModalTitle.textContent = '添加ZIP清单库';
            this.elements.repoPathGroup.style.display = 'none';
            this.elements.repoUrlGroup.style.display = 'block';
            this.elements.repoUrl.placeholder = '例如：https://example.com/download/{app_id}.zip';
        }
        
        this.elements.repoName.value = '';
        this.elements.repoPath.value = '';
        this.elements.repoUrl.value = '';
        
        this.elements.addRepoModal.classList.add('show');
        this.elements.repoName.focus();
    }

    hideAddRepoModal() {
        this.elements.addRepoModal.classList.remove('show');
    }

    saveRepo() {
        const name = this.elements.repoName.value.trim();
        
        if (!name) {
            this.showSnackbar('请输入显示名称', 'error');
            return;
        }
        
        let repoData;
        if (this.currentRepoType === 'github') {
            const path = this.elements.repoPath.value.trim();
            if (!path) {
                this.showSnackbar('请输入仓库路径', 'error');
                return;
            }
            if (!path.includes('/')) {
                this.showSnackbar('GitHub仓库路径格式应为：用户名/仓库名', 'error');
                return;
            }
            repoData = { name, repo: path };
        } else {
            const url = this.elements.repoUrl.value.trim();
            if (!url) {
                this.showSnackbar('请输入下载URL', 'error');
                return;
            }
            if (!url.includes('{app_id}')) {
                this.showSnackbar('URL必须包含{app_id}占位符', 'error');
                return;
            }
            repoData = { name, url };
        }
        
        const existingRepos = this.customRepos[this.currentRepoType];
        const isDuplicate = existingRepos.some(repo => 
            repo.name === name || 
            (this.currentRepoType === 'github' && repo.repo === repoData.repo) ||
            (this.currentRepoType === 'zip' && repo.url === repoData.url)
        );
        
        if (isDuplicate) {
            this.showSnackbar('仓库已存在', 'error');
            return;
        }
        
        this.customRepos[this.currentRepoType].push(repoData);
        this.renderReposList();
        this.hideAddRepoModal();
        this.showSnackbar(`成功添加${this.currentRepoType === 'github' ? 'GitHub仓库' : 'ZIP清单库'}`, 'success');
        
        this.saveConfig().then(() => {
            console.log('自定义仓库配置已保存到服务器');
        }).catch(error => {
            console.error('保存自定义仓库配置失败:', error);
            this.showSnackbar('保存配置失败，请重试', 'error');
        });
    }

    removeRepo(type, index) {
        if (confirm('确定要删除这个仓库吗？')) {
            this.customRepos[type].splice(index, 1);
            this.renderReposList();
            this.showSnackbar('仓库已删除', 'success');
            
            this.saveConfig().then(() => {
                console.log('删除仓库后配置已保存到服务器');
            }).catch(error => {
                console.error('保存删除仓库配置失败:', error);
                this.showSnackbar('保存配置失败，请重试', 'error');
            });
        }
    }

    renderReposList() {
        this.renderReposListByType('github', this.elements.githubReposList);
        this.renderReposListByType('zip', this.elements.zipReposList);
    }

    renderReposListByType(type, container) {
        const repos = this.customRepos[type];
        
        if (repos.length === 0) {
            container.innerHTML = `
                <div class="empty-repos">
                    <span class="material-icons">folder_open</span>
                    <p>暂无${type === 'github' ? 'GitHub仓库' : 'ZIP清单库'}</p>
                </div>
            `;
            return;
        }
        
        container.innerHTML = repos.map((repo, index) => `
            <div class="repo-item" data-repo-type="${type}" data-repo-index="${index}">
                <div class="repo-info">
                    <div class="repo-name">${repo.name}</div>
                    <div class="repo-path">${type === 'github' ? repo.repo : repo.url}</div>
                </div>
                <div class="repo-actions">
                    <button class="btn-icon repo-delete-btn" title="删除">
                        <span class="material-icons">delete</span>
                    </button>
                </div>
            </div>
        `).join('');

        container.querySelectorAll('.repo-delete-btn').forEach((btn) => {
            btn.addEventListener('click', (event) => {
                event.stopPropagation();
                
                const repoItem = btn.closest('.repo-item');
                const repoType = repoItem.dataset.repoType;
                const repoIndex = parseInt(repoItem.dataset.repoIndex, 10);
                
                console.log(`删除仓库: ${repoType}[${repoIndex}]`);
                this.removeRepo(repoType, repoIndex);
            });
        });
    }

    async loadConfig() {
        try {
            const response = await fetch('/api/config/detailed');
            if (!response.ok) throw new Error(`Server responded with ${response.status}`);
            const data = await response.json();
            if (data.success) {
                this.elements.githubToken.value = data.config.github_token || '';
                this.elements.steamPath.value = data.config.steam_path || '';
                this.elements.debugMode.checked = data.config.debug_mode || false;
                this.elements.loggingFiles.checked = data.config.logging_files !== false;
                this.elements.disableLogging.checked = data.config.disable_logging || false;
                this.elements.showConsoleOnStartup.checked = data.config.show_console_on_startup || false;

                const forceUnlockerValue = data.config.force_unlocker_type || 'auto';
                this.elements.forceUnlockerRadios.forEach(radio => {
                    radio.checked = radio.value === forceUnlockerValue;
                });

                this.elements.autoInstallUnlocker.checked = data.config.auto_install_unlocker !== false;
                const prefValue = data.config.unlocker_preference || 'greenluma';
                this.elements.unlockerPrefRadios.forEach(radio => {
                    radio.checked = radio.value === prefValue;
                });
                this.elements.greenlumaRepo.value = data.config.greenluma_repo || '';
                this.elements.steamtoolsRepo.value = data.config.steamtools_repo || '';
                this.elements.opensteamtoolRepo.value = data.config.opensteamtool_repo || '';

                this.customRepos = data.config.custom_repos || { github: [], zip: [] };
                this.renderReposList();

                this.validateSteamPath(data.config.steam_path_is_auto || false);
            } else {
                this.showSnackbar(`加载配置失败: ${data.message}`, 'error');
            }
        } catch (error) {
            this.showSnackbar(`连接服务器时出错: ${error.message}`, 'error');
        }
    }

    async saveConfig() {
        const selectedUnlockerRadio = document.querySelector('input[name="forceUnlocker"]:checked');
        const forceUnlockerValue = selectedUnlockerRadio ? selectedUnlockerRadio.value : 'auto';

        const config = {
            github_token: this.elements.githubToken.value.trim(),
            steam_path: this.elements.steamPath.value.trim(),
            debug_mode: this.elements.debugMode.checked,
            logging_files: this.elements.loggingFiles.checked,
            disable_logging: this.elements.disableLogging.checked,
            show_console_on_startup: this.elements.showConsoleOnStartup.checked,
            force_unlocker_type: forceUnlockerValue,
            auto_install_unlocker: this.elements.autoInstallUnlocker.checked,
            unlocker_preference: (document.querySelector('input[name="unlockerPref"]:checked') || {}).value || 'greenluma',
            greenluma_repo: this.elements.greenlumaRepo.value.trim(),
            steamtools_repo: this.elements.steamtoolsRepo.value.trim(),
            opensteamtool_repo: this.elements.opensteamtoolRepo.value.trim(),
            custom_repos: this.customRepos,
        };

        try {
            const response = await fetch('/api/config/update', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(config),
            });
            if (!response.ok) throw new Error(`Server responded with ${response.status}`);
            const data = await response.json();
            if (data.success) {
                await this.loadConfig();
            }
            this.showSnackbar(data.message, data.success ? 'success' : 'error');
        } catch (error) {
            this.showSnackbar(`保存配置时出错: ${error.message}`, 'error');
        }
    }

    async resetConfig() {
        if (!confirm('您确定要将所有设置重置为默认值吗？此操作不可恢复。')) {
            return;
        }
        try {
            const response = await fetch('/api/config/reset', { method: 'POST' });
            if (!response.ok) throw new Error(`Server responded with ${response.status}`);
            const data = await response.json();
            if (data.success) {
                this.loadConfig();
            }
            this.showSnackbar(data.message, data.success ? 'success' : 'error');
        } catch (error) {
            this.showSnackbar(`重置配置时出错: ${error.message}`, 'error');
        }
    }
    
    showSnackbar(message, type = 'info') {
        this.elements.snackbarMessage.textContent = message;
        this.elements.snackbar.className = `snackbar ${type} show`;
        if (this.snackbarTimeout) clearTimeout(this.snackbarTimeout);
        this.snackbarTimeout = setTimeout(() => this.hideSnackbar(), 4000);
    }

    hideSnackbar() {
        this.elements.snackbar.classList.remove('show');
    }
}

let settingsManager;

document.addEventListener('DOMContentLoaded', () => {
    settingsManager = new SettingsManager();
});