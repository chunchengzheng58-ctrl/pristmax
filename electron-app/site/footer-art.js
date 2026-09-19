/** Pristmax - All Rights Reserved. Copyright © 2024-2026 */
(()=>{
 const scene=document.querySelector('.footer-landscape'),footer=scene?.closest('footer');
 if(!footer)return;
 const noise=scene.querySelector('feTurbulence'),bamboo=scene.querySelector('.living-bamboo');
 const reduced=matchMedia('(prefers-reduced-motion: reduce)');
 let visible=false,stopped=false,frame=0,last=0,time=0,timer=0,atBottom=false,queued=false;
 const mix=(a,b,t)=>'rgb('+a.map((v,i)=>Math.round(v+(b[i]-v)*t)).join(',')+')';
 function tick(now){frame=requestAnimationFrame(tick);if(now-last<42)return;
  time+=Math.min((now-last)/1000,.1);last=now;
  noise?.setAttribute('baseFrequency','0.012 '+(.065+Math.sin(time*.6)*.006));
  bamboo?.setAttribute('transform','rotate('+(Math.sin(time*.75)*.23)+' 2110 724)');
 }
 function update(){cancelAnimationFrame(frame);frame=0;
  const paused=stopped||reduced.matches||!visible||document.hidden;
  scene.classList.toggle('art-paused',paused);scene.classList.toggle('art-reduced',reduced.matches);
  if(!paused){last=performance.now();frame=requestAnimationFrame(tick)}
 }
 function scroll(){queued=false;
  const r=footer.getBoundingClientRect();
  const t=reduced.matches?1:Math.max(0,Math.min(1,(innerHeight*.9-r.top)/(innerHeight*.7)));
  footer.style.setProperty('--footer-bg',mix([255,255,255],[17,53,119],t));
  footer.style.setProperty('--footer-ink',mix([17,53,119],[229,238,255],t));
  footer.style.setProperty('--footer-logo',t<.5?'0':'1');
  const bottom=document.documentElement.scrollHeight-innerHeight-scrollY<=12;
  if(bottom&&!atBottom){timer=setTimeout(()=>{stopped=true;update()},10000)}
  if(!bottom&&atBottom){clearTimeout(timer);stopped=false;update()}
  atBottom=bottom;
 }
 function schedule(){if(!queued){queued=true;requestAnimationFrame(scroll)}}
 addEventListener('scroll',schedule,{passive:true});addEventListener('resize',schedule);
 addEventListener('pageshow',schedule);addEventListener('load',schedule);
 reduced.addEventListener('change',()=>{update();scroll()});
 document.addEventListener('visibilitychange',update);
 if('IntersectionObserver'in window)new IntersectionObserver(es=>{visible=es[0].isIntersecting;update()},{threshold:.05}).observe(scene);
 else visible=true;
 update();scroll();
})();
