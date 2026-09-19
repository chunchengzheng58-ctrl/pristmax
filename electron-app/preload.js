// Preload script - exposes safe IPC APIs to renderer
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
    // Window controls
    minimize: () => ipcRenderer.send('window-minimize'),
    maximize: () => ipcRenderer.send('window-maximize'),
    close: () => ipcRenderer.send('window-close'),
    isMaximized: () => ipcRenderer.invoke('window-is-maximized'),

    // File system
    selectDirectory: () => ipcRenderer.invoke('select-directory'),
    readDirectory: (path) => ipcRenderer.invoke('read-directory', path),
    getFileInfo: (path) => ipcRenderer.invoke('get-file-info', path),

    // Events
    onDirectorySelected: (callback) => {
        ipcRenderer.on('open-directory', (event, path) => callback(path));
    }
});
