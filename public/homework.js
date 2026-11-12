// Weekly homework: teachers assign a saved game with a due date and see who has finished how many questions;
// students work through the questions in a plain chat (or the tower) and the credit is saved to their account.
const Homework=(function(){
 const fmt=t=>t?new Date(t*1000).toLocaleString([],{weekday:'short',month:'short',day:'numeric',hour:'numeric',minute:'2-digit'}):'no due date';
 const bar=(done,total)=>`<span class="hw-bar" role="img" aria-label="${done} of ${total}"><i style="width:${total?Math.min(100,100*done/total):0}%"></i></span>`;
 function overlay(html){
  document.getElementById('hw-view')?.remove();
  const el=document.createElement('div');el.id='hw-view';el.className='modal';el.setAttribute('role','dialog');el.setAttribute('aria-modal','true');
  el.innerHTML=`<div class="modal-card wide"><button class="close" aria-label="Close">×</button>${html}</div>`;
  document.body.append(el);el.querySelector('.close').onclick=()=>el.remove();el.onclick=e=>{if(e.target===el)el.remove()};
  return el;
 }
 const user=()=>window.Classes?.user;
 async function open(){
  if(!user())return toast('Sign in first.');
  user().role==='teacher'?teacherView():studentView();
 }
 // ---------------- students
 async function studentView(){
  let list=[];try{list=(await api('/api/hw/list',{})).assignments}catch(e){return toast(e.message)}
  const el=overlay(`<div class="eyebrow">HOMEWORK</div><h2>${list.length?'Your assignments':'No homework yet.'}</h2>${list.map(a=>`<div class="hw-card"><div class="hw-top"><strong>${esc(a.title)}</strong><span class="muted">${esc(a.className)} · due ${esc(fmt(a.due))}</span></div><div class="hw-row">${bar(a.done,a.total)}<b>${a.done} / ${a.total}</b><span class="muted">${a.percent}%</span></div>${a.done>=a.total?'<p class="hw-done">🎉 All questions complete. Nice work!</p>':`<p class="muted">A question counts when you get it right. You can try again as many times as you like, and each try can show a fresh version.</p><div class="toolbar"><button class="primary small" data-start="${esc(a.id)}" data-type="chat">📘 Start the quiz</button><button class="small" data-start="${esc(a.id)}" data-type="climb">🧗 Tower climb</button><button class="small" data-start="${esc(a.id)}" data-type="station">🕵️ Imposter practice</button></div>`}</div>`).join('')||'<p>Your teacher has not assigned anything yet.</p>'}`);
  el.querySelectorAll('[data-start]').forEach(b=>b.onclick=()=>begin(b.dataset.start,b.dataset.type,b));
 }
 async function begin(assignmentId,gameType,btn){
  if(btn)btn.disabled=true;
  try{
   const created=await api('/api/create',{assignmentId,gameType});
   const joined=await api('/api/join',{code:created.code,name:user().name,look:storageGet('mm-look',null)||undefined});
   session={code:created.code,token:joined.token,relaxed:false};storageSet('mm-session',session);
   document.getElementById('hw-view')?.remove();closeModal?.();enterGame(joined);showRules(true);
  }catch(e){toast(e.message)}finally{if(btn)btn.disabled=false}
 }
 // ---------------- teachers
 async function teacherView(){
  let list=[],classes=window.Classes.classes||[];
  try{list=(await api('/api/hw/list',{})).assignments}catch(e){return toast(e.message)}
  const el=overlay(`<div class="eyebrow">HOMEWORK</div><h2>Weekly assignments</h2>
   ${list.map(a=>`<div class="hw-card"><div class="hw-top"><strong>${esc(a.title)}</strong><span class="muted">${esc(a.className)} · opens ${esc(fmt(a.open))} · due ${esc(fmt(a.due))}</span></div><div class="hw-row">${bar(a.avgPercent,100)}<b>${a.avgPercent}% average</b><span class="muted">${a.finished} of ${a.students} students finished all ${a.total}</span></div><div class="toolbar"><button class="small primary" data-report="${esc(a.id)}">📊 Who has done what</button><button class="small danger" data-del="${esc(a.id)}">Delete</button></div></div>`).join('')||'<p>No assignments yet. Create one below.</p>'}
   ${classes.length?`<div class="toolbar"><span class="muted">Gradebook for a class:</span>${classes.map(c=>`<button class="small" data-export="${esc(c.id)}">⬇️ ${esc(c.name)} (.csv for Google Sheets)</button>`).join('')}</div>`:''}
   <h3>New assignment</h3>
   <label for="hw-class">Class</label><select id="hw-class">${classes.map(c=>`<option value="${esc(c.id)}">${esc(c.name)}</option>`).join('')||'<option value="">Create a class first</option>'}</select>
   <label for="hw-pack">Saved game (its questions are the assignment)</label><select id="hw-pack"><option value="">Loading…</option></select>
   <label for="hw-title">Title</label><input id="hw-title" maxlength="120" placeholder="Week 12: Forces">
   <div class="two"><div><label for="hw-open">Opens</label><input id="hw-open" type="datetime-local"></div><div><label for="hw-due">Due</label><input id="hw-due" type="datetime-local"></div></div>
   <button id="hw-create" class="primary wide">Create assignment</button>`);
  try{const r=await api('/api/pack/list',{});const sel=el.querySelector('#hw-pack');sel.innerHTML=r.packs.map(p=>`<option value="${esc(p.id)}" data-title="${esc(p.title)}">${esc(p.title)} (${p.questions} questions)</option>`).join('')||'<option value="">Save a game in Build your game first</option>'}catch{}
  const toTs=v=>v?new Date(v).getTime()/1000:null;
  el.querySelector('#hw-create').onclick=async()=>{
   const sel=el.querySelector('#hw-pack');
   try{await api('/api/hw/create',{classId:el.querySelector('#hw-class').value,packId:sel.value,title:el.querySelector('#hw-title').value.trim()||sel.selectedOptions[0]?.dataset.title,openAt:toTs(el.querySelector('#hw-open').value),due:toTs(el.querySelector('#hw-due').value)});toast('Assignment created.');teacherView()}catch(e){toast(e.message)}
  };
  el.querySelectorAll('[data-report]').forEach(b=>b.onclick=()=>report(b.dataset.report));
  el.querySelectorAll('[data-del]').forEach(b=>b.onclick=async()=>{if(!confirm('Delete this assignment? Students will no longer see it. Their saved credit is kept in case you create it again.'))return;try{await api('/api/hw/delete',{id:b.dataset.del});teacherView()}catch(e){toast(e.message)}});
  el.querySelectorAll('[data-export]').forEach(b=>b.onclick=async()=>{try{const r=await api('/api/hw/export',{classId:b.dataset.export});download(r.filename,r.csv,'text/csv')}catch(e){toast(e.message)}});
 }
 async function report(id){
  let r;try{r=await api('/api/hw/report',{id})}catch(e){return toast(e.message)}
  const el=overlay(`<button class="back" id="hw-back">← Assignments</button><div class="eyebrow">${esc(fmt(r.due))}</div><h2>${esc(r.title)}</h2><p class="muted">${r.total} questions. A question counts once the student answers it correctly; they can retry as often as they like.</p>
   <div class="roster-table">${r.students.map(s=>`<div class="rrow hw-student"><div><strong>${esc(s.name)}</strong><div class="muted">${esc(s.email)}</div></div><div class="hw-row">${bar(s.done,r.total)}<b>${s.done} / ${r.total}</b><span class="muted">${s.percent}%</span></div><span class="muted">${s.adjust?`adjusted ${s.adjust>0?'+':''}${s.adjust}${s.note?' · '+esc(s.note):''}<br>`:''}${s.pasted?`<b class="flag">⚠️ ${s.pasted} pasted answer${s.pasted>1?'s':''}</b><br>`:''}${s.last?'last credit '+esc(fmt(s.last)):'nothing yet'}</span><span class="toolbar"><button class="small" data-chats="${esc(s.email)}" data-name="${esc(s.name)}">💬 Chats</button><button class="small" data-adjust="${esc(s.email)}" data-name="${esc(s.name)}" data-cur="${s.adjust}">± Adjust</button></span></div>`).join('')||'<p>No students in this class yet.</p>'}</div>`);
  el.querySelector('#hw-back').onclick=teacherView;
  el.querySelectorAll('[data-chats]').forEach(b=>b.onclick=()=>{document.getElementById('hw-view')?.remove();Classes.transcript(r.classId,b.dataset.chats,b.dataset.name)});
  el.querySelectorAll('[data-adjust]').forEach(b=>b.onclick=async()=>{
   const v=prompt(`Add or remove credited questions for ${b.dataset.name}. Enter a number like 2 or -1 (currently ${b.dataset.cur}).`,b.dataset.cur);if(v===null)return;
   const note=prompt('Short note for your records (optional):','')||'';
   try{await api('/api/hw/adjust',{id,email:b.dataset.adjust,delta:Number(v),note});report(id)}catch(e){toast(e.message)}
  });
 }
 // ---------------- the plain chat screen
 async function nextQuestion(){
  const btn=document.getElementById('hw-next');if(btn)btn.disabled=true;
  try{const epoch=++encounterEpoch;reqId=null;const data=await api('/api/start',auth({}));if(epoch===encounterEpoch){state=data;syncEncounter(true);}}catch(e){toast(e.message)}finally{if(btn)btn.disabled=false}
 }
 let lastDone=-1;
 function chatScreen(){
  const on=!!state&&state.room.gameType==='chat';document.body.classList.toggle('hw-chat',on);
  const hw=state?.player?.hw;
  if(hw){
   if(lastDone>=0&&hw.done>lastDone)toast('✅ That one counts! '+hw.done+' of '+hw.total+' done.');
   lastDone=hw.done;
   if(!on){const t=document.getElementById('mission-title');if(t)t.textContent=`${hw.title} · 📘 ${hw.done}/${hw.total} counted`}
  }else lastDone=-1;
  if(!on)return;
  let panel=document.getElementById('hw-panel');
  if(!panel){panel=document.createElement('section');panel.id='hw-panel';panel.className='panel hw-panel';document.querySelector('#game .game-bar').after(panel)}
  const finished=hw.total&&hw.done>=hw.total;
  const html=`<div class="eyebrow">HOMEWORK</div><h2>${esc(hw.title)}</h2><div class="hw-row">${bar(hw.done,hw.total)}<b>${hw.done} / ${hw.total}</b><span class="muted">questions with credit</span></div>${finished?'<p class="hw-done">🎉 Every question has credit. You are finished with this assignment!</p>':`<p class="muted">Answer each question. A question counts when you give a solid explanation. If it does not count yet, just try again. You will see a fresh version.</p><button id="hw-next" class="primary wide">${hw.done?'Next question':'Start'} →</button>`}`;
  if(panel.dataset.sig!==html){panel.dataset.sig=html;panel.innerHTML=html;const b=panel.querySelector('#hw-next');if(b)b.onclick=nextQuestion}
  const ml=document.getElementById('mission-label');if(ml)ml.textContent='HOMEWORK QUIZ';
  const t=document.getElementById('encounter-title');if(t)t.textContent='📘 Question';
  const c=document.getElementById('closechat');if(c)c.textContent='✕ Back';
 }
 return {open,chatScreen};
})();
window.Homework=Homework;
