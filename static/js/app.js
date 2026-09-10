// --- START OF FILE static/js/app.js (MODIFIED WITH WORKSHOP SUPPORT AND DEPOTKEY PATCH) ---

class DxbWebApp {
    constructor() {
        this.socket = null;
        this.taskStatus = 'idle';
        this.unlockerType = null;
        this.currentAppId = null;
        this.pollTimeout = null;
        this.stAutoUpdateContext = null; 
        this.addAllDlcContext = null;
        this.patchDepotKeyContext = null; // NEW: 添加 depotkey修补上下文
        this.isWorkshopMode = false;
        this.initialize();
    }

    initialize() {
        this.elements = {
            configStatus: document.getElementById('configStatus'),
            unlockForm: document.getElementById('unlockForm'),
            unlockBtn: document.getElementById('unlockBtn'),
            resetBtn: document.getElementById('resetBtn'),
            restartSteamBtn: document.getElementById('restartSteamBtn'),
            appIdInput: document.getElementById('appId'),
            appIdLabel: document.getElementById('appIdLabel'),
            appIdHelper: document.getElementById('appIdHelper'),
            toolTypeGroup: document.getElementById('toolTypeGroup'),
            searchResultsContainer: document.getElementById('searchResultsContainer'),
            stAutoUpdateGroup: document.getElementById('stAutoUpdateGroup'),
            addAllDlcGroup: document.getElementById('addAllDlcGroup'),
            patchDepotKeyGroup: document.getElementById('patchDepotKeyGroup'), // NEW: 添加 depotkey修补组
            progressContainer: document.getElementById('progressContainer'),
            clearLogBtn: document.getElementById('clearLogBtn'),
            snackbar: document.getElementById('snackbar'),
            snackbarMessage: document.getElementById('snackbarMessage'),
            snackbarClose: document.getElementById('snackbarClose'),
            gameSearchForm: document.getElementById('gameSearchForm'),
            gameNameInput: document.getElementById('gameNameInput'),
            searchGameBtn: document.getElementById('searchGameBtn'),
            gameSearchResults: document.getElementById('gameSearchResults'),
            gameImageContainer: document.getElementById('gameImageContainer'),
            gameHeaderImage: document.getElementById('gameHeaderImage'),
            gameImagePlaceholder: document.getElementById('gameImagePlaceholder'),
            // 创意工坊相关元素
            workshopModeBtn: document.getElementById('workshopModeBtn'),
            unlockCardIcon: document.getElementById('unlockCardIcon'),
            unlockCardTitle: document.getElementById('unlockCardTitle'),
            modeIndicator: document.getElementById('modeIndicator'),
            gameModeOptions: document.getElementById('gameModeOptions'),
            workshopModeOptions: document.getElementById('workshopModeOptions'),
            // Steam 状态条元素
            steamPathText: document.getElementById('steamPathText'),
            steamKernelText: document.getElementById('steamKernelText'),
            steamToolsText: document.getElementById('steamToolsText'),
        };

        this.initializeSocket();
        this.initializeEventListeners();
        this.initializeBackend();
        this.setupMutationObserver();
    }

    initializeSocket() {
        this.socket = io();
        this.socket.on('connect', () => console.log('Connected to server.'));
        this.socket.on('disconnect', () => this.showSnackbar('Disconnected from server.', 'error'));
        this.socket.on('task_progress', (data) => this.addLogEntry(data.type, data.message));
    }

