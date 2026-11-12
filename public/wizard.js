// Step-by-step setup for the teacher's "Build your game" page. It only moves between the four sections and writes the launch summary; every field keeps its own id and behaviour.
(function(){
 const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
 const setup=$('#setup');if(!setup)return;
 let cur=1;
 function go(n){
  cur=Math.max(1,Math.min(4,n));
  $$('#setup .wiz').forEach(p=>p.classList.toggle('on',Number(p.dataset.step)===cur));
  $$('#wiz-steps li').forEach((li,i)=>{li.classList.toggle('on',i+1===cur);li.classList.toggle('done',i+1<cur)});
  if(cur===4)summary();
  window.scrollTo({top:0,behavior:'smooth'});
 }
 const txt=sel=>{const e=$(sel);return e&&e.selectedOptions&&e.selectedOptions[0]?e.selectedOptions[0].textContent.replace(/^[^A-Za-z]+/,'').trim():''};
 function summary(){
  const box=$('#launch-summary');if(!box)return;
  let n=0;try{n=(pack&&pack.topics&&pack.topics.length)||0}catch{}
  const mc=$('#fmt-mc')&&$('#fmt-mc').checked,fr=$('#fmt-free')&&$('#fmt-free').checked;
  const how=mc&&fr?'multiple choice, then a written explanation':mc?'multiple choice':'written answers';
  const parts=[];
  parts.push('<b>'+esc($('#packtitle').value.trim()||'Your game')+'</b>');
  parts.push(esc(txt('#gamemode')||'Game'));
  parts.push(n?n+' question'+(n===1?'':'s')+' each, '+how:'');
  parts.push($('#unlimited')&&$('#unlimited').checked?'no time limit':'timed answers');
  if($('#gamemode').value==='infiltration'){
   const m=Number($('#meeting-minutes').value);parts.push(m?'meetings about every '+m+' min':'no automatic meetings');
   if($('#round-timer-on').checked)parts.push($('#round-minutes').value+' minute round');
  }
  const cp=$('#classpick');if(cp&&cp.selectedOptions[0])parts.push('for '+esc(cp.selectedOptions[0].textContent.trim()));
  box.innerHTML=parts.filter(Boolean).join(' · ')+(n?'':'<br><span class="warn">No questions yet. Go back to step 2 and press “Create questions”.</span>');
  box.classList.toggle('bad',!n);
 }
 function esc(t){return String(t).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
 setup.addEventListener('click',e=>{const b=e.target.closest('[data-wiz]');if(b){e.preventDefault();go(Number(b.dataset.wiz))}});
 // Start from step 1 each time the page is opened.
 let wasHidden=setup.classList.contains('hidden');
 new MutationObserver(()=>{const h=setup.classList.contains('hidden');if(wasHidden&&!h)go(1);wasHidden=h}).observe(setup,{attributes:true,attributeFilter:['class']});
 // The access-code box only appears when the server asks for one.
 try{if(config&&config.teacherProtected)$('#key-box').classList.remove('hidden')}catch{}
 setTimeout(()=>{try{if(config&&config.teacherProtected)$('#key-box').classList.remove('hidden')}catch{}},800);
 go(1);
})();

// Tower climb offers different ways to play than the space station, so the "How the class plays" list follows the game choice.
(function(){
  const gt=$('#gametype'),gm=$('#gamemode');if(!gt||!gm)return;
  const station=gm.innerHTML;
  function syncGameType(){const cur=gm.value;gm.innerHTML=gt.value==='climb'?'<option value="coop" selected>🧗 Class climb: everyone climbs together</option><option value="race">🏁 Two-team climbing race</option>':station;if([...gm.options].some(o=>o.value===cur))gm.value=cur;gm.dispatchEvent(new Event('change'))}
  gt.addEventListener('change',syncGameType);
  const orig=window.settingsApply;
  if(typeof orig==='function')window.settingsApply=function(s){const mode=s?.mode,r=orig.apply(this,arguments);syncGameType();if(mode&&[...gm.options].some(o=>o.value===mode))gm.value=mode;gm.dispatchEvent(new Event('change'));return r};
})();

// After the questions are created, move on to review them.
(function(){const g=document.getElementById('generate');if(!g)return;let was=false;new MutationObserver(()=>{const busy=g.disabled;if(was&&!busy&&(typeof pack!=='undefined'&&pack?.topics?.length)&&!document.querySelector('#generate-note')?.textContent.match(/couldn|error|failed/i))document.getElementById('wiz-next-1')?.click();was=busy}).observe(g,{attributes:true,attributeFilter:['disabled']})})();
