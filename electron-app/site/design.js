/** Pristmax - All Rights Reserved. Copyright © 2024-2026 */
// Presentation interactions. No production mutations are simulated.
document.querySelectorAll('.table').forEach(table=>{const wrap=document.createElement('div');wrap.className='table-scroll';table.before(wrap);wrap.append(table);});
const statusBox=document.getElementById('ui-status');let statusTimer;
function inform(message){statusBox.textContent=message;clearTimeout(statusTimer);statusTimer=setTimeout(()=>statusBox.textContent='',4500);}
function showPreview(title){document.getElementById('dialog-title').textContent=title;document.getElementById('dialog-message').textContent='当前是合并系统的演示工作空间。此操作尚未连接生产写入接口，不会创建任务、修改策略或接入设备。你可以继续浏览现有示例，评估信息布局与操作路径。';document.getElementById('preview-dialog').showModal();}
document.getElementById('refresh-view').onclick=()=>{renderHashRing();inform('视图已刷新 · 当前仍为演示数据');};
document.querySelectorAll('.section .btn:not([onclick])').forEach(button=>{if(button.textContent.trim()==='导出记录'){button.onclick=()=>{const rows=[...document.querySelectorAll('#audit .table tr')].filter(r=>!r.hidden);const csv='\ufeff'+rows.map(r=>[...r.cells].map(c=>'"'+c.textContent.trim().replaceAll('"','""')+'"').join(',')).join('\r\n');const url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='Pristmax-demo-audit.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);inform('已导出演示审计记录');};}else button.onclick=()=>showPreview(button.textContent.trim());});
document.querySelectorAll('#audit select').forEach(select=>select.onchange=()=>{const selected=[...document.querySelectorAll('#audit select')].map(s=>s.value.toLowerCase()).filter(v=>!v.includes('all')&&v!=='');document.querySelectorAll('#audit tbody tr').forEach(r=>r.hidden=!selected.every(v=>r.textContent.toLowerCase().includes(v)));});
const initialTab=location.hash.slice(1);if(['dashboard','semantic','distributed','audit','roi'].includes(initialTab))switchTab(initialTab);
document.querySelectorAll('a[href="#dashboard"]').forEach(a=>a.onclick=e=>{e.preventDefault();switchTab('dashboard');});
document.getElementById('preview-dialog').addEventListener('click',e=>{if(e.target===e.currentTarget){const r=e.currentTarget.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)e.currentTarget.close();}});
window.addEventListener('hashchange',()=>{const tab=location.hash.slice(1);if(['dashboard','semantic','distributed','audit','roi'].includes(tab))switchTab(tab);});
document.querySelectorAll('.nav-item').forEach(t=>t.setAttribute('aria-current',t.classList.contains('active')?'page':'false'));

// Original pen-and-ink butterfly study. Separate wing hinges preserve drawn detail.
(()=>{
 const detail=document.getElementById('winter-detail');if(!detail)return;
 const svg=detail.querySelector('svg');
 const upper='M4 0 C14 -22 37 -64 78 -101 C98 -120 119 -129 129 -127 C137 -125 128 -104 132 -99 C138 -94 124 -83 127 -77 C130 -70 117 -61 119 -55 C122 -47 108 -42 108 -35 C107 -28 94 -25 91 -19 C86 -10 73 -10 68 -5 C48 5 22 9 4 0Z';
 const lower='M5 4 C37 -3 70 -13 91 -20 C99 -6 99 8 90 18 C94 27 87 38 77 41 C80 51 69 59 59 58 C58 75 53 95 45 105 C39 109 39 99 41 89 L43 62 C29 65 20 48 14 33 C8 20 5 13 5 4Z';
 let wing=`<path class="wing-outline" d="${upper}"/><path class="wing-outline" d="${lower}"/>`;
 // Long, curved vein cells, following the wing's organic contours.
 const cells=[
 'M8 -3 Q32 -51 117 -116 Q88 -104 61 -69 Q35 -32 8 -3Z',
 'M12 -1 Q49 -47 119 -99 Q111 -78 81 -59 Q48 -32 12 -1Z',
 'M15 0 Q58 -34 114 -78 Q113 -61 82 -42 Q52 -20 15 0Z',
 'M17 2 Q53 -14 107 -55 Q102 -38 76 -25 Q44 -6 17 2Z',
 'M20 4 Q54 -4 93 -33 Q86 -16 63 -8 Q35 2 20 4Z',
 'M11 12 Q42 22 84 5 Q85 22 68 28 Q35 33 11 12Z',
 'M13 18 Q38 40 71 31 Q75 43 60 48 Q34 48 13 18Z',
 'M15 25 Q31 48 54 52 Q56 62 45 58 Q27 51 15 25Z'
 ];
 wing+=cells.map(d=>`<path class="wing-vein" d="${d}"/>`).join('');
 // Fine engraving hatching in the marginal bands, not a repeated flower stamp.
 for(let i=0;i<24;i++){
 const t=i/23,x=69+58*t,y=-9-106*t;
 wing+=`<path class="wing-hatch" d="M${x} ${y} q${7-3*t} ${-1-3*t} ${11-4*t} ${-5-2*t}"/>`;
 }
 [[121,-114],[123,-101],[119,-86],[113,-70],[105,-54],[96,-40],[84,-26],[86,1],[83,15],[72,33],[58,47]].forEach(([x,y],i)=>{wing+=`<ellipse cx="${x}" cy="${y}" rx="${i<7?2.3:3}" ry="${i<7?4:2}" transform="rotate(35 ${x} ${y})" fill="currentColor" stroke="none" opacity=".75"/>`;});
 for(let i=0;i<16;i++){let x=18+i*2.5,y=28+i*1.9;wing+=`<path class="wing-hatch" d="M${x} ${y} q-2 5 3 10"/>`;}
 wing+='<path class="wing-vein" d="M24 -15 C35 -43 55 -57 65 -53 C78 -46 61 -25 49 -29 C40 -34 48 -44 54 -41 M24 17 C38 12 57 12 59 23 C60 34 44 35 43 28 C42 21 51 21 52 26"/>';
 const insect=`<g class="paper-wing paper-wing-left">${wing}</g><g transform="scale(-1 1)"><g class="paper-wing paper-wing-right">${wing}</g></g><g class="butterfly-body"><path d="M-3 -16 Q-9 -5 -4 14 Q-3 37 0 48 Q4 31 4 13 Q9 -6 3 -16Z"/><ellipse cy="-20" rx="4" ry="5"/><path d="M-2 -23 C-6 -42 -22 -56 -27 -49 M2 -23 C8 -46 23 -58 28 -49 M-4 1 L-16 12 M4 1 L16 12"/>${Array.from({length:9},(_,i)=>`<path d="M-3 ${i*4} Q0 ${i*4+2} 3 ${i*4}"/>`).join('')}</g>`;
 svg.innerHTML=[[435,285,1.12,-24],[558,100,.48,19],[297,437,.36,-37]].map(([x,y,s,r],i)=>`<g transform="translate(${x} ${y}) scale(${s}) rotate(${r})"><g class="paper-flight" style="--flight-delay:${i*.45}s;--wing-speed:${1.7+i*.3}s">${insect}</g></g>`).join('');
 const bloom=()=>{detail.classList.remove('is-blooming');void svg.getBoundingClientRect();detail.classList.add('is-blooming');};
 detail.addEventListener('toggle',()=>{if(detail.open)bloom();else detail.classList.remove('is-blooming');});
 detail.querySelector('.winter-replay').addEventListener('click',bloom);
})();

// =============================================================================
// Storage Management (Multi-Storage Abstraction Layer)
// =============================================================================

let storageWizard = {
 currentStep: 1,
 selectedType: null,
 config: {}
};

const STORAGE_TYPE_NAMES = {
 local_disk: '本地硬盘',
 nas: 'NAS 存储',
 usb: '外置硬盘',
 cloud: '云存储',
 raid: 'RAID 阵列'
};

const STORAGE_TYPE_ICONS = {
 local_disk: '💾',
 nas: '📡',
 usb: '🔌',
 cloud: '☁️',
 raid: '🗄️'
};

function formatBytes(bytes) {
 if (bytes === 0) return '0 B';
 const k = 1024;
 const sizes = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
 const i = Math.floor(Math.log(bytes) / Math.log(k));
 return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

function loadStorages() {
 const listEl = document.getElementById('storage-list');
 if (!listEl) return;

 fetch('/api/storages')
 .then(r => r.json())
 .then(data => {
 if (!data.storages || data.storages.length === 0) {
 listEl.innerHTML = '<div class="storage-empty">暂未配置存储 · 点击"添加存储"开始</div>';
 return;
 }

 listEl.innerHTML = data.storages.map(s => {
 const typeIcon = STORAGE_TYPE_ICONS[s.type] || '💾';
 const typeName = STORAGE_TYPE_NAMES[s.type] || s.type;
 const usagePercent = s.usage_percent || 0;
 const statusClass = s.status === 'healthy' ? 'status-healthy' : 'status-error';

 return `
 <div class="storage-item" data-storage-id="${s.id}">
 <div class="storage-item-icon">${typeIcon}</div>
 <div class="storage-item-info">
 <div class="storage-item-name">${s.name}</div>
 <div class="storage-item-path">${s.path}</div>
 </div>
 <div class="storage-item-usage">
 <div class="usage-bar"><div class="usage-fill" style="width: ${usagePercent}%"></div></div>
 <span class="usage-text">${formatBytes(s.used_size)} / ${formatBytes(s.total_size)}</span>
 </div>
 <div class="storage-item-status ${statusClass}">● ${s.status === 'healthy' ? '正常' : '异常'}</div>
 <div class="storage-item-actions">
 <button class="btn btn-sm" onclick="scanStorage('${s.id}')">扫描</button>
 <button class="btn btn-sm" onclick="removeStorage('${s.id}')">移除</button>
 </div>
 </div>
 `;
 }).join('');
 })
 .catch(err => {
 listEl.innerHTML = '<div class="storage-empty">加载失败: ' + err.message + '</div>';
 });
}

function openStorageWizard() {
 const wizard = document.getElementById('storage-wizard');
 if (!wizard) return;

 wizard.hidden = false;
 storageWizard.currentStep = 1;
 storageWizard.selectedType = null;
 storageWizard.config = {};

 showWizardStep(1);
}

function closeStorageWizard() {
 const wizard = document.getElementById('storage-wizard');
 if (wizard) wizard.hidden = true;
}

function showWizardStep(step) {
 const stepType = document.getElementById('wizard-step-type');
 const stepConfig = document.getElementById('wizard-step-config');
 const footer = document.querySelector('.wizard-footer');

 if (step === 1) {
 stepType.classList.remove('hidden');
 stepConfig.classList.add('hidden');
 if (footer) footer.style.display = 'none';
 } else {
 stepType.classList.add('hidden');
 stepConfig.classList.remove('hidden');
 if (footer) footer.style.display = 'flex';
 }

 storageWizard.currentStep = step;
}

function wizardNext() {
 if (storageWizard.currentStep === 1 && storageWizard.selectedType) {
 generateConfigForm(storageWizard.selectedType);
 showWizardStep(2);
 }
}

function wizardPrev() {
 if (storageWizard.currentStep === 2) {
 showWizardStep(1);
 }
}

document.querySelectorAll('.storage-type-btn').forEach(btn => {
 btn.addEventListener('click', () => {
 document.querySelectorAll('.storage-type-btn').forEach(b => b.classList.remove('selected'));
 btn.classList.add('selected');
 storageWizard.selectedType = btn.dataset.type;
 });
});

function generateConfigForm(type) {
 const form = document.getElementById('storage-config-form');
 const title = document.getElementById('wizard-title');

 title.textContent = '添加 ' + STORAGE_TYPE_NAMES[type];

 let html = '<div class="form-group"><label>名称</label><input type="text" id="cfg-name" placeholder="存储名称"></div>';

 switch(type) {
 case 'local_disk':
 html += `
 <div class="form-group"><label>挂载点</label><input type="text" id="cfg-mount-points" placeholder="如 C:\\ 或 /home" value="C:\\"></div>
 `;
 break;
 case 'nas':
 html += `
 <div class="form-group"><label>协议</label><select id="cfg-protocol"><option value="smb">SMB/CIFS</option><option value="nfs">NFS</option></select></div>
 <div class="form-group"><label>主机地址</label><input type="text" id="cfg-host" placeholder="192.168.1.100"></div>
 <div class="form-group"><label>共享名称</label><input type="text" id="cfg-share" placeholder="shared"></div>
 <div class="form-group"><label>用户名</label><input type="text" id="cfg-username" placeholder="admin"></div>
 <div class="form-group"><label>密码</label><input type="password" id="cfg-password" placeholder="密码"></div>
 `;
 break;
 case 'usb':
 html += `
 <div class="form-group"><label>自动检测</label><select id="cfg-auto-detect"><option value="true">是</option><option value="false">否</option></select></div>
 `;
 break;
 case 'cloud':
 html += `
 <div class="form-group"><label>服务商</label><select id="cfg-provider"><option value="aws">AWS S3</option><option value="aliyun">阿里云 OSS</option><option value="tencent">腾讯云 COS</option><option value="minio">MinIO</option></select></div>
 <div class="form-group"><label>Bucket 名称</label><input type="text" id="cfg-bucket" placeholder="my-bucket"></div>
 <div class="form-group"><label>Region</label><input type="text" id="cfg-region" placeholder="us-east-1"></div>
 <div class="form-group"><label>Access Key</label><input type="text" id="cfg-access-key" placeholder="AKIA..."></div>
 <div class="form-group"><label>Secret Key</label><input type="password" id="cfg-secret-key" placeholder="..."></div>
 `;
 break;
 case 'raid':
 html += `
 <div class="form-group"><label>RAID 类型</label><select id="cfg-raid-type"><option value="megaraid">MegaRAID</option><option value="hardware">硬件 RAID</option></select></div>
 <div class="form-group"><label>适配器 ID</label><input type="text" id="cfg-adapter-id" placeholder="0" value="0"></div>
 `;
 break;
 }

 form.innerHTML = html;
}

document.addEventListener('click', e => {
 if (e.target.classList.contains('wizard-overlay')) {
 closeStorageWizard();
 }
});

function submitStorage() {
 const type = storageWizard.selectedType;
 const config = { type };

 const name = document.getElementById('cfg-name')?.value;
 if (name) config.name = name;

 switch(type) {
 case 'local_disk':
 config.config = { mount_points: [document.getElementById('cfg-mount-points')?.value || 'C:\\'] };
 break;
 case 'nas':
 config.config = {
 protocol: document.getElementById('cfg-protocol')?.value,
 host: document.getElementById('cfg-host')?.value,
 share: document.getElementById('cfg-share')?.value,
 username: document.getElementById('cfg-username')?.value,
 password: document.getElementById('cfg-password')?.value
 };
 break;
 case 'usb':
 config.config = { auto_detect: document.getElementById('cfg-auto-detect')?.value === 'true' };
 break;
 case 'cloud':
 config.config = {
 provider: document.getElementById('cfg-provider')?.value,
 bucket: document.getElementById('cfg-bucket')?.value,
 region: document.getElementById('cfg-region')?.value,
 access_key: document.getElementById('cfg-access-key')?.value,
 secret_key: document.getElementById('cfg-secret-key')?.value
 };
 break;
 case 'raid':
 config.config = {
 raid_type: document.getElementById('cfg-raid-type')?.value,
 adapter_id: parseInt(document.getElementById('cfg-adapter-id')?.value || '0')
 };
 break;
 }

 fetch('/api/storages', {
 method: 'POST',
 headers: { 'Content-Type': 'application/json' },
 body: JSON.stringify(config)
 })
 .then(r => r.json())
 .then(data => {
 if (data.status === 'ok') {
 inform('存储添加成功');
 closeStorageWizard();
 loadStorages();
 } else {
 inform('添加失败: ' + (data.error || '未知错误'));
 }
 })
 .catch(err => inform('添加失败: ' + err.message));
}

function scanStorage(storageId) {
 inform('正在扫描存储...');
 fetch(`/api/storages/${storageId}/scan`, { method: 'POST' })
 .then(r => r.json())
 .then(data => {
 inform(`扫描完成: 发现 ${data.files_count} 个文件`);
 })
 .catch(err => inform('扫描失败: ' + err.message));
}

function removeStorage(storageId) {
 if (!confirm('确定要移除此存储?')) return;

 fetch(`/api/storages/${storageId}`, { method: 'DELETE' })
 .then(r => r.json())
 .then(data => {
 if (data.status === 'ok') {
 inform('存储已移除');
 loadStorages();
 } else {
 inform('移除失败: ' + (data.error || '未知错误'));
 }
 })
 .catch(err => inform('移除失败: ' + err.message));
}

function scanAllStorages() {
 inform('正在扫描所有存储...');
 fetch('/api/storages')
 .then(r => r.json())
 .then(data => {
 if (data.storages && data.storages.length > 0) {
 const ids = data.storages.map(s => s.id);
 let completed = 0;
 ids.forEach(id => {
 fetch(`/api/storages/${id}/scan`, { method: 'POST' })
 .then(() => {
 completed++;
 if (completed === ids.length) {
 inform('所有存储扫描完成');
 }
 });
 });
 } else {
 inform('暂无存储可扫描');
 }
 })
 .catch(err => inform('扫描失败: ' + err.message));
}

function findDuplicates() {
 inform('正在查找重复文件...');
 fetch('/api/duplicates/find', {
 method: 'POST',
 headers: { 'Content-Type': 'application/json' },
 body: JSON.stringify({})
 })
 .then(r => r.json())
 .then(data => {
 if (data.total_groups > 0) {
 inform(`发现 ${data.total_groups} 组重复文件，共 ${formatBytes(data.total_wasted_size)} 浪费空间`);
 } else {
 inform('未发现重复文件');
 }
 })
 .catch(err => inform('查找失败: ' + err.message));
}

function refreshStorages() {
 loadStorages();
 inform('存储状态已刷新');
}

// Load storages when volumes tab is shown
const volumesTab = document.querySelector('[data-tab="volumes"]');
if (volumesTab) {
 volumesTab.addEventListener('click', () => {
 setTimeout(loadStorages, 100);
 });
}

// Initial load
if (document.getElementById('storage-list')) {
 loadStorages();
}

// Update hash support for volumes tab
const validTabs = ['dashboard','semantic','distributed','volumes','audit','roi'];
if (validTabs.includes(initialTab)) {
 switchTab(initialTab);
}
