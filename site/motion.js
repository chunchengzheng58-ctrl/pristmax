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

// Motion is progressive enhancement: content stays visible without JavaScript.
(()=>{
 const reduced=matchMedia('(prefers-reduced-motion: reduce)');
 const targets=document.querySelectorAll('.section-inner,.feature-card,.console-frame,.workflow-step,.download-card,.statement-inner,.flight-section');
 if(!reduced.matches && 'IntersectionObserver' in window){
  const observer=new IntersectionObserver(entries=>entries.forEach(e=>{if(e.isIntersecting){e.target.classList.add('revealed');observer.unobserve(e.target)}}),{threshold:.08});
  targets.forEach((el,i)=>{el.classList.add('reveal-ready');el.style.setProperty('--reveal-delay',`${Math.min(i%3,2)*70}ms`);observer.observe(el)});
 }
 const section=document.querySelector('.section-download');let queued=false;
 function paint(){queued=false;const r=section.getBoundingClientRect();const t=Math.max(0,Math.min(1,(innerHeight-r.top)/(innerHeight*.75)));section.style.setProperty('--frame',reduced.matches?1:t);document.querySelector('#site-header').classList.toggle('scrolled',scrollY>40)}
 addEventListener('scroll',()=>{if(!queued){queued=true;requestAnimationFrame(paint)}},{passive:true});addEventListener('resize',paint);paint();
 const footer=document.querySelector('footer');if('IntersectionObserver' in window){new IntersectionObserver(es=>es.forEach(e=>footer.classList.toggle('in-view',e.isIntersecting)),{threshold:.1}).observe(footer)}
 reduced.addEventListener('change',()=>{if(reduced.matches)targets.forEach(el=>el.classList.add('revealed'));paint()});
})();

(()=>{
 const opening=document.querySelector('.opening');if(!opening)return;
 const screen=opening.querySelector('.opening-screen');const reduced=matchMedia('(prefers-reduced-motion: reduce)');let pending=false;
 const mix=(a,b,t)=>`rgb(${a.map((v,i)=>Math.round(v+(b[i]-v)*t)).join(',')})`;
 function render(){pending=false;const r=opening.getBoundingClientRect();const distance=Math.max(1,opening.offsetHeight-innerHeight);let t=Math.max(0,Math.min(1,-r.top/distance));if(reduced.matches)t=0;
 screen.style.setProperty('--opening-bg',mix([7,13,18],[255,255,255],t));
 screen.style.setProperty('--opening-ink',mix([166,210,236],[71,127,159],t));
 screen.style.setProperty('--opening-small',mix([165,187,201],[64,96,119],t));
 screen.style.setProperty('--opening-scale',1-t*.04);
 screen.style.setProperty('--intro-progress',t);
 opening.querySelector('.opening-bottom').inert=t>.9;
 const content=opening.querySelector('.opening-content');content.style.visibility=t>.45||reduced.matches?'visible':'hidden';content.inert=t<=.45&&!reduced.matches;
 const active=!reduced.matches && t<.85 && r.bottom>0;document.body.classList.toggle('opening-active',active);document.getElementById('site-header').inert=active;
 }
 opening.querySelector('.opening-bottom a').addEventListener('click',e=>{e.preventDefault();scrollTo({top:scrollY+opening.getBoundingClientRect().top+Math.max(0,opening.offsetHeight-innerHeight),behavior:reduced.matches?'instant':'smooth'});});
 addEventListener('scroll',()=>{if(!pending){pending=true;requestAnimationFrame(render)}},{passive:true});addEventListener('resize',render);addEventListener('pageshow',render);reduced.addEventListener('change',render);render();
})();

// SVG landscape footer: scroll-driven layered reveal
(()=>{
 const footer=document.querySelector('footer');
 const landscape=document.querySelector('.footer-landscape svg');
 if(!footer||!landscape)return;
 const reduced=matchMedia('(prefers-reduced-motion: reduce)');
 const layers=[
  {sel:'.layer-sky',             fadeStart:0.0, fadeEnd:0.08},
  {sel:'.layer-far-mountains',   fadeStart:0.05,fadeEnd:0.22},
  {sel:'.layer-mist-far',        fadeStart:0.08,fadeEnd:0.25},
  {sel:'.layer-mid-mountains-blue',fadeStart:0.15,fadeEnd:0.35},
  {sel:'.layer-mid-mountains-turq',fadeStart:0.22,fadeEnd:0.42},
  {sel:'.layer-mist-mid',        fadeStart:0.30,fadeEnd:0.50},
  {sel:'.layer-near-mountains',  fadeStart:0.38,fadeEnd:0.58},
  {sel:'.layer-river',           fadeStart:0.45,fadeEnd:0.62},
  {sel:'.layer-pavilions',       fadeStart:0.52,fadeEnd:0.70},
  {sel:'.layer-pines',           fadeStart:0.55,fadeEnd:0.72},
  {sel:'.layer-mist-near',      fadeStart:0.60,fadeEnd:0.78},
  {sel:'.layer-foreground',      fadeStart:0.68,fadeEnd:0.85},
 ];
 const svgEl=landscape;
 let pending=false;
 function apply(){
  pending=false;
  const r=footer.getBoundingClientRect();
  const total=footer.offsetHeight;
  const scrolled=Math.max(0,-r.top);
  const progress=reduced.matches?1:Math.min(1,scrolled/(total-innerHeight));
  layers.forEach(({sel,fadeStart,fadeEnd})=>{
   const el=svgEl.querySelector(sel);
   if(!el)return;
   const t=Math.max(0,Math.min(1,(progress-fadeStart)/(fadeEnd-fadeStart)));
   el.style.opacity=t;
  });
  footer.classList.toggle('in-view',r.top<innerHeight&&r.bottom>0);
 }
 const schedule=()=>{if(!pending){pending=true;requestAnimationFrame(apply)}};
 addEventListener('scroll',schedule,{passive:true});
 addEventListener('resize',schedule);
 addEventListener('pageshow',schedule);
 reduced.addEventListener('change',schedule);
 apply();
})();

