# 最新入口（2026-09-18）

请先读 [DEPLOY-CLAUDE-LATEST.md](DEPLOY-CLAUDE-LATEST.md)。当前官网和 Pages 已上线 b108e618e00a88695a1eacc54d7a400edeeba3d1。下文保留历史记录，凡提交号、尚未发布或暂停按钮描述与最新文档冲突，以最新文档为准。

# Pristmax 官网续接与统一部署手册

更新：2026-09-18。请先读此文，再改页面或部署。

## 1. 接手基线

- 最近一次已验证上线基线提交：`f9ced06613b9af118449c64be308962b631eeecd`。
- 此提交 GitHub Pages Actions 已确认 success。
- 工作区：`C:/Users/zcc36/Documents/ChatGPT/存储项目`，PowerShell。
- 仓库：https://github.com/chunchengzheng58-ctrl/pristmax ，主分支 `main`。
- Pages：https://chunchengzheng58-ctrl.github.io/pristmax/
- 当前自定义域名：https://jiangchenghehe.top/
- **两处均在线，但不是同一个托管入口**：Pages 在 GitHub；当前自定义域名仍由原 Nginx 服务器提供。尚未迁移 DNS。

用户要求继续当前视觉，先做好官网。不要重新设计品牌，不要重建第二套官网。

## 2. 唯一官网源码与文件职责

**唯一官网发布源：仓库根目录 `site/`。**

| 文件 | 职责 |
|---|---|
| `site/index.html` | 首页结构，单一开场标题、产品说明、功能、安装与页脚 |
| `site/docs.html` | 安装文档，有 `#install` 锚点 |
| `site/style.css` | 基础样式、文档样式、共享 GitHub/Install 按钮 |
| `site/home.css` | 首页布局与移动端排布 |
| `site/motion.css` | 动效与黑白首屏布局，最后加载覆盖基础样式 |
| `site/main.js` | 移动菜单 |
| `site/motion.js` | 蝴蝶 SVG、滚动显现、安装框、统一首屏滚动效果 |
| `site/assets/` | 三曲面过渡 Logo 的深色和反白 SVG |
| `.github/workflows/pages.yml` | GitHub Actions 发布 site/ |

`docs/`、`src/pristmax/site/`、`unified/` 中可能保留旧网站或产品页面。**不要向这些目录复制官网改动，不要从它们发布官网。** 先确认用途再清理，不能直接删除用户资料。

`site/design.js`、`site/design.css`、`site/pristmax-editorial.css` 是历史材料，目前主页不加载。尤其不要恢复 `../design.js` 或把旧 design.js 整体引入：它包含依赖控制台 DOM/API 的代码，会报错。曾经有效的蝴蝶部分已单独提取到 motion.js。

## 3. 用户确定的视觉与交互

- 品牌 **Pristmax**，过渡 Logo 是三片曲面围绕中央留白，不是字母标志。
- 冰蓝、深墨蓝、白；不使用绿色、翡翠石头。
- 英文大标题与简洁中文说明，衬线品牌字，数字使用等高数字。
- 首页和文档页右上角统一：`GitHub ↗` 描边按钮 + 蓝色 `Install 安装` 实心按钮。
- GitHub 按钮直达上述仓库，新标签页；Install 进入 `docs.html#install`，不是虚构安装包下载。
- 开场是黑底、巨大冰蓝 PRISTMAX，向下滚动变白、标题上移、介绍与按钮出现。
- **开场和白色首页是同一个首屏、同一个 h1。绝不能再追加第二个 PRISTMAX 首屏。** 用户明确指出前一版上下重复是 Bug，已经修复。
- 功能区：左侧标题桌面 sticky，右侧原生 details 展开。
- 蝴蝶线描：展开时飞舞，按钮可重播；页脚同系列线描。
- 安装区随滚动出现蓝色外框，区块随进入视口逐渐显现。
- 不劫持滚轮、不要求第三方 CDN；支持 prefers-reduced-motion。

## 4. 首屏实现与注意点

DOM：`.opening > .opening-screen`，内部只有一个 `h1.opening-word` 和 `.opening-content`。

- 正常模式 opening 高 180svh，screen sticky 高 100svh。
- motion.js 按滚动距离计算 0–1 进度，更新背景、字色、标题位置和内容显现。
- `.opening-content` 初始隐藏且 inert，变白后恢复可交互。
- `body.opening-active` 时导航隐藏并 inert；结束时恢复，导航 z-index 高于 opening。
- 向下箭头推进到首屏展开状态；向上滚动可逆。
- 减少动态模式展示静态白色首屏；noscript 提供内容可读降级。
- 页脚有品牌字属于独立页脚设计，不等于首屏重复。

