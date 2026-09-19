# 给 Claude Code：最新改动与可执行部署方式

更新时间：2026-09-18。此文是官网当前交接入口，优先于旧交接文档中的历史状态。

## 已完成并上线

线上提交：`b108e618e00a88695a1eacc54d7a400edeeba3d1`。
GitHub Pages workflow 已 success；Nginx 官网也已发布同一提交的 site/。

- 页脚换成宝蓝＋鎏金的松柏、竹林、湖面画，山体为左侧层崖、右侧石柱，移除建筑群。
- 图片：`site/assets/blue-gold-forest.webp`。内置 imagegen 在旧蓝金画面基础上编辑，并非纯文字独立生成；记录见同目录 `blue-gold-forest-notes.md`。不宣称已取得法律审核。
- `site/footer-art.js`：湖面 SVG 位移、竹梢轻摆、离屏暂停；到底部后计时 10000 ms 停止，离开底部复位，再到底部重新计时。
- `site/footer-art.css`：局部动效样式、贡献者区域宽度约束、底部颜色。
- 底部背景随滚动由白色过渡到宝蓝 `#113577`，标题文字同步由深色变浅。
- 没有 Pause motion 按钮；支持 prefers-reduced-motion。
- 保留 Claude 的社区区域与页面修改。发布包含当前首页及共享 motion.css。

线上实测：图片自然宽度 2172、到底 11 秒后 art-paused=true、按钮不存在、背景 rgb(17,53,119)，浏览器无脚本错误。Pages 首页及 footer-art.js HTTP 200。

旧的 forest-gorge、landscape-continuous、六块 landscape-panel 图均不是当前首页资源；不要重新挂回。

## 两个发布入口，缺一不可

1. https://chunchengzheng58-ctrl.github.io/pristmax/ ：GitHub Pages，GitHub Actions 发布。
2. https://jiangchenghehe.top/ ：阿里云服务器上的 Nginx，并非指向 Pages。更新 Pages 不会自动更新这个域名。

仓库：https://github.com/chunchengzheng58-ctrl/pristmax ，分支 main。
唯一发布目录：site/。不要部署 docs/、src/pristmax/site/ 或整个仓库。

## 本机环境与凭据定位

工作目录：C:/Users/zcc36/Documents/ChatGPT/存储项目，使用 PowerShell。
现有工具：git、gh、ssh、scp、python、node/npx。
服务器：root@8.133.180.156。
SSH 私钥位置：$env:USERPROFILE/.ssh/ashou_deploy_ed25519。
网站根目录：/var/www/pristmax。
Nginx 配置：/etc/nginx/conf.d/pristmax.conf。
TLS 文件：/etc/nginx/ssl/ashou.pem、ashou.key。名字虽旧仍在用，不要删除。
私钥内容不可打印、提交或放进网站。不要关闭主机指纹检查。

先检查：
```powershell
Set-Location 'C:/Users/zcc36/Documents/ChatGPT/存储项目'
git status --short
git branch --show-current
gh auth status
Test-Path "$env:USERPROFILE/.ssh/ashou_deploy_ed25519"
ssh -i "$env:USERPROFILE/.ssh/ashou_deploy_ed25519" -o BatchMode=yes -o StrictHostKeyChecking=yes root@8.133.180.156 'test -d /var/www/pristmax && nginx -t'
```

## 统一发布步骤

下列任何一步失败都先停止，不要继续报成功。只提交本次确认要发布的文件；特别注意其他人的 staged 文件。