    initializeEventListeners() {
        this.elements.unlockForm.addEventListener('submit', (e) => {
            e.preventDefault();
            this.startUnlockTask();
        });

        this.elements.gameSearchForm.addEventListener('submit', (e) => {
            e.preventDefault();
            this.searchGame();
        });

        this.elements.gameSearchResults.addEventListener('click', (e) => {
            const previewBtn = e.target.closest('.preview-btn');
            const selectCopyBtn = e.target.closest('.select-copy-btn');
            if (previewBtn) {
                const appId = previewBtn.dataset.appid;
                this.previewGameImage(appId);
                this.showSnackbar(`正在预览游戏 AppID: ${appId}`, 'info');
            }
            if (selectCopyBtn) {
                const appId = selectCopyBtn.dataset.appid;
                this.elements.appIdInput.value = appId;
                navigator.clipboard.writeText(appId).then(() => {
                    this.showSnackbar(`AppID "${appId}" 已选择并复制`, 'success');
                }).catch(err => {
                    this.showSnackbar(`已选择 AppID "${appId}" (复制失败)`, 'warning');
                    console.error('复制失败:', err);
                });
                this.previewGameImage(appId);
                this.elements.appIdInput.focus();
            }
        });
        
        this.elements.restartSteamBtn.addEventListener('click', () => this.restartSteam());
        this.elements.resetBtn.addEventListener('click', () => this.resetForm());
        this.elements.clearLogBtn.addEventListener('click', () => this.clearLogs());
        this.elements.snackbarClose.addEventListener('click', () => this.hideSnackbar());

        // 创意工坊模式切换
        this.elements.workshopModeBtn.addEventListener('click', () => this.toggleWorkshopMode());

        this.elements.unlockForm.addEventListener('change', (event) => {
            if (event.target.name === 'toolType') {
                this.elements.searchResultsContainer.style.display = 'none';
                this.elements.searchResultsContainer.innerHTML = '';
            } else if (event.target.name === 'searchResult') {
                const originalToolType = document.querySelector('input[name="toolType"]:checked');
                if (originalToolType) originalToolType.checked = false;
            }
        });

        this.elements.searchResultsContainer.addEventListener('change', (event) => {
            if (event.target.name === 'searchResult') {
                const originalToolType = document.querySelector('input[name="toolType"]:checked');
                if (originalToolType) originalToolType.checked = false;
                this.elements.unlockBtn.disabled = false;
            }
        });
    }

    // 切换创意工坊模式
    toggleWorkshopMode() {
        this.isWorkshopMode = !this.isWorkshopMode;
        this.updateModeUI();
        this.resetForm();
    }

    // 更新界面根据当前模式
    updateModeUI() {
        const workshopBtn = this.elements.workshopModeBtn;
        const cardIcon = this.elements.unlockCardIcon;
        const cardTitle = this.elements.unlockCardTitle;
        const modeIndicator = this.elements.modeIndicator;
        const gameModeOptions = this.elements.gameModeOptions;
        const workshopModeOptions = this.elements.workshopModeOptions;
        const appIdLabel = this.elements.appIdLabel;
        const appIdHelper = this.elements.appIdHelper;
        const appIdInput = this.elements.appIdInput;

        if (this.isWorkshopMode) {
            // 切换到创意工坊模式
            workshopBtn.innerHTML = '<span class="material-icons">build_circle</span>游戏入库';
            workshopBtn.title = '切换到游戏入库模式';
            cardIcon.textContent = 'extension';
            cardTitle.textContent = '创意工坊资源下载';
            modeIndicator.style.display = 'block';
            gameModeOptions.style.display = 'none';
            workshopModeOptions.style.display = 'block';
            // 保持游戏搜索卡片始终显示
            appIdLabel.textContent = '创意工坊物品链接或ID';
            appIdHelper.textContent = '支持创意工坊链接或数字ID，例如: https://steamcommunity.com/sharedfiles/filedetails/?id=123456789';
            appIdInput.placeholder = '例如: 创意工坊链接或物品ID';
        } else {
            // 切换到游戏模式
            workshopBtn.innerHTML = '<span class="material-icons">extension</span>创意工坊资源下载';
            workshopBtn.title = '切换到创意工坊资源下载';
            cardIcon.textContent = 'build_circle';
            cardTitle.textContent = '游戏入库';
            modeIndicator.style.display = 'none';
            gameModeOptions.style.display = 'block';
            workshopModeOptions.style.display = 'none';
            // 保持游戏搜索卡片始终显示
            appIdLabel.textContent = 'App ID / 链接';
            appIdHelper.textContent = '请先通过左侧搜索或其它方式获取AppID。';
            appIdInput.placeholder = '例如: 730 或 Steam 链接';
        }
    }