后续特别检查：短屏横屏、缩放、锚点直达、浏览器返回、减少动态效果、滚动中间态文字对比度。不要因修复一个断点破坏其他设备。

## 5. 当前已验证与未验证

已验证：
- 1440×1000 和 390×844，无整页横向溢出。
- 主标题数量为 1；白色状态介绍可见，导航不被开场遮挡。
- 手机菜单、GitHub/Install 路径、功能展开、蝴蝶重播。
- 动效添加后的浏览器无控制台错误。
- 动效版本减少动态设置下动画停止、滚动显现内容不再隐藏；合并首屏后的各极端屏幕仍应继续检查。
- 原域名静态文件同步；Pages 最后成功提交为上述基线。

这不是产品后端的完整验收。官网示意不证明真实存储节省率；正式安装包尚未发布。根 LICENSE 和 README 的开源描述曾发现不一致，需用户明确授权模式后再统一，不要擅自换许可证。

## 6. 统一部署流程（照此执行）

### A. 修改前

```powershell
git status --short
git log -5 --oneline
```

目前有用户/Claude 尚未提交的 README、main.py、src/pristmax/api 等修改。保留它们；不要 git reset --hard、git clean 或 git add .。不要把数据库、日志、录屏、研究 PDF、密钥发布出去。

### B. 本地预览

从仓库根目录运行：

```powershell
python -m http.server 8780 --bind 127.0.0.1 --directory site
```

访问 `http://127.0.0.1:8780/`。端口在用先检查是否已有预览进程，不要盲目结束服务。

### C. 提交官网并发布 Pages（主发布流程）

只暂存本轮确实修改的官网文件，例如：

```powershell
git add site/index.html site/docs.html site/style.css site/home.css site/motion.css site/main.js site/motion.js
git diff --cached --stat
git diff --cached
git commit -m "Describe website change"
git push origin main
gh run list -R chunchengzheng58-ctrl/pristmax --limit 5 --json databaseId,headSha,status,conclusion
```

核对运行的 headSha 是否等于 `git rev-parse HEAD`，不能把上一次 success 当成本次成功。用真实 run ID 查看结果：

```powershell
gh run view <RUN_ID> -R chunchengzheng58-ctrl/pristmax --json status,conclusion,headSha
# 失败时：
gh run view <RUN_ID> -R chunchengzheng58-ctrl/pristmax --log-failed
```

工作流自动从 `site/` 上传 Pages artifact；不需要 npm build，不需要 Python API，不需要 gh-pages 分支。
Pages Settings 的 Source 应为 **GitHub Actions**。不要改成 docs/ 或仓库根目录分支发布。
所有站内资源保持相对路径，使 `/pristmax/` 子路径可用。
`docs/CNAME` 不在当前发布物里，不要复制到 site/，也不要未经验证绑定旧域名到 Pages。

### D. 同版本同步原域名服务器（仍在双入口期间必须做）

当前服务器：`8.133.180.156`，Nginx 根目录 `/var/www/pristmax`。
本机已有 SSH key：`$env:USERPROFILE/.ssh/ashou_deploy_ed25519`。不读取/打印/上传私钥内容。

确认 site/ 工作区与刚发布的提交一致，再先备份远端静态页面：

```powershell
$releaseTag = Get-Date -Format 'yyyyMMdd-HHmmss'
$deployKey = Join-Path $env:USERPROFILE '.ssh/ashou_deploy_ed25519'
ssh -o BatchMode=yes -o StrictHostKeyChecking=yes -i $deployKey root@8.133.180.156 "mkdir -p /root/pristmax-site-backups/$releaseTag && cp -a /var/www/pristmax/. /root/pristmax-site-backups/$releaseTag/"
if ($LASTEXITCODE -ne 0) { throw 'Remote backup failed; stop deployment.' }
scp -o BatchMode=yes -i $deployKey site/style.css site/home.css site/motion.css site/main.js site/motion.js root@8.133.180.156:/var/www/pristmax/
if ($LASTEXITCODE -ne 0) { throw 'Resource upload failed; stop deployment.' }
scp -o BatchMode=yes -i $deployKey site/assets/*.svg root@8.133.180.156:/var/www/pristmax/assets/
if ($LASTEXITCODE -ne 0) { throw 'Asset upload failed; stop deployment.' }
# 资源先上传，HTML 最后上传。
scp -o BatchMode=yes -i $deployKey site/docs.html site/index.html root@8.133.180.156:/var/www/pristmax/
if ($LASTEXITCODE -ne 0) { throw 'HTML upload failed; verify server before continuing.' }
```

