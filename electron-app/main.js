const { app, BrowserWindow, Menu, shell, ipcMain, dialog } = require('electron');
const path = require('path');
const fs = require('fs');
const { autoUpdater } = require('electron-updater');

let mainWindow;

// Auto-updater configuration
autoUpdater.autoDownload = false;
autoUpdater.autoInstallOnAppQuit = true;

function setupAutoUpdater() {
  autoUpdater.on('checking-for-update', () => {
    console.log('检查更新中...');
    sendToRenderer('update-status', { status: 'checking' });
  });

  autoUpdater.on('update-available', (info) => {
    console.log('发现新版本:', info.version);
    sendToRenderer('update-status', {
      status: 'available',
      version: info.version,
      releaseDate: info.releaseDate,
      releaseNotes: info.releaseNotes
    });
  });

  autoUpdater.on('update-not-available', () => {
    console.log('已是最新版本');
    sendToRenderer('update-status', { status: 'up-to-date' });
  });

  autoUpdater.on('download-progress', (progress) => {
    sendToRenderer('update-status', {
      status: 'downloading',
      percent: Math.round(progress.percent)
    });
  });

  autoUpdater.on('update-downloaded', () => {
    console.log('下载完成');
    sendToRenderer('update-status', { status: 'downloaded' });
  });

  autoUpdater.on('error', (error) => {
    console.error('更新错误:', error);
    sendToRenderer('update-status', { status: 'error', message: error.message });
  });
}

function sendToRenderer(channel, data) {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send(channel, data);
  }
}

function checkForUpdates() {
  autoUpdater.checkForUpdates().catch(err => {
    console.error('检查更新失败:', err);
  });
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1024,
    minHeight: 700,
    title: 'Pristmax',
    frame: false,
    backgroundColor: '#1a1a2e',
    autoHideMenuBar: true,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js'),
      webSecurity: true
    }
  });

  const websitePath = path.join(__dirname, 'site');
  mainWindow.loadFile(path.join(websitePath, 'index.html'));

  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  const menuTemplate = [
    {
      label: 'File',
      submenu: [
        {
          label: 'Open Directory...',
          accelerator: 'CmdOrCtrl+O',
          click: async () => {
            const result = await dialog.showOpenDialog(mainWindow, {
              properties: ['openDirectory']
            });
            if (!result.canceled && result.filePaths.length > 0) {
              mainWindow.webContents.send('open-directory', result.filePaths[0]);
            }
          }
        },
        { type: 'separator' },
        {
          label: 'Refresh',
          accelerator: 'CmdOrCtrl+R',
          click: () => mainWindow.reload()
        },
        { type: 'separator' },
        {
          label: 'Exit',
          accelerator: 'Alt+F4',
          click: () => app.quit()
        }
      ]
    },
    {
      label: 'View',
      submenu: [
        { role: 'reload' },
        { role: 'forceReload' },
        { role: 'toggleDevTools' },
        { type: 'separator' },
        { role: 'resetZoom' },
        { role: 'zoomIn' },
        { role: 'zoomOut' },
        { type: 'separator' },
        { role: 'togglefullscreen' }
      ]
    },
    {
      label: 'Help',
      submenu: [
        {
          label: '检查更新',
          click: () => checkForUpdates()
        },
        {
          label: '关于 Pristmax',
          click: () => {
            dialog.showMessageBox(mainWindow, {
              type: 'info',
              title: 'About Pristmax',
              message: 'Pristmax v1.2.0',
              detail: 'Enterprise Storage Optimization\n\nLess storage. More clarity.'
            });
          }
        },
        {
          label: 'Visit Website',
          click: () => shell.openExternal('https://jiangchenghehe.top')
        }
      ]
    }
  ];

  const menu = Menu.buildFromTemplate(menuTemplate);
  Menu.setApplicationMenu(menu);
}

// IPC Handlers
ipcMain.on('window-minimize', () => {
  if (mainWindow) mainWindow.minimize();
});

