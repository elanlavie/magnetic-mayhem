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
  ${classes.map(c=>`<div class="class-card"><div><strong>${esc(c.name)}</strong><div class="muted">${c.students} student${c.students===1?'':'s'} · accepts ${c.domains.map(d=>'@'+esc(d)).join(', ')}</div></div><div class="toolbar"><button class="small" data-invite="${esc(c.id)}">🔗 Invite link</button><button class="small" data-roster="${esc(c.id)}">👥 Students &amp; nicknames</button></div></div>`).join('')||'<p>No classes yet. Create your first below.</p>'}
  <h3>New class</h3><label for="cn">Class name</label><input id="cn" maxlength="80" placeholder="Period 3 Physical Science"><label for="cd">Student email domains <span class="muted">(comma separated)</span></label><input id="cd" value="${esc((cfg.defaultStudentDomains||[]).join(', '))}" placeholder="yourschool.org"><button id="cc" class="primary wide">Create class</button>`,{wide:true});
  el.querySelectorAll('[data-alert]').forEach(b=>b.onclick=()=>openAlert(b.dataset.alert));
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
 return {init,token,needSignIn,classId,firstClass,prepareSetup,get user(){return user},get classes(){return classes}};
})();

window.Classes=Classes;