此清单为当前发布文件；新增资源时明确加入。不要 scp 整个仓库；不需要启动 Flask。纯静态文件更新不必重启 Nginx。
不要运行历史 `cleanup-ashou.py` / 旧迁移脚本；阿寿已备份清理完成。

### E. 两处公网都验证

- `https://chunchengzheng58-ctrl.github.io/pristmax/`
- `https://jiangchenghehe.top/`

验证：首页、docs.html、motion.css、motion.js 和 SVG 返回 200；首页使用最新单标题结构；滚动黑白切换、导航显示、移动菜单、GitHub 和 Install 正常；没有 JS 错误或资源 404。必要时用 Ctrl+F5 排除浏览器缓存。

不要只看到 push 成功就说上线完成；必须等 Pages run 成功并检查公网。

### F. 回滚

Pages：在确认目标提交后，`git revert <本轮官网提交>`，检查后 push，让工作流重新发布；不 force push，不覆盖别人的业务改动。
服务器：从本轮记录的 `/root/pristmax-site-backups/<releaseTag>/` 恢复静态文件；本轮新增文件若要移除，只删明确列出的文件。不要恢复整个旧 Nginx 配置，不要 rm -rf 网站或 /var/www。

## 7. 域名与服务器的后续决策

Pages 已可独立托管官网，但现有域名尚在服务器上。若用户要求真正停止依赖服务器，需要另做 DNS/自定义域名/HTTPS 迁移验证。**当前不要自行停服务器或改 DNS。**

当前 Nginx 仍使用 `/etc/nginx/ssl/ashou.pem` 和 `ashou.key`，它们是域名证书，不是可删除的旧项目垃圾。先前检查有效期到 2026-12-10，自动续期未确认。

## 8. 给 Claude 的继续任务

1. 先核对工作区与线上版本，维持本手册的单一发布源。
2. 优化视觉时以用户下一条反馈为准，保留单一首屏黑→白的连续关系。
3. 不把文案、安装状态、开源许可、产品能力与 UI 示意混淆。
4. 每轮更新按 C→D→E 完成部署并报告两个地址，不只改本地。
5. 产品业务代码的未提交修改属于其他工作，未经检查不要纳入官网提交。

可直接交给 Claude：

> 请先完整阅读根目录 HANDOFF-CLAUDE.md，沿用当前 Pristmax 官网继续操作。唯一官网源是 site/。开场与白色介绍共用一个 h1，禁止恢复两个重复首屏；保留冰蓝配色、三曲面 Logo、GitHub+蓝色安装按钮以及独立动效脚本。按文档统一部署到 GitHub Pages 和现有 Nginx 域名，验证本次提交的 Actions 与公网效果。保留其他未提交的业务代码，不改 DNS、不重跑旧项目清理脚本。

## 2026-09-18 页脚更新
页脚蝴蝶已替换为原创山水插画 assets/pristmax-shanshui.webp。保留页中蝴蝶展示。新图提示词和部署说明见 site/assets/shanshui-notes.md。部署必须包含 WebP，不可只复制 SVG。雾层支持减少动态效果偏好。


## 页脚二次调整（以此为准）
用户要求直接拼接六幅蓝金山水，现改用 landscape-panel-1.webp 到 6.webp。不再使用生成的山水。滚动控制各幅升起与缩放，手机另有横向展开。详见 site/assets/shanshui-notes.md。


页脚最终版本：单张 landscape-continuous.webp 经 AI 重绘融合参考画，去掉文字与手机界面，连续山脊河流。替代六图直拼；整幅随滚动升起，手机横移。


最新：页脚已在本地改为 forest-gorge.webp。纯文字生成调用，无图像输入；构图为左侧松柏高崖、右侧竹林、斜向云谷，无建筑瀑布。详见 site/assets/forest-gorge-provenance.md。尚未发布，工作区存在其他页面修改，部署前合并核对。


## 当前页脚动效版（2026-09-18）
使用 assets/blue-gold-forest.webp，沿用原蓝金画面编辑更换为层崖、石柱、松柏和竹林，无建筑。footer-art.css/js 是独立动效文件，index.html 引用两者并含 SVG 湖面遮罩。暂停按钮、离屏停止、减少动态偏好已验证。发布需包含这两个新文件与新 WebP。此次仅完成本地，未覆盖远端。来源及提示词见 assets/blue-gold-forest-notes.md。


页脚最新交互：移除暂停按钮；到底部后 10 秒停止湖面、竹梢和雾层动画，离开底部后复位，下次到底重新计时。背景随滚动白色变为宝蓝 #113577，标题文字同步反色。改动在 footer-art.js/css，仍为本地未发布。

