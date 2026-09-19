// Pristmax Desktop - Main Process Handler
// This file runs in the renderer process

(function() {
    'use strict';

    // 等待 DOM 加载完成
    document.addEventListener('DOMContentLoaded', function() {
        initWindowControls();
        initNavigation();
        initQuickActions();
        initScanButton();
    });

    // 窗口控制
    function initWindowControls() {
        const btnMinimize = document.getElementById('btn-minimize');
        const btnMaximize = document.getElementById('btn-maximize');
        const btnClose = document.getElementById('btn-close');

        if (btnMinimize) {
            btnMinimize.addEventListener('click', () => {
                window.electronAPI?.minimize();
            });
        }

        if (btnMaximize) {
            btnMaximize.addEventListener('click', () => {
                window.electronAPI?.maximize();
            });
        }

        if (btnClose) {
            btnClose.addEventListener('click', () => {
                window.electronAPI?.close();
            });
        }
    }

    // 导航
    function initNavigation() {
        const navItems = document.querySelectorAll('.nav-item');
        navItems.forEach(item => {
            item.addEventListener('click', function(e) {
                e.preventDefault();
                const href = this.getAttribute('href');
                if (href) {
                    // 移除所有 active
                    navItems.forEach(n => n.classList.remove('active'));
                    // 添加当前 active
                    this.classList.add('active');
                    // 更新顶部标题
                    updateTopBar(this.querySelector('span')?.textContent || 'Dashboard');
                }
            });
        });
    }

    // 更新顶部栏
    function updateTopBar(title) {
        const breadcrumb = document.querySelector('.top-bar-breadcrumb span');
        if (breadcrumb) {
            breadcrumb.textContent = title;
        }
    }

    // 快速操作
    function initQuickActions() {
        const actions = document.querySelectorAll('.quick-action, .nav-item');
        actions.forEach(action => {
            action.addEventListener('click', function() {
                const id = this.id || this.getAttribute('href');
                if (id === 'action-scan' || id === '#files') {
                    handleScanAction();
                } else if (id === 'action-duplicates' || id === '#duplicates') {
                    handleDuplicatesAction();
                } else if (id === 'action-large' || id === '#large') {
                    handleLargeFilesAction();
                }
            });
        });
    }

    // 扫描按钮
    function initScanButton() {
        const btnScan = document.getElementById('btn-scan');
        if (btnScan) {
            btnScan.addEventListener('click', handleScanAction);
        }

        const btnNewTask = document.getElementById('btn-new-task');
        if (btnNewTask) {
            btnNewTask.addEventListener('click', handleNewTaskAction);
        }
    }

    // 处理扫描操作
    async function handleScanAction() {
        try {
            const directory = await window.electronAPI?.selectDirectory();
            if (directory) {
                console.log('Selected directory:', directory);
                updateStatus('正在扫描...');
                // TODO: 调用 Storage Agent 分析目录
                setTimeout(() => {
                    updateMetrics({
                        totalFiles: 12847,
                        totalSize: 128.5,
                        saved: 12.3,
                        percent: 9.6
                    });
                    updateStatus('扫描完成');
                }, 1500);
            }
        } catch (e) {
            console.error('Scan error:', e);
            updateStatus('扫描失败');
        }
    }

    // 处理重复文件操作
    async function handleDuplicatesAction() {
        updateStatus('正在查找重复文件...');
        // TODO: 实现重复文件检测
        setTimeout(() => {
            updateStatus('找到 5 组重复文件');
        }, 1500);
    }

    // 处理大文件操作
    async function handleLargeFilesAction() {
        updateStatus('正在分析大文件...');
        // TODO: 实现大文件分析
        setTimeout(() => {
            updateStatus('分析完成');
        }, 1500);
    }

    // 处理新建任务
    function handleNewTaskAction() {
        const navItems = document.querySelectorAll('.nav-item');
        navItems.forEach(n => n.classList.remove('active'));
        const tasksNav = document.querySelector('a[href="#tasks"]');
        if (tasksNav) tasksNav.classList.add('active');
        updateTopBar('新建任务');
        updateStatus('准备创建新任务');
    }

    // 更新指标显示
    function updateMetrics(data) {
        const metrics = document.querySelectorAll('.metric-card');
        if (metrics[0]) {
            metrics[0].querySelector('.metric-value').innerHTML =
                `${data.totalFiles.toLocaleString()} <span class="unit">文件</span>`;
        }
        if (metrics[1]) {
            metrics[1].querySelector('.metric-value').innerHTML =
                `${data.totalSize} <span class="unit">GB</span>`;
        }
        if (metrics[2]) {
            metrics[2].querySelector('.metric-value').innerHTML =
                `${data.saved} <span class="unit">GB</span>`;
        }
        if (metrics[3]) {
            metrics[3].querySelector('.metric-value').innerHTML =
                `${data.percent} <span class="unit">%</span>`;
        }
    }

    // 更新状态栏
    function updateStatus(message) {
        const statusItem = document.querySelector('.status-item span:last-child');
        if (statusItem) {
            statusItem.textContent = message;
        }
    }

    // 监听 Electron API 事件
    if (window.electronAPI) {
        window.electronAPI.onDirectorySelected((path) => {
            console.log('Directory selected from menu:', path);
            handleScanAction();
        });
    }
})();
