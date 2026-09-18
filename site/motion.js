// Motion is progressive enhancement: content stays visible without JavaScript.
(()=>{
 const scene=document.querySelector('.footer-landscape');if(!scene)return;
 const panels=[...scene.querySelectorAll('.landscape-panel')];
 const reduced=matchMedia('(prefers-reduced-motion: reduce)');let pending=false;
 const clamp=x=>Math.max(0,Math.min(1,x));
 function render(){pending=false;const r=scene.getBoundingClientRect();
 const progress=clamp((innerHeight-r.top)/Math.min(r.height+80,innerHeight*.8));
 scene.style.setProperty('--pan',reduced.matches?0:progress);
 panels.forEach((panel,i)=>{const t=reduced.matches?1:clamp((progress-i*.055)/.72);const ease=1-Math.pow(1-t,3);
 panel.style.setProperty('--rise',`${(1-ease)*(160+i%3*45)}px`);
 panel.style.setProperty('--zoom',1+(1-ease)*.12);
 panel.style.setProperty('--shown',.12+ease*.88);
 });
 }
 const schedule=()=>{if(!pending){pending=true;requestAnimationFrame(render)}};
 addEventListener('scroll',schedule,{passive:true});addEventListener('resize',schedule);addEventListener('pageshow',schedule);reduced.addEventListener('change',schedule);render();
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