    setupMutationObserver() {
        const observer = new MutationObserver((mutations) => {
            mutations.forEach((mutation) => {
                if (mutation.addedNodes.length) this.enableSearchResultInputs();
            });
        });
        observer.observe(this.elements.searchResultsContainer, { childList: true });
    }

    enableSearchResultInputs() {
        const inputs = this.elements.searchResultsContainer.querySelectorAll('input[name="searchResult"]');
        inputs.forEach(el => { el.disabled = false; });
        this.elements.unlockBtn.disabled = false;
        this.elements.unlockBtn.innerHTML = `<span class="material-icons">play_arrow</span> 开始任务`;
    }

    async initializeBackend() {
        try {
            const response = await fetch('/api/initialize', { method: 'POST' });
            if (!response.ok) throw new Error(`Server responded with ${response.status}`);
            const data = await response.json();

            if (data.success) {
                this.unlockerType = data.unlocker_type;
                this.elements.configStatus.innerHTML = this.generateConfigStatusHTML(data);
                this.elements.unlockBtn.disabled = false;
                
                const showStOptions = this.unlockerType === 'steamtools';
                this.elements.stAutoUpdateGroup.style.display = showStOptions ? 'block' : 'none';
                this.elements.addAllDlcGroup.style.display = showStOptions ? 'block' : 'none';
                this.elements.patchDepotKeyGroup.style.display = showStOptions ? 'block' : 'none'; // NEW: 显示depotkey修补选项
                
                await this.loadSources();
                this.loadSteamStatus();
            } else {
                this.elements.configStatus.innerHTML = `<div class="status-item error"><span class="material-icons status-icon">error</span><span class="status-text">后端错误: ${data.message}</span></div>`;
            }
        } catch (error) {
            this.elements.configStatus.innerHTML = `<div class="status-item error"><span class="material-icons status-icon">error</span><span class="status-text">无法连接到后端: ${error.message}</span></div>`;
        }
    }

    generateConfigStatusHTML(config) {
        const items = [];
        const unlockerStatusMap = {
            'steamtools': { class: 'success', text: '已检测到 SteamTools', icon: 'check_circle' },
            'greenluma': { class: 'success', text: '已检测到 GreenLuma', icon: 'check_circle' },
            'conflict': { class: 'error', text: '冲突: 同时检测到两种工具!', icon: 'error' },
            'none': { class: 'warning', text: '未检测到解锁工具。', icon: 'warning' },
        };
        const status = unlockerStatusMap[config.unlocker_type] || unlockerStatusMap.none;
        items.push(`<div class="status-item ${status.class}"><span class="material-icons status-icon">${status.icon}</span><span class="status-text">${status.text}</span></div>`);
        const steamPathStatus = config.steam_path !== 'Not Found' ? { class: 'success', text: `Steam 路径: ${config.steam_path}`, icon: 'check_circle' } : { class: 'error', text: '未找到 Steam 路径!', icon: 'error' };
        items.push(`<div class="status-item ${steamPathStatus.class}"><span class="material-icons status-icon">${steamPathStatus.icon}</span><span class="status-text">${steamPathStatus.text}</span></div>`);
        return items.join('');
    }