```powershell
# 先验证当前改动。其他页面改动按实际增加明确路径。
node --check site/footer-art.js
if ($LASTEXITCODE -ne 0) { throw 'JS check failed' }
git diff --check -- site
if ($LASTEXITCODE -ne 0) { throw 'Diff check failed' }

# 示例路径列表；若有其他新增资源，必须明确加入。
$publishFiles = @('site/index.html','site/motion.css','site/footer-art.css','site/footer-art.js','site/bamboo-shoot.css','site/bamboo-shoot.js','site/assets/blue-gold-forest.webp','site/assets/blue-gold-forest-notes.md')
git add -- $publishFiles
# --only 防止提交其他已暂存的后端改动。文件内的现有修改仍需事先审阅。
git commit --only -m 'Update Pristmax website' -- $publishFiles
# 如果提示没有更改且 HEAD 已是目标版本，跳过提交；不要创建空提交。
git push origin main
if ($LASTEXITCODE -ne 0) { throw 'Push failed; inspect remote changes, never force push' }

# 打包同一个已提交版本，避免把未跟踪图片、凭据和后端传到服务器。
$releaseId = (git rev-parse --short HEAD).Trim()
New-Item -ItemType Directory -Force output | Out-Null
git archive --format=tar -o output/pristmax-site-release.tar HEAD site
if ($LASTEXITCODE -ne 0) { throw 'Archive failed' }
$sshKey = "$env:USERPROFILE/.ssh/ashou_deploy_ed25519"
scp -i $sshKey -o BatchMode=yes -o StrictHostKeyChecking=yes output/pristmax-site-release.tar "root@8.133.180.156:/tmp/pristmax-site-$releaseId.tar"
if ($LASTEXITCODE -ne 0) { throw 'Upload failed' }
$backupId = "$releaseId-$(Get-Date -Format yyyyMMddHHmmss)"
ssh -i $sshKey -o BatchMode=yes -o StrictHostKeyChecking=yes root@8.133.180.156 "mkdir -p /root/pristmax-site-backups/$backupId && cp -a /var/www/pristmax/. /root/pristmax-site-backups/$backupId/ && tar -xf /tmp/pristmax-site-$releaseId.tar --strip-components=1 -C /var/www/pristmax && nginx -t"
if ($LASTEXITCODE -ne 0) { throw 'Server deploy failed; inspect before retry' }
```

纯静态文件更新不需要重启服务器、不需要启动 Python 后端，也不需要 Nginx reload。上述发布覆盖同名静态文件，不会清空系统或删除 TLS。

## Pages 配置与核验

`.github/workflows/pages.yml` 自动监听 main 上 site/** 和 workflow 的变更；上传 site，随后 deploy-pages。无需 npm build，也不需要手动把文件复制到 gh-pages 分支。不要设置另一个 CNAME 或改 DNS。

```powershell
gh run list --workflow pages.yml --limit 3 --json databaseId,headSha,status,conclusion
# 必须确认 headSha 等于 git rev-parse HEAD 且 conclusion=success。
# 失败时：gh run view <databaseId> --log-failed
# 若对应提交没有触发：gh workflow run pages.yml --ref main

$urls = @('https://jiangchenghehe.top/','https://chunchengzheng58-ctrl.github.io/pristmax/')
foreach ($url in $urls) {
  $html = Invoke-WebRequest -Uri $url -UseBasicParsing
  if (!$html.Content.Contains('blue-gold-forest.webp')) { throw "Wrong version at $url" }
  foreach ($asset in @('footer-art.js','footer-art.css','assets/blue-gold-forest.webp')) {
    $result = Invoke-WebRequest -Uri ($url+$asset) -UseBasicParsing
    if ($result.StatusCode -ne 200) { throw "Missing $asset at $url" }
  }
}
```

浏览器最后确认：滚动白→宝蓝、底部动画、10 秒后停止、回滚再进入恢复、手机不横向溢出、无控制台错误。单独 HTTP 200 不能代表动效验收通过。

## 常见部署故障

- Permission denied(publickey)：核对用户名 root、上述密钥是否存在、当前环境能否访问 Windows 的密钥路径。不要重新生成覆盖旧密钥。
- Host key verification failed：核对服务器指纹/known_hosts；不能用 StrictHostKeyChecking=no 绕过。
- SSH 连接超时：确认 8.133.180.156:22 可达和阿里云防火墙；本地权限/网络沙盒受限时，如实说明限制。
- gh 未登录：先 gh auth status，在用户自己的终端完成 gh auth login；不要索要聊天明文 token。
- push 被拒：先 fetch/diff，保留双方改动，不强推、不 reset。
- Pages 绿了但域名没更新：漏做服务器发布。
- 图片或动效 404：忘了提交新资源或漏传 footer-art.css/js。git archive 只包含已提交文件。
- 样式看起来旧：先核对线上文件内容，再 Ctrl+F5；不要把所有问题都归因于缓存。
- Claude 所在环境缺少 Windows 密钥/SSH 网络权限：无法凭空部署；明确报告哪个命令及错误，把命令交给本机环境执行。不要谎称完成。

## 已有回滚备份

最近部署前备份：/root/pristmax-site-backups/b108e61-before/。
回滚时先备份当前线上，再把选定备份内容复制回 /var/www/pristmax/ 并验收。Pages 应对目标网站提交做可审阅的 revert 后 push，不改写 main 历史。若备份后新增的静态文件需要移除，应逐项确认，不递归清空网站。
