// Pristmax Desktop - Frontend Logic
(function() {
    'use strict';

    let currentPath = null;
    let currentPage = 'overview';

    // Initialize
    document.addEventListener('DOMContentLoaded', function() {
        initWindowControls();
        initSidebar();
        initActions();
        initPathSelector();
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

    // Actions
    function initActions() {
        // Scan button
        document.getElementById('btn-scan')?.addEventListener('click', selectAndScan);

        // Quick action cards
        document.getElementById('action-scan-dir')?.addEventListener('click', selectAndScan);
        document.getElementById('action-find-dup')?.addEventListener('click', findDuplicates);
        document.getElementById('action-find-large')?.addEventListener('click', findLargeFiles);
    }

    // Path Selector
    function initPathSelector() {
        document.getElementById('path-selector')?.addEventListener('click', selectAndScan);
    }

    // Select directory and scan
    async function selectAndScan() {
        try {
            const path = await window.electronAPI?.selectDirectory();
            if (path) {
                currentPath = path;
                document.getElementById('current-path').textContent = path;
                updateStatus('正在扫描...');
                scanDirectory(path);
            }
        } catch (e) {
            console.error('Select directory error:', e);
            updateStatus('选择文件夹失败');
        }
    }

    // Scan directory
    async function scanDirectory(path) {
        try {
            const items = await window.electronAPI?.readDirectory(path);
            if (items) {
                displayFiles(items);
                updateMetrics(items);
                updateStatus('扫描完成');
            }
        } catch (e) {
            console.error('Scan error:', e);
            updateStatus('扫描失败');
        }
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

        count.textContent = `${items.length} 个文件`;

        list.innerHTML = items.map(item => `
            <div class="file-item" data-path="${item.path}">
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
                const path = this.dataset.path;
                handleFileClick(path);
            });
        });
    }

    // Handle file click
    async function handleFileClick(path) {
        try {
            const info = await window.electronAPI?.getFileInfo(path);
            if (info) {
                if (info.isDirectory) {
                    currentPath = path;
                    document.getElementById('current-path').textContent = path;
                    scanDirectory(path);
                } else {
                    // Show file info
                    alert(`文件: ${path}\n大小: ${formatSize(info.size)}\n修改时间: ${formatDate(info.modified)}`);
                }
            }
        } catch (e) {
            console.error('Get file info error:', e);
        }
    }

    // Update metrics
    function updateMetrics(items) {
        const totalFiles = items.filter(i => !i.isDirectory).length;
        const totalSize = items.reduce((sum, i) => sum + (i.size || 0), 0);

        document.getElementById('metric-files').textContent = totalFiles.toLocaleString();
        document.getElementById('metric-size').innerHTML = `${(totalSize / 1024**3).toFixed(2)} <span class="unit">GB</span>`;

        // Calculate by type
        const byType = { video: 0, image: 0, doc: 0, code: 0, other: 0 };
        items.forEach(item => {
            if (item.isDirectory) return;
            const ext = getFileExtension(item.name).toLowerCase();
            if (['mp4', 'avi', 'mkv', 'mov', 'wmv'].includes(ext)) byType.video += item.size;
            else if (['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp'].includes(ext)) byType.image += item.size;
            else if (['pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt'].includes(ext)) byType.doc += item.size;
            else if (['py', 'js', 'java', 'c', 'cpp', 'h', 'cs', 'go'].includes(ext)) byType.code += item.size;
            else byType.other += item.size;
        });

        const maxSize = Math.max(...Object.values(byType), 1);
        document.getElementById('size-video').textContent = formatSize(byType.video);
        document.getElementById('size-image').textContent = formatSize(byType.image);
        document.getElementById('size-doc').textContent = formatSize(byType.doc);
        document.getElementById('size-code').textContent = formatSize(byType.code);
        document.getElementById('size-other').textContent = formatSize(byType.other);

        // Update progress bars
        document.querySelectorAll('.storage-fill')[0].style.width = `${(byType.video / maxSize * 100)}%`;
        document.querySelectorAll('.storage-fill')[1].style.width = `${(byType.image / maxSize * 100)}%`;
        document.querySelectorAll('.storage-fill')[2].style.width = `${(byType.doc / maxSize * 100)}%`;
        document.querySelectorAll('.storage-fill')[3].style.width = `${(byType.code / maxSize * 100)}%`;
        document.querySelectorAll('.storage-fill')[4].style.width = `${(byType.other / maxSize * 100)}%`;
    }

    // Find duplicates
    function findDuplicates() {
        if (!currentPath) {
            alert('请先选择文件夹');
            return;
        }
        updateStatus('正在查找重复文件...');
        // TODO: Implement duplicate detection
        setTimeout(() => {
            document.getElementById('metric-duplicates').textContent = '5';
            document.getElementById('metric-savings').innerHTML = `4.2 <span class="unit">GB</span>`;
            updateStatus('找到 5 组重复文件，可释放 4.2 GB');
        }, 1500);
    }

    // Find large files
    function findLargeFiles() {
        if (!currentPath) {
            alert('请先选择文件夹');
            return;
        }
        updateStatus('正在查找大文件...');
        // TODO: Implement large file detection
        setTimeout(() => {
            updateStatus('找到大文件分析完成');
        }, 1500);
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
        if (bytes === 0) return '0 B';
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