    // FIXED: 修复后的 loadSources 方法，从后端获取包含自定义仓库的完整源列表
    async loadSources() {
        try {
            // 显示加载状态
            this.elements.toolTypeGroup.innerHTML = '<div class="loading">正在加载清单源...</div>';
            
            // 从后端获取所有可用的源（包括自定义仓库）
            const response = await fetch('/api/sources');
            if (!response.ok) throw new Error(`Server responded with ${response.status}`);
            
            const data = await response.json();
            if (data.success) {
                this.renderSourceList(data.sources, data.recommended);
                // 如果有自定义仓库，显示提示信息
                const customCount = (data.custom_github_count || 0) + (data.custom_zip_count || 0);
                if (customCount > 0) {
                    console.log(`已加载 ${customCount} 个自定义清单源`);
                    this.showSnackbar(`已加载 ${customCount} 个自定义清单源`, 'success');
                }
                if (data.recommended) {
                    this.showSnackbar('已自动选择最优可用清单源', 'info');
                }
            } else {
                throw new Error(data.message || '获取清单源失败');
            }
        } catch (error) {
            console.error('加载清单源失败:', error);
            // 回退到硬编码的内置源
            const fallbackSources = {
                "自动搜索GitHub": "search",
                "SWA V2": "printedwaste",
                "Cysaw": "cysaw",
                "Furcate": "furcate",
                "Walftech": "walftech",
                "steamdatabase": "steamdatabase",
                "GitHub (Auiowu)": "Auiowu/ManifestAutoUpdate",
                "GitHub (SAC)": "SteamAutoCracks/ManifestHub",
                "SteamAutoCracks/ManifestHub(2) （仅密钥）": "steamautocracks_v2",
                "Sudama库 (仅密钥)": "sudama",
                "GitHub (ikun0014/ManifestHub)": "ikun0014/ManifestHub",
                "GitHub (Masaiki/ManifestAutoUpdate)": "Masaiki/ManifestAutoUpdate",
                "GitHub (wxy1343/ManifestAutoUpdate)": "wxy1343/ManifestAutoUpdate",
                "GitHub (Cyberbolt/ManifestAutoUpdate)": "Cyberbolt/ManifestAutoUpdate",
                "GitHub (Fairyvmos/bruh-hub)": "Fairyvmos/bruh-hub",
                "GitHub (Cracko298/ManifestHub)": "Cracko298/ManifestHub",
            };
            this.renderSourceList(fallbackSources, 'search');
            this.showSnackbar('加载自定义清单源失败，使用默认源', 'warning');
        }
    }

    renderSourceList(sources, recommended) {
        const entries = Object.entries(sources);
        const VISIBLE = 6;
        let html = '';
        entries.forEach(([name, value], idx) => {
            const hidden = idx >= VISIBLE ? ' style="display:none;"' : '';
            const isRec = recommended && value === recommended;
            const checked = isRec ? 'checked' : (!recommended && idx === 0 ? 'checked' : '');
            const badge = isRec ? ' <span class="recommended-badge">推荐</span>' : '';
            html += `<label class="radio-item${isRec ? ' rec' : ''}"${hidden}>
                <input type="radio" name="toolType" value="${value}" ${checked}>
                <span class="radio-button"></span>
                <span class="radio-label">${name}${badge}</span>
            </label>`;
        });
        if (entries.length > VISIBLE) {
            html += `<button type="button" class="btn btn-text more-sources-btn" id="moreSourcesBtn"><span class="material-icons">expand_more</span> 更多清单源</button>`;
        }
        this.elements.toolTypeGroup.innerHTML = html;
        const moreBtn = document.getElementById('moreSourcesBtn');
        if (moreBtn) {
            moreBtn.addEventListener('click', () => {
                const items = this.elements.toolTypeGroup.querySelectorAll('.radio-item');
                const anyHidden = Array.from(items).some(el => el.style.display === 'none');
                items.forEach(el => { el.style.display = ''; });
                if (anyHidden) {
                    moreBtn.innerHTML = '<span class="material-icons">expand_less</span> 收起';
                } else {
                    items.forEach((el, i) => { if (i >= VISIBLE) el.style.display = 'none'; });
                    moreBtn.innerHTML = '<span class="material-icons">expand_more</span> 更多清单源';
                }
            });
        }
    }