ipcMain.on('window-maximize', () => {
  if (mainWindow) {
    if (mainWindow.isMaximized()) {
      mainWindow.unmaximize();
    } else {
      mainWindow.maximize();
    }
  }
});

ipcMain.on('window-close', () => {
  if (mainWindow) mainWindow.close();
});

ipcMain.handle('window-is-maximized', () => {
  return mainWindow ? mainWindow.isMaximized() : false;
});

ipcMain.handle('select-directory', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openDirectory']
  });
  if (!result.canceled && result.filePaths.length > 0) {
    return result.filePaths[0];
  }
  return null;
});

ipcMain.handle('read-directory', async (event, dirPath) => {
  try {
    const items = fs.readdirSync(dirPath, { withFileTypes: true });
    const result = [];
    for (const item of items.slice(0, 100)) {
      try {
        const fullPath = path.join(dirPath, item.name);
        const stats = fs.statSync(fullPath);
        result.push({
          name: item.name,
          path: fullPath,
          isDirectory: item.isDirectory(),
          size: stats.size,
          modified: stats.mtime.toISOString()
        });
      } catch (e) {
        // Skip inaccessible files
      }
    }
    return result;
  } catch (e) {
    return [];
  }
});

ipcMain.handle('get-file-info', async (event, filePath) => {
  try {
    const stats = fs.statSync(filePath);
    return {
      size: stats.size,
      modified: stats.mtime.toISOString(),
      created: stats.birthtime.toISOString(),
      isDirectory: stats.isDirectory()
    };
  } catch (e) {
    return null;
  }
});

// Update handlers
ipcMain.handle('check-update', () => {
  checkForUpdates();
});

ipcMain.handle('get-app-version', () => {
  return app.getVersion();
});

ipcMain.handle('download-update', () => {
  autoUpdater.downloadUpdate();
});

ipcMain.handle('install-update', () => {
  autoUpdater.quitAndInstall();
});

// Storage monitoring handlers - forward to MCP server
let storageAgent = null;

function getStorageAgent() {
  if (!storageAgent) {
    try {
      const { StorageAgent } = require('../src/pristmax/agent/storage_agent');
      storageAgent = new StorageAgent();
    } catch (err) {
      console.error('Failed to load StorageAgent:', err);
      return null;
    }
  }
  return storageAgent;
}

ipcMain.handle('storage_monitor_start', async (event, { path, recursive }) => {
  const agent = getStorageAgent();
  if (!agent) return { error: 'StorageAgent not available' };
  try {
    const monitorId = agent.startMonitoring(path, null, recursive);
    return { monitor_id: monitorId, status: 'started', path };
  } catch (err) {
    return { error: err.message };
  }
});

ipcMain.handle('storage_monitor_stop', async (event, { monitor_id }) => {
  const agent = getStorageAgent();
  if (!agent) return { error: 'StorageAgent not available' };
  return agent.stopMonitoring(monitor_id);
});

ipcMain.handle('storage_monitor_changes', async (event, { monitor_id }) => {
  const agent = getStorageAgent();
  if (!agent) return { error: 'StorageAgent not available' };
  return {
    monitor_id,
    changes: agent.get_monitoring_changes(monitor_id)
  };
});

ipcMain.handle('storage_incremental_scan', async (event, { path, since_mtime }) => {
  const agent = getStorageAgent();
  if (!agent) return { error: 'StorageAgent not available' };
  return agent.get_incremental_changes(path, since_mtime);
});

ipcMain.handle('storage_search_content', async (event, { path, keyword, file_types, max_results }) => {
  const agent = getStorageAgent();
  if (!agent) return { error: 'StorageAgent not available' };
  try {
    return agent.search_file_content(path, keyword, file_types, max_results);
  } catch (err) {
    return { error: err.message, matches: [] };
  }
});

// App lifecycle
app.whenReady().then(() => {
  console.log('App ready, creating window...');
  createWindow();
  setupAutoUpdater();
  // 启动时检查更新
  setTimeout(() => checkForUpdates(), 3000);
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});
