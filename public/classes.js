'use strict';
// Accounts and classes: Google sign-in, teacher class dashboard, student class list.
// Only active when the server reports authMode === 'classes'. Uses helpers from app.js ($, esc, api, toast).
const Classes=(()=>{
 let user=null,classes=[],cfg=null,gsiReady=false;
 const KEY='mm-user-token',JOIN='mm-pending-join',fmt=t=>t?new Date(t*1000).toLocaleString([],{dateStyle:'medium',timeStyle:'short'}):'never';
 const get=k=>{try{return localStorage.getItem(k)}catch{return null}},put=(k,v)=>{try{v==null?localStorage.removeItem(k):localStorage.setItem(k,v)}catch{}};
 const token=()=>get(KEY)||'';
 function overlay(id,html,{closable=true,wide=false}={}){
  document.getElementById(id)?.remove();
  const el=document.createElement('div');el.id=id;el.className='modal';el.setAttribute('role','dialog');el.setAttribute('aria-modal','true');
  el.innerHTML=`<div class="modal-card ${wide?'wide':''}">${closable?'<button class="close" aria-label="Close">×</button>':''}${html}</div>`;
  document.body.append(el);
  if(closable){el.querySelector('.close').onclick=()=>el.remove();el.onclick=e=>{if(e.target===el)el.remove()}}
  return el;
 }
 const close=id=>document.getElementById(id)?.remove();
 async function call(path,data={}){return api(path,data)}

 // ---------- sign-in
 function loadGsi(){return new Promise((res,rej)=>{if(window.google?.accounts?.id)return res();const s=document.createElement('script');s.src='https://accounts.google.com/gsi/client';s.async=true;s.onload=res;s.onerror=()=>rej(Error('Could not load Google sign-in.'));document.head.append(s)})}
 async function signInScreen(message=''){
  close('classes-view');close('alert-view');
  const el=overlay('signin',`<div class="eyebrow">WELCOME</div><h2>Sign in with your school Google account.</h2><p>Students use their school account. Teachers use their teacher account. Your teacher shares an invite link to put you in a class.</p>${message?`<p class="notice">${esc(message)}</p>`:''}<div id="g-button" style="min-height:44px;margin-top:18px"></div><p id="g-error" class="hint-text"></p>`,{closable:false});
  try{
   await loadGsi();
   google.accounts.id.initialize({client_id:cfg.googleClientId,callback:r=>onCredential(r.credential),auto_select:false,hd:'*'});
   google.accounts.id.renderButton(el.querySelector('#g-button'),{theme:'filled_blue',size:'large',shape:'pill',text:'signin_with'});
  }catch(e){el.querySelector('#g-error').textContent=e.message+(cfg.googleClientId?'':' The server has no Google client ID configured.')}
 }
 async function onCredential(credential){
  try{
   const r=await fetch('/api/auth/google',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({credential})});
   const data=await r.json();if(!r.ok)throw Error(data.error||'Sign-in failed.');
   put(KEY,data.userToken);user=data.user;classes=data.classes;close('signin');afterSignIn();
  }catch(e){const n=document.querySelector('#g-error');if(n)n.textContent=e.message;else toast(e.message)}
 }
 async function signOut(){try{await call('/api/auth/logout',{})}catch{}put(KEY,null);user=null;classes=[];renderAccount();signInScreen()}
 function needSignIn(message){put(KEY,null);user=null;renderAccount();signInScreen(message||'Please sign in again.')}

 // ---------- header account control
 function renderAccount(){
  let box=document.getElementById('account');
  if(!box){box=document.createElement('div');box.id='account';box.className='account';document.querySelector('.header-right').prepend(box)}
  box.innerHTML=user?`<span class="who" title="${esc(user.email)}">${esc(user.name)} · ${user.role}</span><button class="quiet" id="acct-classes">${user.role==='teacher'?'🏫 Classes':'🏫 My classes'}</button><button class="quiet" id="acct-out">Sign out</button>`:'';
  if(user){box.querySelector('#acct-classes').onclick=openClasses;box.querySelector('#acct-out').onclick=signOut}
  const teacherCard=document.getElementById('teacher');if(teacherCard)teacherCard.classList.toggle('hidden',!!user&&user.role!=='teacher');
 }

 async function afterSignIn(){
  renderAccount();
  const code=get(JOIN);
  if(code&&user.role==='student'){
   try{const c=await call('/api/class/join',{code});put(JOIN,null);classes=(await call('/api/class/list')).classes;toast(`You joined ${c.name}. Room codes from your teacher will work now.`);history.replaceState(null,'',location.pathname)}
   catch(e){put(JOIN,null);overlay('join-error',`<div class="eyebrow">INVITE</div><h2>That invite did not work.</h2><p>${esc(e.message)}</p>`)}
  }else if(code){put(JOIN,null);toast('Invite links are for students. Open it in a student account to join.')}
  const alertId=new URLSearchParams(location.search).get('alert');
  if(alertId&&user.role==='teacher'){history.replaceState(null,'',location.pathname);openAlert(alertId)}
  populateClassPick();
  if(user.role==='teacher'){packsMount();libMount();materialMount()}
 }

 // ---------- teacher / student class screen
 async function refresh(){classes=(await call('/api/class/list')).classes}
 async function openClasses(){
  try{await refresh()}catch(e){return toast(e.message)}
  user.role==='teacher'?teacherHome():studentHome();
 }
 function studentHome(){
  const el=overlay('classes-view',`<div class="eyebrow">YOUR CLASSES</div><h2>${classes.length?'Ready to play.':'No class yet.'}</h2>${classes.length?`<ul class="plain">${classes.map(c=>`<li><strong>${esc(c.name)}</strong> <span class="muted">${c.teacher?'· '+esc(c.teacher):''}</span></li>`).join('')}</ul><p>Use the room code your teacher shares and choose “Join your crew.”</p>`:'<p>Ask your teacher for an invite link, then open it while signed in.</p>'}<label for="invite-code">Have an invite code?</label><input id="invite-code" placeholder="Paste invite code or link"><button id="join-invite" class="primary wide">Join class</button>`);
  el.querySelector('#join-invite').onclick=async()=>{let v=el.querySelector('#invite-code').value.trim();try{v=new URL(v).searchParams.get('join')||v}catch{}try{const c=await call('/api/class/join',{code:v});toast('Joined '+c.name);await refresh();studentHome();populateClassPick()}catch(e){toast(e.message)}};
 }
 async function teacherHome(){
  let alerts=[];try{alerts=(await call('/api/class/alerts')).alerts}catch{}
  const open=alerts.filter(a=>!a.reviewed);
  const el=overlay('classes-view',`<div class="eyebrow">YOUR CLASSES</div><h2>Classes &amp; students</h2>
  ${open.length?`<div class="info-box alerts"><strong>⚠️ ${open.length} safety alert${open.length>1?'s':''} to review</strong>${open.map(a=>`<div class="alert-row"><span>${esc(a.label)} · ${esc(a.student_name)} · ${esc(a.class_name)} · ${fmt(a.created)}</span><span class="muted">email: ${esc(a.status.replace('_',' '))}</span><button class="small" data-alert="${esc(a.id)}">Review</button></div>`).join('')}</div>`:''}
  ${classes.map(c=>`<div class="class-card"><div><strong>${esc(c.name)}</strong><div class="muted">${c.students} student${c.students===1?'':'s'} · accepts ${c.domains.map(d=>'@'+esc(d)).join(', ')}</div></div><div class="toolbar"><button class="small" data-invite="${esc(c.id)}">🔗 Invite link</button><button class="small" data-roster="${esc(c.id)}">👥 Students &amp; nicknames</button><button class="small danger" data-delete="${esc(c.id)}">🗑 Delete</button></div></div>`).join('')||'<p>No classes yet. Create your first below.</p>'}
  <h3>New class</h3><label for="cn">Class name</label><input id="cn" maxlength="80" placeholder="Period 3 Physical Science"><label for="cd">Student email domains <span class="muted">(comma separated)</span></label><input id="cd" value="${esc((cfg.defaultStudentDomains||[]).join(', '))}" placeholder="yourschool.org"><button id="cc" class="primary wide">Create class</button>`,{wide:true});
  el.querySelectorAll('[data-alert]').forEach(b=>b.onclick=()=>openAlert(b.dataset.alert));
  el.querySelectorAll('[data-delete]').forEach(b=>b.onclick=async()=>{const c=classes.find(x=>x.id===b.dataset.delete);if(!confirm(`Delete "${c.name}"? This permanently removes its students, invite links and all saved chats and alerts. It cannot be undone.`))return;try{await call('/api/class/delete',{classId:c.id});await refresh();teacherHome();populateClassPick();toast('Class deleted.')}catch(e){toast(e.message)}});
  el.querySelectorAll('[data-roster]').forEach(b=>b.onclick=()=>roster(b.dataset.roster));
  el.querySelectorAll('[data-invite]').forEach(b=>b.onclick=async()=>{try{const i=await call('/api/class/invite',{classId:b.dataset.invite});const url=i.url.startsWith('http')?i.url:location.origin+i.url;try{await navigator.clipboard.writeText(url);toast('Invite link copied. Valid for 14 days.')}catch{prompt('Copy this invite link',url)}}catch(e){toast(e.message)}});
  el.querySelector('#cc').onclick=async()=>{try{await call('/api/class/create',{name:el.querySelector('#cn').value,domains:el.querySelector('#cd').value});await refresh();teacherHome();populateClassPick()}catch(e){toast(e.message)}};
 }
 async function roster(classId){
  const cls=classes.find(c=>c.id===classId);let members;try{members=(await call('/api/class/members',{classId})).members}catch(e){return toast(e.message)}
  const el=overlay('classes-view',`<button class="back" id="back">← Classes</button><div class="eyebrow">${esc(cls?.name||'')}</div><h2>Students &amp; nicknames</h2><p>Nicknames are what students are called in games when you choose “class nicknames.” Edit them, then save. Future sign-ins use your saved names.</p>
  <div class="toolbar"><button id="suggest" class="small">✨ Suggest nicknames (AI)</button><button id="savenick" class="primary small">Save nicknames</button><span id="nick-note" class="muted"></span></div>
  <div class="roster-table">${members.map(m=>`<div class="rrow ${m.removed?'removed':''}" data-email="${esc(m.email)}"><div><strong>${esc(m.name)}</strong><div class="muted">${esc(m.email)}</div></div><input class="nick" aria-label="Nickname for ${esc(m.name)}" value="${esc(m.nickname||'')}" maxlength="24" ${m.removed?'disabled':''}><span class="muted">${m.nickConfirmed?'✓ saved':'guess'}</span><span class="muted">${m.messages} msgs${m.flagged?` · <b class="flag">${m.flagged} flagged</b>`:''}<br>last: ${fmt(m.lastActive)}</span><span class="toolbar"><button class="small" data-t="${esc(m.email)}">💬 Chats</button><button class="small ${m.removed?'':'danger'}" data-r="${esc(m.email)}" data-removed="${m.removed?1:0}">${m.removed?'Restore':'Remove'}</button></span></div>`).join('')||'<p>No students yet. Share the invite link from the class list.</p>'}</div>`,{wide:true});
  el.querySelector('#back').onclick=teacherHome;
  const note=el.querySelector('#nick-note');
  el.querySelector('#suggest').onclick=async()=>{note.textContent='Thinking…';try{const r=await call('/api/class/nicknames/suggest',{classId});r.suggestions.forEach(s=>{const inp=el.querySelector(`.rrow[data-email="${CSS.escape(s.email)}"] .nick`);if(inp&&!inp.disabled)inp.value=s.suggested});note.textContent=(r.source==='ai'?'AI suggestions filled in.':'AI unavailable; used simple name guesses.')+' Review, edit, then save.'}catch(e){note.textContent='';toast(e.message)}};
  el.querySelector('#savenick').onclick=async()=>{const map={};el.querySelectorAll('.rrow:not(.removed)').forEach(r=>map[r.dataset.email]=r.querySelector('.nick').value);try{await call('/api/class/nicknames/save',{classId,nicknames:map});toast('Nicknames saved for this class.');roster(classId)}catch(e){toast(e.message)}};
  el.querySelectorAll('[data-t]').forEach(b=>b.onclick=()=>transcript(classId,b.dataset.t,members.find(m=>m.email===b.dataset.t)?.name));
  el.querySelectorAll('[data-r]').forEach(b=>b.onclick=async()=>{const removed=b.dataset.removed==='1';if(!removed&&!confirm('Remove this student from the class? They lose access to class games until restored.'))return;try{await call(removed?'/api/class/restore':'/api/class/remove',{classId,email:b.dataset.r});roster(classId)}catch(e){toast(e.message)}});
 }
 async function transcript(classId,email,name){
  let convos;try{convos=(await call('/api/class/transcript',{classId,email})).conversations}catch(e){return toast(e.message)}
  const el=overlay('classes-view',`<button class="back" id="back">← Students</button><div class="eyebrow">CHAT HISTORY</div><h2>${esc(name||email)}</h2>${convos.map(c=>`<details open><summary>${esc(c.topic??'Conversation')} · room ${esc(c.room)}</summary>${c.messages.map(m=>`<div class="bubble ${m.role==='student'?'user':''}"><small>${m.role==='student'?'STUDENT':'TUTOR'} · ${fmt(m.ts)}${m.flag?` · <b class="flag">${esc(m.flag)}</b>`:''}</small>${esc(m.text)}</div>`).join('')}</details>`).join('')||'<p>No chats yet.</p>'}`,{wide:true});
  el.querySelector('#back').onclick=()=>roster(classId);
 }
 async function openAlert(id){
  let r;try{r=await call('/api/class/alert',{alertId:id})}catch(e){return toast(e.message)}
  const a=r.alert,failed=a.status==='failed'||a.status==='not_configured';
  const el=overlay('alert-view',`<div class="eyebrow">SAFETY ALERT</div><h2>${esc(r.label||a.category)}</h2><p><strong>${esc(a.student_name)}</strong> (${esc(a.student_email)}) · ${fmt(a.created)}<br>Email to you: <b>${esc(a.status.replace('_',' '))}</b>${a.detail?' — '+esc(a.detail):''}</p>${failed?'<button id="retry" class="small">Retry email</button>':''}<h3>Conversation</h3>${r.messages.map(m=>`<div class="bubble ${m.role==='student'?'user':''}"><small>${m.role==='student'?'STUDENT':'TUTOR'} · ${fmt(m.ts)}${m.flag?` · <b class="flag">${esc(m.flag)}</b>`:''}</small>${esc(m.text)}</div>`).join('')}<button id="reviewed" class="primary wide">${a.reviewed?'Reviewed ✓':'Mark as reviewed'}</button>`,{wide:true});
  el.querySelector('#reviewed').onclick=async()=>{try{await call('/api/class/alert/review',{alertId:id});close('alert-view');toast('Marked as reviewed.')}catch(e){toast(e.message)}};
  const rt=el.querySelector('#retry');if(rt)rt.onclick=async()=>{try{await call('/api/class/alert/retry',{alertId:id});toast('Retrying…');openAlert(id)}catch(e){toast(e.message)}};
 }

 // ---------- private question library (teacher setup screen)
 let libSets=[];
 async function libLoad(){try{libSets=(await call('/api/library/list')).sets}catch{libSets=[]}libRender()}
 function libRender(){
  const box=document.getElementById('lib-sets');if(!box)return;
  box.innerHTML=libSets.map(s=>`<div class="lib-set"><label class="check"><input type="checkbox" class="lib-pick" value="${esc(s.id)}"> <strong>${esc(s.title)}</strong> <span class="muted">${s.count} questions</span></label><button class="small danger" data-libdel="${esc(s.id)}" aria-label="Delete ${esc(s.title)}">🗑</button></div>`).join('')||'<p class="hint-text">No saved question sets yet. Import a test below. Only you can see your library.</p>';
  box.querySelectorAll('.lib-pick').forEach(i=>i.onchange=libSubjects);
  box.querySelectorAll('[data-libdel]').forEach(b=>b.onclick=async()=>{if(!confirm('Delete this question set from your library?'))return;try{await call('/api/library/delete',{id:b.dataset.libdel});await libLoad()}catch(e){toast(e.message)}});
  libSubjects();
 }
 function libSubjects(){
  const picked=[...document.querySelectorAll('.lib-pick:checked')].map(i=>i.value),tags={};
  libSets.filter(s=>picked.includes(s.id)).forEach(s=>Object.entries(s.subjects).forEach(([k,n])=>tags[k]=(tags[k]||0)+n));
  document.getElementById('lib-subjects').innerHTML=Object.entries(tags).map(([k,n])=>`<label class="check"><input type="checkbox" class="lib-subject" value="${esc(k)}"> ${esc(k)} <span class="muted">(${n})</span></label>`).join('');
  document.getElementById('lib-build').disabled=!picked.length;
 }

 // ---------- saved games: build once, reuse for any class or for solo practice
 let savedId=null,savedList=[];
 async function packsLoad(){try{savedList=(await call('/api/pack/list')).packs}catch{savedList=[]}packsRender()}
 function packsRender(){const box=document.getElementById('saved-list');if(!box)return;
  box.innerHTML=savedList.length?savedList.map(p=>`<div class="saved-row" data-id="${esc(p.id)}"><div><b>${esc(p.title)}</b> <span class="muted">${p.questions} questions · ${p.topics} topics</span><div class="hint-text">${p.allClasses?'Available to all your classes':p.classes.length?'Assigned to: '+p.classes.map(c=>esc(c.name)).join(', '):'Hidden from students'}</div></div><div class="toolbar"><button type="button" class="small" data-act="load">Use this game</button><button type="button" class="small" data-act="assign">Classes…</button><button type="button" class="small danger" data-act="del">Delete</button></div><div class="assign hidden">${classes.map(c=>`<label class="check"><input type="checkbox" value="${esc(c.id)}" ${p.allClasses||p.classes.some(x=>x.id===c.id)?'checked':''}> ${esc(c.name)}</label>`).join('')||'<span class="muted">Create a class first.</span>'}<button type="button" class="small primary" data-act="saveassign">Save</button></div></div>`).join(''):'<p class="hint-text">Nothing saved yet. Games you create are saved here automatically.</p>';
  box.querySelectorAll('.saved-row').forEach(row=>{const id=row.dataset.id,p=savedList.find(x=>x.id===id);
   row.querySelector('[data-act=load]').onclick=async()=>{try{const r=await call('/api/pack/get',{id});pack=r.pack;savedId=id;preview();toast('Loaded “'+p.title+'”. Pick your settings and create the game.');document.getElementById('packtitle').scrollIntoView({behavior:'smooth'})}catch(e){toast(e.message)}};
   row.querySelector('[data-act=assign]').onclick=()=>row.querySelector('.assign').classList.toggle('hidden');
   row.querySelector('[data-act=saveassign]').onclick=async()=>{try{const boxes=[...row.querySelectorAll('.assign input')],on=boxes.filter(i=>i.checked);await call('/api/pack/assign',{id,classIds:on.map(i=>i.value),all:boxes.length>0&&on.length===boxes.length});toast('Saved. Students in those classes can now play it on their own.');packsLoad()}catch(e){toast(e.message)}};
   row.querySelector('[data-act=del]').onclick=async()=>{if(!confirm('Delete “'+p.title+'”? Students lose access to it.'))return;try{await call('/api/pack/delete',{id});if(savedId===id)savedId=null;packsLoad()}catch(e){toast(e.message)}}})}
 function packsMount(){
  if(document.getElementById('savedbox'))return;
  document.getElementById('packtitle').insertAdjacentHTML('beforebegin','<details id="savedbox" class="lib-box" open><summary>🗂️ My saved games <span class="muted">(build once, reuse anywhere)</span></summary><div id="saved-list"></div></details>');
  packsLoad()}
 // Save (or update) the current pack. Returns its id so a room or solo game can be created from it.
 async function savePack(){if(!pack)return null;try{const r=await call('/api/pack/save',{pack,id:savedId||undefined});savedId=r.id;packsLoad();return r.id}catch(e){if(savedId){savedId=null;return savePack()}return null}}
 function resetSaved(){savedId=null}
 function libMount(){
  if(document.getElementById('libbox'))return;
  const anchor=document.getElementById('packtitle');
  anchor.insertAdjacentHTML('beforebegin',`<details id="libbox" class="lib-box"><summary>📚 My question library <span class="muted">(private to you)</span></summary>
   <div id="lib-sets"></div><div class="muted">Topics to include <span class="hint-text">(leave all unchecked to use every topic)</span></div><div id="lib-subjects"></div>
   <button id="lib-build" class="small" disabled>Build mission from selection</button>
   <h3>Add to library</h3><p class="hint-text">Import a test or study guide (TXT, PDF, DOCX) or paste it. Multiple-choice questions become "explain your reasoning" questions, each tagged by topic.</p>
   <div class="toolbar"><label class="file-label small">Choose file<input id="lib-file" type="file" accept=".txt,.md,.pdf,.docx" hidden></label><span id="lib-note" class="muted"></span></div>
   <textarea id="lib-text" rows="5" placeholder="Or paste the questions here"></textarea><button id="lib-import" class="primary small">Add to my library</button></details>`);
  document.getElementById('lib-build').onclick=async()=>{resetSaved();
   const ids=[...document.querySelectorAll('.lib-pick:checked')].map(i=>i.value),subjects=[...document.querySelectorAll('.lib-subject:checked')].map(i=>i.value);
   try{const r=await call('/api/library/pack',{ids,subjects,title:subjects.length?subjects.join(' & ')+' mission':undefined});pack=r.pack;preview();toast('Mission built from your library. Review it below, then create the room.')}catch(e){toast(e.message)}};
  document.getElementById('lib-file').onchange=async e=>{
   const f=e.target.files[0];if(!f)return;const note=document.getElementById('lib-note');
   try{if(f.size>4000000)throw Error('Choose a file smaller than 4 MB.');
    if(/\.(txt|md)$/i.test(f.name))document.getElementById('lib-text').value=await f.text();
    else{note.textContent='Reading file…';const bytes=new Uint8Array(await f.arrayBuffer());let bin='';for(let i=0;i<bytes.length;i+=8192)bin+=String.fromCharCode(...bytes.slice(i,i+8192));const r=await call('/api/extract',{name:f.name,data:btoa(bin)});document.getElementById('lib-text').value=r.text}
    note.textContent='File read. Click "Add to my library".'}catch(err){note.textContent='';toast(err.message)}e.target.value=''};
  document.getElementById('lib-import').onclick=async()=>{
   const b=document.getElementById('lib-import'),note=document.getElementById('lib-note');b.disabled=true;note.textContent='Reading questions with AI… this can take a minute.';
   try{const s=await call('/api/library/import',{text:document.getElementById('lib-text').value});document.getElementById('lib-text').value='';note.textContent=`Added "${s.title}" with ${s.count} questions.`;await libLoad()}
   catch(e){note.textContent='';toast(e.message)}finally{b.disabled=false}};
  libLoad();
 }

 // ---------- teacher material helpers: voice dictation + AI planning chat
 const SR=window.SpeechRecognition||window.webkitSpeechRecognition;
 function dictation(button,target){
  if(!SR){button.classList.add('hidden');return}
  let rec=null,base='';
  button.onclick=()=>{
   if(rec){rec.stop();return}
   rec=new SR();rec.continuous=true;rec.interimResults=true;rec.lang=navigator.language||'en-US';base=target.value&&!/\s$/.test(target.value)?target.value+' ':target.value;
   rec.onresult=e=>{let t='';for(let i=0;i<e.results.length;i++)t+=e.results[i][0].transcript;target.value=base+t;target.dispatchEvent(new Event('input'))};
   rec.onend=()=>{rec=null;button.textContent='🎤 Dictate';button.classList.remove('rec')};rec.onerror=ev=>{toast(ev.error==='not-allowed'?'Allow microphone access in your browser to dictate.':'Dictation stopped.')};
   try{rec.start();button.textContent='⏹ Stop dictating';button.classList.add('rec')}catch{rec=null}
  };
 }
 function materialMount(){
  if(document.getElementById('assist-box'))return;
  const topics=document.getElementById('topics');
  topics.insertAdjacentHTML('beforebegin','<div class="toolbar"><button type="button" id="dict-topics" class="small">🎤 Dictate</button><span class="muted">Speak your content, or type it. Chrome sends dictation audio to Google for transcription.</span></div>');
  dictation(document.getElementById('dict-topics'),topics);
  document.getElementById('generate').insertAdjacentHTML('afterend',`<details id="assist-box" class="lib-box" open><summary>💬 Plan it with the AI helper</summary>
   <p class="hint-text">Describe what you are teaching. The helper asks questions, suggests topics, simulations and images. When it sounds right, click "Make questions from this conversation".</p>
   <div id="assist-log" class="chatlog" aria-live="polite" style="max-height:260px"></div>
   <textarea id="assist-input" rows="2" placeholder="For example: I teach magnetism to 9th graders. We covered domains and electromagnets."></textarea>
   <div class="toolbar"><button type="button" id="dict-assist" class="small">🎤 Dictate</button><button type="button" id="assist-send" class="primary small">Send</button><button type="button" id="assist-make" class="small">✦ Make questions from this conversation</button></div></details>`);
  const log=document.getElementById('assist-log'),input=document.getElementById('assist-input'),msgs=[];
  const draw=()=>{log.innerHTML=msgs.map(m=>`<div class="bubble ${m.role==='user'?'user':''}"><small>${m.role==='user'?'YOU':'AI HELPER'}</small>${esc(m.text)}</div>`).join('');log.scrollTop=log.scrollHeight};
  dictation(document.getElementById('dict-assist'),input);
  const send=async()=>{const text=input.value.trim();if(!text)return;msgs.push({role:'user',text});input.value='';draw();const b=document.getElementById('assist-send');b.disabled=true;
   try{const r=await call('/api/assist',{messages:msgs,material:document.getElementById('topics').value});msgs.push({role:'assistant',text:r.reply})}catch(e){toast(e.message);msgs.pop();input.value=text}finally{b.disabled=false;draw()}};
  document.getElementById('assist-send').onclick=send;input.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send()}});
  document.getElementById('assist-make').onclick=()=>{if(!msgs.length)return toast('Chat with the helper first.');const t=document.getElementById('topics');t.value=(t.value?t.value+'\n\n':'')+'Teacher planning conversation:\n'+msgs.map(m=>(m.role==='user'?'Teacher: ':'Helper: ')+m.text).join('\n');document.getElementById('generate').click()};
 }

 // ---------- class picker inside game setup
 function populateClassPick(){
  const sel=document.getElementById('classpick');if(!sel)return;
  sel.innerHTML=classes.map(c=>`<option value="${esc(c.id)}">${esc(c.name)}</option>`).join('')||'<option value="">Create a class first</option>';
 }
 function prepareSetup(){
  if(!document.getElementById('classpick')){
   const gt=document.getElementById('gametype');
   gt.insertAdjacentHTML('beforebegin','<label for="classpick">Class</label><select id="classpick"></select>');
   const an=document.getElementById('autonames');
   an.checked=false;an.parentElement.lastChild.textContent=' 🐼 Hide real names: give students anonymous fun names for this game';
   an.parentElement.insertAdjacentHTML('afterend','<p class="hint-text">Unchecked: students appear with the nicknames you saved for the class, so you can match online play to who is in the room. Checked: they get random names, and only you can see who is who.</p>');
  }
  populateClassPick();
  if(user?.role==='teacher')libMount();
 }
 function classId(){const s=document.getElementById('classpick');return s?s.value:''}
 function firstClass(){return classes[0]?.id||''}

 async function init(){
  cfg=config;
  const code=new URLSearchParams(location.search).get('join');if(code)put(JOIN,code);
  document.body.classList.add('classes-mode');prepareSetup();
  if(!token())return signInScreen();
  try{const r=await call('/api/auth/me');user=r.user;classes=r.classes;afterSignIn()}catch{needSignIn('Your session ended. Please sign in again.')}
 }
 return {init,token,dictation,savePack,resetSaved,packsLoad,needSignIn,classId,firstClass,prepareSetup,get user(){return user},get classes(){return classes}};
})();

window.Classes=Classes;
