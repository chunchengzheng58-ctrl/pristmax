# Pristmax Desktop (Electron)

独立桌面窗口版本的 Pristmax，加载官网界面。

## 系统要求

- Node.js 18+
- 网络连接（下载 Electron 二进制文件）

## 安装

```bash
cd electron-app
npm install
```

## 开发运行

```bash
npm start
```

## 构建 .exe

```bash
npm run build
```

输出目录: `dist/`

## 注意事项

- 首次运行需要下载 Electron 二进制文件（约 100MB）
- 如果下载慢，可以设置国内镜像：

```bash
export ELECTRON_MIRROR=https://npmmirror.com/mirrors/electron/
npm install
```
