// Pristmax Desktop - Frontend Logic
(function() {
    'use strict';

    let currentPath = null;
    let currentPage = 'overview';
    let scanResults = null;

    // Initialize
    document.addEventListener('DOMContentLoaded', function() {
        initWindowControls();
        initSidebar();
        initActions();
        initPathSelector();
        initUpdateCheck();
        loadDemoData();
    });

    // Window Controls
    function initWindowControls() {
        const btnMin = document.getElementById('btn-minimize');
        const btnMax = document.getElementById('btn-maximize');
        const btnClose = document.getElementById('btn-close');

        if (btnMin) btnMin.addEventListener('click', () => window.electronAPI?.minimize());
        if (btnMax) btnMax.addEventListener('click', () => window.electronAPI?.maximize());
        if (btnClose) btnClose.addEventListener('click', () => window.electronAPI?.close());
    }

    // Sidebar Navigation
    function initSidebar() {
        const icons = document.querySelectorAll('.sidebar-icon');
        icons.forEach(icon => {
            icon.addEventListener('click', function() {
                icons.forEach(i => i.classList.remove('active'));
                this.classList.add('active');

                const page = this.dataset.page;
                currentPage = page;
                updatePageTitle(page);
                showPage(page);
            });
        });
    }

    function updatePageTitle(page) {
        const titles = {
            'overview': '概览',
            'files': '文件分析',
            'duplicates': '重复文件',
            'large': '大文件',
            'tasks': '任务',
            'reports': '报告',
            'settings': '设置'
        };
        document.getElementById('page-title').textContent = titles[page] || '概览';
    }

    function showPage(page) {
        // Hide all pages first
        document.querySelectorAll('.page-content').forEach(p => p.style.display = 'none');

        // Show selected page
        const pageEl = document.getElementById('page-' + page);
        if (pageEl) pageEl.style.display = 'flex';

        // Update content based on page
        if (page === 'duplicates' && scanResults) {
            showDuplicatesPage();
        } else if (page === 'large' && scanResults) {
            showLargeFilesPage();
        }
    }

    // Actions
    function initActions() {
        document.getElementById('btn-scan')?.addEventListener('click', selectAndScan);
        document.getElementById('action-scan-dir')?.addEventListener('click', selectAndScan);
        document.getElementById('action-find-dup')?.addEventListener('click', function() {
            if (!currentPath) {
                showNotification('请先选择文件夹');
                return;
            }
            navigateTo('duplicates');
        });
        document.getElementById('action-find-large')?.addEventListener('click', function() {
            if (!currentPath) {
                showNotification('请先选择文件夹');
                return;
            }
            navigateTo('large');
        });

        // Task actions
        document.getElementById('btn-new-task')?.addEventListener('click', function() {
            navigateTo('tasks');
            showNotification('新建任务功能开发中...');
        });
    }

    function navigateTo(page) {
        document.querySelectorAll('.sidebar-icon').forEach(icon => {
            icon.classList.toggle('active', icon.dataset.page === page);
        });
        currentPage = page;
        updatePageTitle(page);
        showPage(page);
    }

    // Load demo data for display
    function loadDemoData() {
        scanResults = {
            totalFiles: 12847,
            totalSize: 128.5 * 1024 * 1024 * 1024, // bytes
            duplicates: 5,
            duplicateSize: 4.2 * 1024 * 1024 * 1024,
            largeFiles: [
                { name: 'video_archive_2024.mp4', size: 2.8 * 1024**3, path: '/data/video_archive_2024.mp4' },
                { name: 'database_backup.sql', size: 1.5 * 1024**3, path: '/data/database_backup.sql' },
                { name: 'ubuntu-22.04.iso', size: 890 * 1024**2, path: '/data/ubuntu-22.04.iso' },
                { name: 'photos_archive.zip', size: 650 * 1024**2, path: '/data/photos_archive.zip' },
                { name: 'project_videos.mp4', size: 420 * 1024**2, path: '/data/project_videos.mp4' }
            ],
            byCategory: {
                video: 45 * 1024**3,
                image: 25 * 1024**3,
                document: 12 * 1024**3,
                code: 8 * 1024**3,
                other: 38.5 * 1024**3
            },
            duplicateGroups: [
                { name: 'operations.csv', count: 8, size: 120 * 1024**2, wasted: 105 * 1024**2 },
                { name: 'backup_2024.zip', count: 3, size: 800 * 1024**2, wasted: 600 * 1024**2 },
                { name: 'report.docx', count: 5, size: 50 * 1024**2, wasted: 40 * 1024**2 },
                { name: 'data_export.xlsx', count: 4, size: 30 * 1024**2, wasted: 22 * 1024**2 },
                { name: 'image_assets.png', count: 6, size: 180 * 1024**2, wasted: 150 * 1024**2 }
            ]
        };

        updateMetricsDisplay();
    }

    function updateMetricsDisplay() {
        if (!scanResults) return;

        document.getElementById('metric-files').textContent = scanResults.totalFiles.toLocaleString();
        document.getElementById('metric-size').innerHTML = `${(scanResults.totalSize / 1024**3).toFixed(1)} <span class="unit">GB</span>`;
        document.getElementById('metric-duplicates').textContent = scanResults.duplicates;
        document.getElementById('metric-savings').innerHTML = `${(scanResults.duplicateSize / 1024**3).toFixed(1)} <span class="unit">GB</span>`;

        // Update storage bars
        const maxSize = Math.max(...Object.values(scanResults.byCategory), 1);
        const cats = ['video', 'image', 'doc', 'code', 'other'];
        cats.forEach((cat, i) => {
            const size = scanResults.byCategory[cat] || 0;
            const pct = (size / maxSize * 100).toFixed(0);
            document.querySelectorAll('.storage-fill')[i].style.width = pct + '%';
            document.getElementById('size-' + cat).textContent = formatSize(size);
        });
    }

    // Path Selector
    function initPathSelector() {
        document.getElementById('path-selector')?.addEventListener('click', selectAndScan);
    }

    // Select directory and scan
    async function selectAndScan() {
        updateStatus('正在选择文件夹...');
        try {
            const path = await window.electronAPI?.selectDirectory();
            if (path) {
                currentPath = path;
                document.getElementById('current-path').textContent = path;
                updateStatus('正在扫描...');

                // Simulate scan delay
                setTimeout(() => {
                    performScan(path);
                }, 500);
            } else {
                updateStatus('已取消');
            }
        } catch (e) {
            console.error('Select directory error:', e);
            updateStatus('选择文件夹失败');
        }
    }

    async function performScan(path) {
        try {
            const items = await window.electronAPI?.readDirectory(path);
            if (items && items.length > 0) {
                // Calculate real stats
                const stats = calculateStats(items);
                scanResults = stats;
                displayFiles(items);
                updateMetricsDisplay();
                updateStatus(`扫描完成: ${items.length} 个项目`);
                showNotification(`扫描完成！找到 ${stats.totalFiles} 个文件`);
            } else {
                updateStatus('文件夹为空');
                showNotification('选择的文件夹为空');
            }
        } catch (e) {
            console.error('Scan error:', e);
            updateStatus('扫描失败');
            showNotification('扫描失败: ' + e.message);
        }
    }

    function calculateStats(items) {
        const result = {
            totalFiles: 0,
            totalSize: 0,
            duplicates: 0,
            duplicateSize: 0,
            largeFiles: [],
            byCategory: { video: 0, image: 0, doc: 0, code: 0, other: 0 },
            duplicateGroups: []
        };

        const sizeMap = {};
        const extMap = {};

        items.forEach(item => {
            if (item.isDirectory) return;
            result.totalFiles++;
            result.totalSize += item.size;

            // Track by extension
            const ext = getFileExtension(item.name).toLowerCase();
            extMap[ext] = (extMap[ext] || 0) + item.size;

            // Track large files
            if (item.size > 100 * 1024 * 1024) {
                result.largeFiles.push(item);
            }

            // Track for duplicates (by size)
            if (!sizeMap[item.size]) sizeMap[item.size] = [];
            sizeMap[item.size].push(item);
        });

        // Find duplicates (same size)
        Object.values(sizeMap).forEach(files => {
            if (files.length > 1) {
                result.duplicates += files.length - 1;
                result.duplicateSize += files[0].size * (files.length - 1);
                result.duplicateGroups.push({
                    name: files[0].name,
                    count: files.length,
                    size: files[0].size,
                    wasted: files[0].size * (files.length - 1)
                });
            }
        });

        // Categorize
        result.byCategory = {
            video: (extMap['mp4'] || 0) + (extMap['avi'] || 0) + (extMap['mkv'] || 0) + (extMap['mov'] || 0),
            image: (extMap['jpg'] || 0) + (extMap['jpeg'] || 0) + (extMap['png'] || 0) + (extMap['gif'] || 0),
            doc: (extMap['pdf'] || 0) + (extMap['doc'] || 0) + (extMap['docx'] || 0) + (extMap['xls'] || 0),
            code: (extMap['py'] || 0) + (extMap['js'] || 0) + (extMap['java'] || 0) + (extMap['cpp'] || 0),
            other: result.totalSize - Object.values(result.byCategory).reduce((a, b) => a + b, 0)
        };

        // Sort large files
        result.largeFiles.sort((a, b) => b.size - a.size);

        return result;
    }

    // Display files
    function displayFiles(items) {
        const list = document.getElementById('file-list');
        const count = document.getElementById('file-count');

        if (!items || items.length === 0) {
            list.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">📂</div>
                    <h3>文件夹为空</h3>
                    <p>此文件夹没有文件</p>
                </div>
            `;
            count.textContent = '0 个文件';
            return;
        }

        count.textContent = `${items.length} 个项目`;

        // Sort: folders first, then by size
        items.sort((a, b) => {
            if (a.isDirectory && !b.isDirectory) return -1;
            if (!a.isDirectory && b.isDirectory) return 1;
            return (b.size || 0) - (a.size || 0);
        });

        list.innerHTML = items.slice(0, 100).map(item => `
            <div class="file-item" data-path="${item.path || item.name}">
                <div class="file-icon">${item.isDirectory ? '📁' : getFileIcon(item.name)}</div>
                <div class="file-info">
                    <div class="file-name">${item.name}</div>
                    <div class="file-meta">${item.isDirectory ? '文件夹' : formatDate(item.modified)}</div>
                </div>
                <div class="file-size">${item.isDirectory ? '' : formatSize(item.size)}</div>
            </div>
        `).join('');

        // Add click handlers
        list.querySelectorAll('.file-item').forEach(item => {
            item.addEventListener('click', function() {
                // Remove previous selection
                list.querySelectorAll('.file-item').forEach(i => i.classList.remove('selected'));
                this.classList.add('selected');

                const path = this.dataset.path;
                handleFileClick(path);
            });
        });
    }

    async function handleFileClick(path) {
        try {
            const info = await window.electronAPI?.getFileInfo(path);
            if (info) {
                if (info.isDirectory) {
                    currentPath = path;
                    document.getElementById('current-path').textContent = path;
                    updateStatus('正在进入: ' + path);
                    performScan(path);
                } else {
                    showNotification(`文件: ${path.split(/[/\\]/).pop()}\n大小: ${formatSize(info.size)}\n修改: ${formatDate(info.modified)}`);
                }
            }
        } catch (e) {
            console.error('Get file info error:', e);
        }
    }

    // Duplicates page
    function showDuplicatesPage() {
        const list = document.getElementById('duplicate-list');
        if (!scanResults || !scanResults.duplicateGroups.length) {
            list.innerHTML = '<div class="empty-state"><div class="empty-state-icon">📦</div><h3>未找到重复文件</h3><p>当前扫描结果中没有重复文件</p></div>';
            return;
        }

        list.innerHTML = scanResults.duplicateGroups.map(g => `
            <div class="duplicate-item">
                <div class="dup-info">
                    <div class="dup-name">${g.name}</div>
                    <div class="dup-meta">${g.count} 个重复 · 单个 ${formatSize(g.size)}</div>
                </div>
                <div class="dup-waste">浪费 ${formatSize(g.wasted)}</div>
            </div>
        `).join('');
    }

    // Large files page
    function showLargeFilesPage() {
        const list = document.getElementById('large-list');
        if (!scanResults || !scanResults.largeFiles.length) {
            list.innerHTML = '<div class="empty-state"><div class="empty-state-icon">📊</div><h3>没有大文件</h3><p>没有找到超过 100MB 的文件</p></div>';
            return;
        }

        list.innerHTML = scanResults.largeFiles.slice(0, 20).map((f, i) => `
            <div class="large-item">
                <div class="large-rank">#${i + 1}</div>
                <div class="large-info">
                    <div class="large-name">${f.name}</div>
                    <div class="large-path">${f.path}</div>
                </div>
                <div class="large-size">${formatSize(f.size)}</div>
            </div>
        `).join('');
    }

    // Notification
    function showNotification(message) {
        const notification = document.getElementById('notification');
        if (notification) {
            notification.textContent = message;
            notification.style.display = 'block';
            notification.style.opacity = '1';
            setTimeout(() => {
                notification.style.opacity = '0';
                setTimeout(() => {
                    notification.style.display = 'none';
                }, 300);
            }, 3000);
        }
    }

    // Auto Update
    function initUpdateCheck() {
        // 显示当前版本
        window.electronAPI?.getAppVersion().then(version => {
            const versionEl = document.getElementById('update-status');
            if (versionEl) versionEl.textContent = '📌 v' + version;
        });

        // 监听更新状态
        window.electronAPI?.onUpdateStatus(data => {
            const versionEl = document.getElementById('update-status');
            if (!versionEl) return;

            switch (data.status) {
                case 'checking':
                    versionEl.textContent = '🔄 检查更新...';
                    break;
                case 'available':
                    versionEl.textContent = '🆕 v' + data.version + ' 可用';
                    versionEl.style.opacity = '1';
                    showNotification('发现新版本 v' + data.version + '！点击右下角版本号下载更新。');
                    break;
                case 'downloading':
                    versionEl.textContent = '📥 下载中 ' + data.percent + '%';
                    break;
                case 'downloaded':
                    versionEl.textContent = '✅ 下载完成';
                    versionEl.style.opacity = '1';
                    break;
                case 'up-to-date':
                    versionEl.textContent = '✅ 已是最新';
                    setTimeout(() => {
                        window.electronAPI?.getAppVersion().then(v => {
                            if (versionEl) versionEl.textContent = '📌 v' + v;
                        });
                    }, 2000);
                    break;
                case 'error':
                    versionEl.textContent = '⚠️ 更新失败';
                    setTimeout(() => {
                        window.electronAPI?.getAppVersion().then(v => {
                            if (versionEl) versionEl.textContent = '📌 v' + v;
                        });
                    }, 3000);
                    break;
            }
        });

        // 点击版本号检查更新
        document.getElementById('update-status')?.addEventListener('click', () => {
            window.electronAPI?.checkUpdate();
        });
    }

    // Update status
    function updateStatus(text) {
        const status = document.getElementById('status-text');
        if (status) status.textContent = text;
    }

    // Utility functions
    function getFileIcon(filename) {
        const ext = getFileExtension(filename).toLowerCase();
        if (['mp4', 'avi', 'mkv', 'mov', 'wmv'].includes(ext)) return '🎬';
        if (['mp3', 'wav', 'flac', 'aac', 'ogg'].includes(ext)) return '🎵';
        if (['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp'].includes(ext)) return '🖼️';
        if (['pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx'].includes(ext)) return '📄';
        if (['zip', 'rar', '7z', 'tar', 'gz'].includes(ext)) return '📦';
        if (['py', 'js', 'java', 'c', 'cpp', 'h', 'cs', 'go'].includes(ext)) return '💻';
        return '📄';
    }

    function getFileExtension(filename) {
        const parts = filename.split('.');
        return parts.length > 1 ? parts.pop() : '';
    }

    function formatSize(bytes) {
        if (!bytes || bytes === 0) return '0 B';
        const units = ['B', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(1024));
        return (bytes / Math.pow(1024, i)).toFixed(1) + ' ' + units[i];
    }

    function formatDate(isoString) {
        if (!isoString) return '';
        const date = new Date(isoString);
        return date.toLocaleDateString('zh-CN');
    }
})();