    // 首页 Steam 状态条：位置 + 内核 + SteamTools
    async loadSteamStatus() {
        try {
            const response = await fetch('/api/steam_status');
            const data = await response.json();
            if (!data.success) return;
            const st = data;
            this.elements.steamPathText.textContent = st.exists
                ? `Steam: ${st.steam_path}`
                : 'Steam: 未检测到';
            const kernelMap = {
                'opensteamtool': { t: '内核: OpenSteamTool（清单导入）', c: 'ok' },
                'steamtools': { t: '内核: SteamTools（稳定入库）', c: 'ok' },
                'none': { t: '内核: 未安装', c: 'warn' },
            };
            const k = kernelMap[st.kernel] || kernelMap['none'];
            this.elements.steamKernelText.textContent = k.t;
            this.elements.steamKernelText.className = `steam-status-text ${k.c}`;
            this.elements.steamToolsText.textContent = `SteamTools: ${st.steamtools ? '已检测' : '未检测'}`;
            this.elements.steamToolsText.className = `steam-status-text ${st.steamtools ? 'ok' : ''}`;
        } catch (e) {
            this.elements.steamPathText.textContent = 'Steam: 检测失败';
        }
    }

    async searchGame() {
        const gameName = this.elements.gameNameInput.value.trim();
        if (!gameName) { this.showSnackbar('请输入游戏名称。', 'error'); return; }
        this.elements.searchGameBtn.disabled = true;
        this.elements.searchGameBtn.innerHTML = `<span class="material-icons spin">hourglass_top</span> 搜索中...`;
        this.elements.gameSearchResults.innerHTML = `<div class="loading">正在搜索...</div>`;
        try {
            const response = await fetch('/api/search_game', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ game_name: gameName }), });
            const data = await response.json();
            if (data.success) { this.displayGameResults(data.games); } else { throw new Error(data.message); }
        } catch(error) {
            this.elements.gameSearchResults.innerHTML = `<div class="status-item error">${error.message}</div>`;
        } finally {
            this.elements.searchGameBtn.disabled = false;
            this.elements.searchGameBtn.innerHTML = `<span class="material-icons">search</span> 搜索`;
        }
    }

    displayGameResults(games) {
        if (!games || games.length === 0) { this.elements.gameSearchResults.innerHTML = `<div class="status-item warning">未找到相关游戏。</div>`; return; }
        let html = games.map(game => `
            <div class="search-result-item">
                <img class="search-result-thumb" loading="lazy"
                     src="https://cdn.akamai.steamstatic.com/steam/apps/${game.appid}/capsule_184x69.jpg"
                     onerror="this.style.display='none'"/>
                <div class="search-result-info">
                    <span class="name">${game.name}</span>
                    <span class="appid">AppID: ${game.appid}</span>
                </div>
                <button class="preview-btn" data-appid="${game.appid}" title="预览图片">
                    <span class="material-icons">image</span>
                </button>
                <button class="select-copy-btn" data-appid="${game.appid}" title="选择并复制 AppID">
                    <span class="material-icons">content_copy</span>
                </button>
            </div>
        `).join('');
        this.elements.gameSearchResults.innerHTML = html;
    }

    setImageState(showImage) {
        this.elements.gameImagePlaceholder.style.display = showImage ? 'none' : 'flex';
        this.elements.gameHeaderImage.style.display = showImage ? 'block' : 'none';
    }

    previewGameImage(appId) {
        const numericAppId = appId.match(/\d+/)?.[0];
        if (numericAppId) {
            this.setImageState(false);
            const imageUrl = `https://cdn.akamai.steamstatic.com/steam/apps/${numericAppId}/header.jpg`;
            const img = this.elements.gameHeaderImage;
            img.onload = () => this.setImageState(true);
            img.onerror = () => { this.setImageState(false); this.showSnackbar('无法加载游戏图片。', 'warning'); };
            img.src = imageUrl;
        } else { this.setImageState(false); }
    }
    
    async restartSteam() {
        const btn = this.elements.restartSteamBtn;
        const originalContent = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = `<span class="material-icons spin">hourglass_top</span> 正在请求...`;
        try {
            const response = await fetch('/api/steam/restart', { method: 'POST' });
            const data = await response.json();
            this.showSnackbar(data.message, data.success ? 'success' : 'error');
        } catch (error) {
            this.showSnackbar(`请求重启 Steam 时出错: ${error.message}`, 'error');
        } finally {
            setTimeout(() => { btn.disabled = false; btn.innerHTML = originalContent; }, 1000);
        }
    }

    async startUnlockTask() {
        if (this.taskStatus === 'running') { this.showSnackbar('一个任务正在运行中，请稍候。', 'warning'); return; }
    
        const formData = new FormData(this.elements.unlockForm);
        this.currentAppId = this.elements.appIdInput.value.trim();
        
        if (!this.currentAppId) { 
            const errorMsg = this.isWorkshopMode ? '请输入创意工坊物品链接或ID。' : '请输入 App ID 或链接。';
            this.showSnackbar(errorMsg, 'error'); 
            return; 
        }

        // 根据模式处理不同的任务类型
        if (this.isWorkshopMode) {
            await this.startWorkshopTask(formData);
        } else {
            await this.startGameTask(formData);
        }
    }

    // 处理创意工坊资源下载任务
    async startWorkshopTask(formData) {
        const downloadResources = formData.get('workshopDownloadResources') === 'on';
        const copyToDepot = formData.get('workshopCopyToDepot') === 'on';

        if (!downloadResources && !copyToDepot) {
            this.showSnackbar('请至少选择一个操作。', 'error');
            return;
        }

        this.taskStatus = 'running';
        this.setFormDisabled(true);
        this.elements.progressContainer.innerHTML = '';
        this.addLogEntry('info', `--- 开始下载创意工坊资源: '${this.currentAppId}' ---`);

        try {
            // 下载前先检测物品是否存在，避免无效下载
            this.addLogEntry('info', '正在检测创意工坊物品是否存在...');
            const checkResp = await fetch('/api/workshop/check', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ workshop_input: this.currentAppId }),
            });
            const checkData = await checkResp.json();
            if (!checkData.success || !checkData.exists) {
                const reason = (checkData.reason) || (checkData.message) || '物品不存在';
                this.addLogEntry('error', `检测失败: ${reason}`);
                this.showSnackbar(`创意工坊物品不存在: ${reason}`, 'error');
                this.taskStatus = 'idle';
                this.setFormDisabled(false);
                return;
            }
            this.addLogEntry('info', `物品存在: ${checkData.title}`);
            if (checkData.local_exists) {
                this.addLogEntry('warning', '该物品已在本地存在，将覆盖更新。');
            }

            const response = await fetch('/api/workshop/start_task', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    workshop_input: this.currentAppId,
                    download_resources: downloadResources,
                    copy_to_depot: copyToDepot,
                }),
            });
            const data = await response.json();
            if (data.success) {
                this.showSnackbar('创意工坊资源下载已开始。', 'info');
                this.startStatusPolling();
            } else { 
                throw new Error(data.message); 
            }
        } catch (error) {
            this.taskStatus = 'idle';
            this.setFormDisabled(false);
            this.showSnackbar(`启动创意工坊资源下载失败: ${error.message}`, 'error');
            this.addLogEntry('error', `启动创意工坊资源下载失败: ${error.message}`);
        }
    }

    // 原有的游戏任务处理逻辑
    async startGameTask(formData) {
        let toolType = formData.get('toolType');
        let useStAutoUpdate;
        let addAllDlc;
        let patchDepotKey; // NEW: 添加 depotkey修补参数

        const searchResultChoice = document.querySelector('input[name="searchResult"]:checked');
        if (searchResultChoice) {
            toolType = searchResultChoice.value;
            useStAutoUpdate = this.stAutoUpdateContext;
            addAllDlc = this.addAllDlcContext;
            patchDepotKey = this.patchDepotKeyContext; // NEW: 从上下文获取
        } else {
            useStAutoUpdate = formData.get('stAutoUpdate') === 'on';
            addAllDlc = formData.get('addAllDlc') === 'on';
            patchDepotKey = formData.get('patchDepotKey') === 'on'; // NEW: 从表单获取
        }

        if (!toolType) { this.showSnackbar('请选择一个清单源。', 'error'); return; }

        const appIdMatch = this.currentAppId.match(/(?:\/app\/|\b)(\d+)\b/);
        const numericAppId = appIdMatch ? appIdMatch[1] : (this.currentAppId.match(/^\d+$/) ? this.currentAppId : null);
        this.previewGameImage(numericAppId || this.currentAppId);
    
        this.taskStatus = 'running';
        this.setFormDisabled(true);
    
        if (toolType !== 'search') {
            this.elements.searchResultsContainer.style.display = 'none';
            this.elements.searchResultsContainer.innerHTML = '';
        }
        
        this.elements.progressContainer.innerHTML = '';
        this.addLogEntry('info', `--- 开始为 '${this.currentAppId}' 执行任务 (源: ${toolType}) ---`);
    
        try {
            const response = await fetch('/api/start_task', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    app_id: this.currentAppId,
                    tool_type: toolType,
                    use_st_auto_update: useStAutoUpdate,
                    add_all_dlc: addAllDlc,
                    patch_depot_key: patchDepotKey, // NEW: 传递depotkey修补参数
                }),
            });
            const data = await response.json();
            if (data.success) {
                this.showSnackbar('任务已开始。', 'info');
                this.startStatusPolling();
            } else { throw new Error(data.message); }
        } catch (error) {
            this.taskStatus = 'idle';
            this.setFormDisabled(false);
            this.showSnackbar(`启动任务失败: ${error.message}`, 'error');
            this.addLogEntry('error', `启动任务失败: ${error.message}`);
        }
    }

    startStatusPolling() {
        const maxPollDuration = 300000;
        let pollStartTime = Date.now();
        const pollInterval = setInterval(async () => {
            try {
                const response = await fetch('/api/task_status', { timeout: 10000 });
                const data = await response.json();
                if (data.status === 'completed' || data.status === 'error') {
                    clearInterval(pollInterval);
                    clearTimeout(this.pollTimeout);
                    this.taskStatus = 'idle';
                    if (data.result?.action_required === 'select_source') { this.handleSourceSelection(data.result); } 
                    else { 
                        this.stAutoUpdateContext = null; 
                        this.addAllDlcContext = null; 
                        this.patchDepotKeyContext = null; // NEW: 清空depotkey上下文
                        this.setFormDisabled(false); 
                    }
                    if (data.result?.message) { this.showSnackbar(data.result.message, data.result.success ? 'success' : 'error'); }
                    this.addLogEntry(data.result?.success ? 'info' : 'error', `--- 任务结束 ---`);
                }
                if (Date.now() - pollStartTime > maxPollDuration) {
                    clearInterval(pollInterval); clearTimeout(this.pollTimeout); this.taskStatus = 'idle'; this.setFormDisabled(false);
                    this.stAutoUpdateContext = null; this.addAllDlcContext = null; this.patchDepotKeyContext = null; // NEW: 清空上下文
                    this.showSnackbar('任务超时，请检查网络或重试。', 'error'); this.addLogEntry('error', '任务超时，可能由于网络问题或服务器无响应。');
                }
            } catch (error) {
                console.error('Status polling error:', error);
                clearInterval(pollInterval); clearTimeout(this.pollTimeout); this.taskStatus = 'idle'; this.setFormDisabled(false);
                this.stAutoUpdateContext = null; this.addAllDlcContext = null; this.patchDepotKeyContext = null; // NEW: 清空上下文
                this.showSnackbar(`轮询状态失败: ${error.message}`, 'error'); this.addLogEntry('error', `轮询状态失败: ${error.message}`);
            }
        }, 1500);

        this.pollTimeout = setTimeout(() => {
            clearInterval(pollInterval); this.taskStatus = 'idle'; this.setFormDisabled(false);
            this.stAutoUpdateContext = null; this.addAllDlcContext = null; this.patchDepotKeyContext = null; // NEW: 清空上下文
            this.showSnackbar('任务超时，请检查网络或重试。', 'error'); this.addLogEntry('error', '任务超时，可能由于网络问题或服务器无响应。');
        }, maxPollDuration);
    }

    handleSourceSelection(result) {
        const sources = result.sources;
        this.stAutoUpdateContext = result.context?.use_st_auto_update ?? false;
        this.addAllDlcContext = result.context?.add_all_dlc ?? false;
        this.patchDepotKeyContext = result.context?.patch_depot_key ?? false; // NEW: 保存depotkey上下文
        
        let html = '<label class="input-label">请从搜索结果中选择一个源:</label>';
        sources.forEach((source, index) => {
            const updateDate = new Date(source.update_date).toLocaleString('zh-CN');
            html += `<label class="radio-item-detailed"> <input type="radio" name="searchResult" value="${source.repo}" class="visually-hidden" ${index === 0 ? 'checked' : ''} disabled> <div class="radio-button-wrapper"> <span class="radio-button"></span> <div class="radio-label-group"> <span class="radio-label">${source.repo}</span> <span class="radio-date">最后更新: ${updateDate}</span> </div> </div> </label>`;
        });
        
        this.elements.searchResultsContainer.innerHTML = html;
        this.elements.searchResultsContainer.style.display = 'flex';
        this.elements.unlockBtn.innerHTML = `<span class="material-icons spin">hourglass_top</span> 等待选择...`;
        this.elements.unlockBtn.disabled = true;
    }

    clearLogs() {
        this.elements.progressContainer.innerHTML = `<div class="progress-placeholder"> <span class="material-icons">info</span> <p>等待任务开始...</p> </div>`;
    }

    addLogEntry(type, message) {
        const placeholder = this.elements.progressContainer.querySelector('.progress-placeholder');
        if (placeholder) { this.elements.progressContainer.innerHTML = ''; }
        const div = document.createElement('div');
        div.className = `log-entry ${type}`;
        div.textContent = `[${new Date().toLocaleTimeString()}] ${message}`;
        this.elements.progressContainer.appendChild(div);
        this.elements.progressContainer.scrollTop = this.elements.progressContainer.scrollHeight;
    }

    setFormDisabled(disabled) {
        this.elements.unlockBtn.disabled = disabled;
        this.elements.resetBtn.disabled = disabled;
        this.elements.appIdInput.disabled = disabled;
        
        const allRadios = this.elements.unlockForm.querySelectorAll('input[type="radio"]');
        allRadios.forEach(radio => radio.disabled = disabled);

        const allCheckboxes = this.elements.unlockForm.querySelectorAll('input[type="checkbox"]');
        allCheckboxes.forEach(checkbox => checkbox.disabled = disabled);

        // 在任务运行时禁用模式切换按钮
        if (this.elements.workshopModeBtn) {
            this.elements.workshopModeBtn.disabled = disabled;
        }
    }

    showSnackbar(message, type = 'info') {
        this.elements.snackbarMessage.textContent = message;
        this.elements.snackbar.className = `snackbar show ${type}`;
        setTimeout(() => this.hideSnackbar(), 5000);
    }

    hideSnackbar() {
        this.elements.snackbar.classList.remove('show');
    }

    resetForm() {
        this.elements.unlockForm.reset();
        this.elements.searchResultsContainer.innerHTML = '';
        this.elements.searchResultsContainer.style.display = 'none';
        this.setFormDisabled(false);
        this.currentAppId = null;
        this.stAutoUpdateContext = null; 
        this.addAllDlcContext = null;
        this.patchDepotKeyContext = null; // NEW: 重置depotkey上下文
        this.setImageState(false);
        
        // 重置时也更新界面状态
        this.updateModeUI();
    }
}

document.addEventListener('DOMContentLoaded', () => {
    new DxbWebApp();
});