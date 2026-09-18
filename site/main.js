const menu=document.querySelector('.menu');const nav=document.querySelector('nav');if(menu&&nav){menu.addEventListener('click',()=>{const open=menu.getAttribute('aria-expanded')!=='true';menu.setAttribute('aria-expanded',String(open));nav.classList.toggle('open',open)});nav.addEventListener('click',e=>{if(e.target.closest('a')){nav.classList.remove('open');menu.setAttribute('aria-expanded','false')}});document.addEventListener('keydown',e=>{if(e.key==='Escape'){nav.classList.remove('open');menu.setAttribute('aria-expanded','false')}})}

// Storage Agent install tabs
document.querySelectorAll('.install-tab').forEach(tab=>{tab.addEventListener('click',()=>{const panelId='install-'+tab.dataset.tab;document.querySelectorAll('.install-tab').forEach(t=>t.classList.remove('active'));document.querySelectorAll('.install-panel').forEach(p=>p.classList.remove('active'));tab.classList.add('active');document.getElementById(panelId).classList.add('active')})});

// API tabs
document.querySelectorAll('.api-tab').forEach(tab=>{tab.addEventListener('click',()=>{const panelId='api-'+tab.dataset.api;document.querySelectorAll('.api-tab').forEach(t=>t.classList.remove('active'));document.querySelectorAll('.api-panel').forEach(p=>p.classList.remove('active'));tab.classList.add('active');document.getElementById(panelId).classList.add('active')})});

// Copy buttons
document.querySelectorAll('.copy-btn').forEach(btn=>{btn.addEventListener('click',()=>{const text=btn.dataset.copy;if(!text)return;navigator.clipboard.writeText(text.replace(/<br>/g,'\n'));btn.textContent='已复制!';btn.classList.add('copied');setTimeout(()=>{btn.textContent='复制';btn.classList.remove('copied')},2000)})});

// Terminal animation
const terminalLines=[
{cls:'prompt',text:'$ ',delay:0},{cls:'cmd',text:'python -m storage_agent --path /data --analyze',delay:100},
{cls:'',text:'',delay:800,br:true},
{cls:'output',text:'✓ 扫描完成，耗时 12.3s',delay:900},
{cls:'comment',text:'  总文件: 12,847 | 总大小: 128.5 GB',delay:1100},
{cls:'',text:'',delay:1400,br:true},
{cls:'prompt',text:'$ ',delay:1500},{cls:'cmd',text:'python -m storage_agent --large-files --min 100MB',delay:1600},
{cls:'',text:'',delay:2100,br:true},
{cls:'output',text:'✓ 找到 23 个大文件 (>100MB)',delay:2200},
{cls:'comment',text:'  #1  video/archive_2024.mp4 — 2.8 GB',delay:2400},
{cls:'comment',text:'  #2  backup/database.sql — 1.5 GB',delay:2550},
{cls:'',text:'',delay:2800,br:true},
{cls:'prompt',text:'$ ',delay:2900},{cls:'cmd',text:'python -m storage_agent --duplicates',delay:3000},
{cls:'',text:'',delay:3500,br:true},
{cls:'output',text:'✓ 找到 5 组重复文件，可节省 4.2 GB',delay:3600},
{cls:'cursor',text:'',delay:3800}];
let terminalTimeout=null;function playTerminal(){if(terminalTimeout)clearTimeout(terminalTimeout);const output=document.getElementById('terminal-output');if(!output)return;output.innerHTML='';terminalLines.forEach((line,i)=>{terminalTimeout=setTimeout(()=>{const el=document.createElement('div');el.className='terminal-line'+(line.br?' br':'');if(line.cls==='prompt')el.innerHTML='<span class="prompt">'+line.text+'</span>';else if(line.cls==='cmd')el.innerHTML='<span class="cmd">'+line.text+'</span>';else if(line.cls==='output')el.innerHTML='<span class="output">'+line.text+'</span>';else if(line.cls==='comment')el.innerHTML='<span class="comment">'+line.text+'</span>';else if(line.cls==='cursor')el.innerHTML='<span class="cursor"></span>';else if(line.br)return;output.appendChild(el);requestAnimationFrame(()=>el.classList.add('visible'));if(!line.br)output.scrollTop=output.scrollHeight},line.delay)})}

// Init terminal on load
document.querySelectorAll('#storage-terminal').forEach(term=>{const replayBtn=term.querySelector('.terminal-replay');if(replayBtn)replayBtn.addEventListener('click',playTerminal);const observer=new IntersectionObserver(entries=>{entries.forEach(entry=>{if(entry.isIntersecting)playTerminal()})},{threshold:0.5});observer.observe(term)});

// Counter animation
function animateCounters(){document.querySelectorAll('.stat-value[data-count]').forEach(el=>{const target=el.dataset.count;const isSpecial=target==='<'||target==='0';if(isSpecial)return;const num=parseInt(target);let current=0;const step=Math.ceil(num/30);const interval=setInterval(()=>{current+=step;if(current>=num){current=num;clearInterval(interval)}el.textContent=current},50)})}
const statsObserver=new IntersectionObserver(entries=>{entries.forEach(entry=>{if(entry.isIntersecting){animateCounters();statsObserver.disconnect()}})},{threshold:0.5});const statsEl=document.querySelector('.storage-stats');if(statsEl)statsObserver.observe(statsEl);

// CLI command navigation
const cliCommands=document.querySelectorAll('.cli-command');
const cliDots=document.querySelectorAll('.cli-dot');
const prevBtn=document.querySelector('.cli-nav-btn.prev');
const nextBtn=document.querySelector('.cli-nav-btn.next');
let currentCli=0;
function showCli(index){cliCommands.forEach((cmd,i)=>{cmd.classList.toggle('active',i===index)});cliDots.forEach((dot,i)=>{dot.classList.toggle('active',i===index)});prevBtn.disabled=index===0;nextBtn.disabled=index===cliCommands.length-1;currentCli=index}
if(prevBtn&&nextBtn){prevBtn.addEventListener('click',()=>{if(currentCli>0)showCli(currentCli-1)});nextBtn.addEventListener('click',()=>{if(currentCli<cliCommands.length-1)showCli(currentCli+1)});cliDots.forEach((dot,i)=>{dot.addEventListener('click',()=>showCli(i))})}

// Chart animation
const chartObserver=new IntersectionObserver(entries=>{entries.forEach(entry=>{if(entry.isIntersecting){document.querySelectorAll('.bar-fill').forEach((bar,index)=>{setTimeout(()=>{bar.style.width=bar.style.getPropertyValue('--fill')},index*100)});chartObserver.disconnect()}})},{threshold:0.3});const chartEl=document.querySelector('.storage-chart');if(chartEl)chartObserver.observe(chartEl);

// Interactive terminal suggestions
const terminalInput=document.getElementById('terminal-input');
if(terminalInput){terminalInput.addEventListener('focus',()=>{document.getElementById('terminal-suggestions').style.display='flex'});terminalInput.addEventListener('blur',()=>{setTimeout(()=>{document.getElementById('terminal-suggestions').style.display='none'},200)});terminalInput.addEventListener('input',function(){const val=this.value.toLowerCase();document.querySelectorAll('.suggestion').forEach(s=>{const cmd=s.dataset.cmd.toLowerCase();s.style.opacity=val&&!cmd.includes(val.replace('--',''))?'0.3':'1'})});document.querySelectorAll('.suggestion').forEach(s=>{s.addEventListener('click',function(){terminalInput.value=this.dataset.cmd;terminalInput.focus()})})}
