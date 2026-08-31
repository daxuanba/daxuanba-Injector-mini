// 项目信息增强脚本
class AboutPageEnhancer {
    constructor() {
        this.initializeProjectInfo();
    }

    initializeProjectInfo() {
        this.addProjectLinkTracking();
        this.addVersionClickEaster();
        this.addLogoClickEffect();
    }

    addProjectLinkTracking() {
        const projectLinks = document.querySelectorAll('.project-link');
        projectLinks.forEach(link => {
            link.addEventListener('click', (e) => {
                console.log(`User clicked a project link.`);
                link.style.transform = 'scale(0.95)';
                setTimeout(() => {
                    link.style.transform = '';
                }, 150);
            });
        });
    }

    addVersionClickEaster() {
        const versionLabels = document.querySelectorAll('.version-label');
        let clickCount = 0;
        
        versionLabels.forEach(label => {
            label.addEventListener('click', () => {
                clickCount++;
                if (clickCount === 5) {
                    this.showEasterEgg();
                    clickCount = 0;
                }
                label.style.animation = 'pulse 0.3s ease';
                setTimeout(() => { label.style.animation = ''; }, 300);
            });
        });
    }

    addLogoClickEffect() {
        const logos = document.querySelectorAll('.project-logo');
        logos.forEach(logo => {
            logo.addEventListener('click', () => {
                logo.style.transform = 'rotate(360deg)';
                logo.style.transition = 'transform 0.6s ease';
                setTimeout(() => {
                    logo.style.transform = '';
                    logo.style.transition = '';
                }, 600);
                this.showTooltip(logo, '大轩巴入库器网页版 - 让 Steam 入库变得简单！');
            });
        });
    }

    showEasterEgg() {
        const messages = [
            '你发现了隐藏彩蛋！', '感谢你使用大轩巴入库器网页版！',
            '别忘了给项目点个 Star 哦！', '祝你游戏愉快！',
            '开源让世界更美好！', '一键入库，畅享游戏！'
        ];
        const randomMessage = messages[Math.floor(Math.random() * messages.length)];
        const easterEgg = document.createElement('div');
        easterEgg.textContent = randomMessage;
        easterEgg.style.cssText = `
            position: fixed; top: 50%; left: 50%;
            transform: translate(-50%, -50%);
            background: linear-gradient(135deg, #f1c40f, #d4a017); color: #111111;
            padding: 20px 30px; border-radius: 15px; font-size: 18px; font-weight: 600;
            box-shadow: 0 10px 30px rgba(0,0,0,0.4); z-index: 9999;
            animation: easterEggBounce 0.6s ease-out;
        `;
        if (!document.getElementById('easter-egg-styles')) {
            const style = document.createElement('style');
            style.id = 'easter-egg-styles';
            style.textContent = `
                @keyframes easterEggBounce {
                    0% { transform: translate(-50%, -50%) scale(0); opacity: 0; }
                    50% { transform: translate(-50%, -50%) scale(1.1); opacity: 1; }
                    100% { transform: translate(-50%, -50%) scale(1); opacity: 1; }
                }
                @keyframes pulse {
                    0% { transform: scale(1); }
                    50% { transform: scale(1.05); }
                    100% { transform: scale(1); }
                }
            `;
            document.head.appendChild(style);
        }
        document.body.appendChild(easterEgg);
        setTimeout(() => {
            easterEgg.style.animation = 'easterEggBounce 0.3s ease-in reverse';
            setTimeout(() => { if (easterEgg.parentNode) easterEgg.parentNode.removeChild(easterEgg); }, 300);
        }, 3000);
    }

    showTooltip(element, message) {
        const tooltip = document.createElement('div');
        tooltip.textContent = message;
        tooltip.style.cssText = `
            position: fixed; background-color: rgba(0, 0, 0, 0.8); color: white;
            padding: 8px 12px; border-radius: 6px; font-size: 12px;
            white-space: nowrap; z-index: 1000; opacity: 0;
            transition: opacity 0.3s ease; pointer-events: none;
        `;
        const rect = element.getBoundingClientRect();
        tooltip.style.left = (rect.left + rect.width / 2) + 'px';
        tooltip.style.top = (rect.top - 10) + 'px'; // Show above the element
        tooltip.style.transform = 'translate(-50%, -100%)';
        document.body.appendChild(tooltip);
        setTimeout(() => { tooltip.style.opacity = '1'; }, 10);
        setTimeout(() => {
            tooltip.style.opacity = '0';
            setTimeout(() => { if (tooltip.parentNode) tooltip.parentNode.removeChild(tooltip); }, 300);
        }, 2000);
    }
}
document.addEventListener('DOMContentLoaded', () => { new AboutPageEnhancer(); });