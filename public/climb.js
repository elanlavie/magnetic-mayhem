// Tower climb: a jumping platformer. Each ledge has a question gate; answering it builds the next stretch of tower.
// Uses the same tutor chat, timers, saved games and review as the station game (see server.py climb_pick).
const CLIMB={W:900,FH:330,G:2100,JUMP:800,SPEED:300,HALF:22,vx:0,vy:0,ground:false,coyote:0,buf:0,room:'',h:-1,zone:0,cool:0,wasActive:false,built:0,moveAt:0,celebrated:false};
const climbOn=()=>state?.room?.gameType==='climb';
const climbFloors=()=>Math.max(1,state.room.floors||state.room.pack.topics.reduce((n,t)=>n+t.questions.length,0));
const climbHeight=()=>Math.min(climbFloors(),state.player.completed.length);
const ledgeY=k=>-k*CLIMB.FH;
const ledgeCX=k=>k===0?450:(k%2?230:670);
const ledgeW=k=>k===0?800:300;
function climbPlatforms(h){
  const out=[];
  for(let k=0;k<=h;k++){
    out.push({x:ledgeCX(k)-ledgeW(k)/2,y:ledgeY(k),w:ledgeW(k),ledge:k});
    if(k<h){const a=ledgeCX(k),b=ledgeCX(k+1);for(let j=1;j<=2;j++)out.push({x:a+(b-a)*j/3-55,y:ledgeY(k)-110*j,w:110,step:k})}
  }
  return out;
}
function climbReset(){const h=climbHeight();pos.x=ledgeCX(h);pos.y=ledgeY(h)-CLIMB.HALF;CLIMB.vx=CLIMB.vy=0;CLIMB.ground=true}
function climbHud(){
  if(!state)return;const climb=climbOn(),r=state.room,p=state.player;
  $('#relay-start')?.classList.toggle('hidden',climb);$('#cell-count')?.classList.toggle('hidden',climb);$('#boost-hud')?.classList.toggle('hidden',climb);
  const pill=document.querySelector('.live-pill');if(pill)pill.textContent=climb?'● TOWER':'● SECTOR 09';
  const mb=document.querySelector('.map-bottom');if(mb)mb.innerHTML=climb?'<span>← → &nbsp; MOVE</span><span>↑ / SPACE &nbsp; JUMP</span><span>ENTER &nbsp; ANSWER AT THE GATE</span>':'<span>WASD / ↑↓←→ &nbsp; MOVE</span><span>ENTER &nbsp; INTERACT</span><span>SPACE &nbsp; DASH · RECHARGES</span><span>⚡ COLLECT CELLS</span>';
  $('#world')?.setAttribute('aria-label',climb?'Tower. Move with left and right arrows, jump with up arrow or space, press Enter at the gate to answer a question.':'Space station. Move using WASD or arrow keys; press Enter near a station to interact.');
  $('#viewport')?.classList.toggle('climb',climb);
  const swap=(id,station,tower)=>{const e=document.getElementById(id);if(e)e.innerHTML=climb?tower:station};
  swap('side-eyebrow','STATION STATUS','TOWER PROGRESS');swap('side-title','Bring it back<br>to life.','Climb to<br>the top.');
  swap('side-face','🧑‍🔧','🧗');swap('side-card-title','🛠️ Ship engineer','🧗 Tower guide');
  swap('side-card-text','Run supplies 📦, collect energy ⚡, and repair the station 🔧. Chat whenever you want; leave whenever you want.','Jump up the ledges. Stand in the glowing gate to get a question, and explain your thinking to build the next stretch.');
  $('#boost-meter')?.classList.toggle('hidden',climb);$('#objectivesbtn')?.classList.toggle('hidden',climb);
  if(!climb)return;
  const h=climbHeight(),floors=climbFloors();
  $('#repair-count').textContent=`🧗 ${h} / ${floors} floors`;
  $('#mission-label').textContent=r.mode==='solo'?'SOLO CLIMB':`${r.mode==='race'?p.team.toUpperCase()+' TEAM RACE':'TOWER CLIMB'} · ${r.code}`;
  $('#overall-fill').style.width=`${100*h/floors}%`;$('#progress-copy').textContent=`${h} / ${floors} floors climbed`;
  $('#station-list').innerHTML=r.pack.topics.map((t,i)=>{const done=p.completed.filter(x=>x.startsWith(i+':')).length,n=t.questions.length;return `<div class="station-entry ${done>=n?'complete':''}" style="--rc:${roomColor(i)}"><span class="indicator">${done>=n?'✓':i+1}</span><span>${esc(t.name)}</span><small>${done}/${n}</small></div>`}).join('');
  $('#next-objective').textContent=h>=floors?'🏆 You reached the summit!':`🎯 Climb to the glowing gate on floor ${h+1} and answer to build the next stretch.`;
  const rank=[...r.players].sort((a,b)=>b.completed.length-a.completed.length).slice(0,8);
  const teamLines=r.mode==='race'?['violet','mint'].map(team=>{const best=Math.max(0,...r.players.filter(x=>x.team===team).map(x=>x.completed.length));return `${team==='violet'?'🟣':'🟢'} ${team}: top climber ${best}/${floors}`}).join('<br>'):rank.map(x=>`${esc(x.name)} · floor ${Math.min(floors,x.completed.length)}`).join('<br>');
  $('#crew-panel').innerHTML=(r.winner?`<strong>${esc(r.winner).toUpperCase()} TEAM REACHED THE SUMMIT!</strong><br>`:'')+teamLines;
}
function climbRules(){
  modal(`<div class="rules"><div class="eyebrow">TOWER CLIMB</div><h2>Jump up the tower.</h2><ul><li>Move with <b>← →</b> and jump with <b>↑</b> or <b>Space</b>. On a touch screen use the on-screen buttons.</li><li>Every ledge has a glowing gate. Stand in it and press <b>Enter</b> to get your question.</li><li>Explain your thinking to the tutor. When you finish, the next stretch of tower builds itself.</li><li>Falling is safe: you only drop to a lower ledge. Take your time.</li><li>${state.room.mode==='race'?'The first team to the summit wins.':'Climb as high as you can with your class.'}</li></ul><button class="primary" onclick="closeModal()">Start climbing</button></div>`);
}
async function climbEnter(){
  if(!state||state.player.active||CLIMB.zone<=0)return toast('🧗 Climb to the glowing gate first.');
  if(climbHeight()>=climbFloors())return toast('🏆 You already reached the summit!');
  keys.clear();
  try{const epoch=++encounterEpoch;reqId=null;const data=await api('/api/start',auth({topic:climbHeight()%state.room.pack.topics.length}));if(epoch===encounterEpoch){state=data;syncEncounter(true);$('#answer').focus()}}catch(e){toast(e.message)}
}
function drawClimb(ts,dt,paused){
  const r=state.room,p=state.player,h=climbHeight(),floors=climbFloors();
  if(CLIMB.room!==r.code){CLIMB.room=r.code;CLIMB.h=h;climbReset();CLIMB.celebrated=false;climbHud()}
  if(h>CLIMB.h){toast(h>=floors?'🏆 Summit! You made it to the top!':`⬆️ Floor ${h} unlocked! The next stretch is built.`);CLIMB.h=h;CLIMB.built=ts;climbHud()}
  if(p.active)CLIMB.wasActive=true;else if(CLIMB.wasActive){CLIMB.wasActive=false;CLIMB.cool=ts+1600}
  const plats=climbPlatforms(h);
  if(!paused){
    const left=keys.has('a')||keys.has('arrowleft'),right=keys.has('d')||keys.has('arrowright'),jump=keys.has('w')||keys.has('arrowup')||keys.has(' ');
    const want=((right?1:0)-(left?1:0))*CLIMB.SPEED;CLIMB.vx+=(want-CLIMB.vx)*Math.min(1,dt*(CLIMB.ground?18:9));
    if(jump&&!CLIMB.jumpHeld){CLIMB.buf=.12}CLIMB.jumpHeld=jump;CLIMB.buf=Math.max(0,CLIMB.buf-dt);CLIMB.coyote=CLIMB.ground?.1:Math.max(0,CLIMB.coyote-dt);
    if(CLIMB.buf>0&&CLIMB.coyote>0){CLIMB.vy=-CLIMB.JUMP;CLIMB.buf=0;CLIMB.coyote=0;CLIMB.ground=false}
    const prevFeet=pos.y+CLIMB.HALF;CLIMB.vy=Math.min(1300,CLIMB.vy+CLIMB.G*dt);pos.x=Math.max(16,Math.min(CLIMB.W-16,pos.x+CLIMB.vx*dt));pos.y+=CLIMB.vy*dt;
    const feet=pos.y+CLIMB.HALF;CLIMB.ground=false;
    if(CLIMB.vy>=0)for(const q of plats){if(pos.x>q.x-12&&pos.x<q.x+q.w+12&&prevFeet<=q.y+5&&feet>=q.y){pos.y=q.y-CLIMB.HALF;CLIMB.vy=0;CLIMB.ground=true;break}}
    if(pos.y>ledgeY(h)+2*CLIMB.FH+260){toast('🪂 Soft landing. Back to your gate!');climbReset()}
  }
  // gate zone
  const gx=ledgeCX(h),atGate=h<floors&&Math.abs(pos.x-gx)<46&&CLIMB.ground&&Math.abs(pos.y+CLIMB.HALF-ledgeY(h))<4;
  CLIMB.zone=atGate?1:0;
  if(!paused&&atGate&&ts>CLIMB.cool&&!CLIMB.stand)CLIMB.stand=ts;if(!atGate)CLIMB.stand=0;
  if(!paused&&atGate&&CLIMB.stand&&ts-CLIMB.stand>650&&ts>CLIMB.cool){CLIMB.stand=0;climbEnter()}
  if(h>=floors&&!CLIMB.celebrated&&Math.abs(pos.y+CLIMB.HALF-ledgeY(h))<4){CLIMB.celebrated=true;if(typeof celebrate==='function')celebrate(1)}
  // camera
  const rect=canvas.getBoundingClientRect(),dpr=Math.min(devicePixelRatio||1,2);
  if(canvas.width!==Math.round(rect.width*dpr)||canvas.height!==Math.round(rect.height*dpr)){canvas.width=Math.round(rect.width*dpr);canvas.height=Math.round(rect.height*dpr)}
  ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,rect.width,rect.height);
  const scale=Math.max(.55,Math.min(rect.width/CLIMB.W,rect.height/540,1.15)),viewH=rect.height/scale,viewW=rect.width/scale;
  const camX=(CLIMB.W-viewW)/2,camY=pos.y-viewH*.6;
  // sky: grows darker with height
  const alt=Math.min(1,-camY/(CLIMB.FH*Math.max(6,floors))),top=`hsl(${215+25*alt},${55+10*alt}%,${34-22*alt}%)`,bot=`hsl(${200+30*alt},${60}%,${62-38*alt}%)`;
  const g=ctx.createLinearGradient(0,0,0,rect.height);g.addColorStop(0,top);g.addColorStop(1,bot);ctx.fillStyle=g;ctx.fillRect(0,0,rect.width,rect.height);
  ctx.save();ctx.scale(scale,scale);ctx.translate(-camX,-camY);
  // far details (parallax clouds and stars)
  for(let i=0;i<26;i++){const sx=(i*263)%CLIMB.W,sy=-((i*517)%(CLIMB.FH*Math.max(8,floors+2)))+300,py=sy+camY*.5*0,ax=sx+Math.sin(ts/4000+i)*18;ctx.globalAlpha=.2+.25*alt;ctx.fillStyle=alt>.35?'#fff':'#ffffffcc';ctx.beginPath();ctx.ellipse(ax,py,alt>.35?2.5:46,alt>.35?2.5:14,0,0,7);ctx.fill()}ctx.globalAlpha=1;
  // tower spine
  ctx.fillStyle='#00000018';ctx.fillRect(CLIMB.W/2-130,ledgeY(h)-CLIMB.FH,260,CLIMB.FH*(h+3));
  // platforms
  const grow=Math.min(1,(ts-CLIMB.built)/600);
  for(const q of plats){
    const isLedge=q.ledge!==undefined,col=roomColor(isLedge?q.ledge:q.step),fresh=!isLedge&&q.step===h-1,sc=fresh?grow:1;
    ctx.save();if(fresh){ctx.translate(q.x+q.w/2,q.y);ctx.scale(sc,sc);ctx.translate(-(q.x+q.w/2),-q.y)}
    rounded(q.x,q.y,q.w,isLedge?26:15,6,isLedge?'#5b3f6e':'#6c8aa8','#ffffff66');ctx.fillStyle=col;ctx.fillRect(q.x+4,q.y,q.w-8,5);
    if(isLedge){ctx.fillStyle='#ffffffcc';ctx.font='bold 12px monospace';ctx.textAlign='center';ctx.fillText(q.ledge===0?'START':'FLOOR '+q.ledge,q.x+q.w/2,q.y+19)}
    ctx.restore();
  }
  // gate or summit flag
  const gy=ledgeY(h);
  if(h<floors){
    const pulse=.55+.25*Math.sin(ts/260),col=roomColor(h%state.room.pack.topics.length);
    ctx.save();ctx.shadowColor=col;ctx.shadowBlur=24;rounded(gx-34,gy-92,68,92,14,col+(atGate?'ee':'88'),'#fff');ctx.restore();
    ctx.fillStyle='#2b1a15';ctx.font='bold 38px sans-serif';ctx.textAlign='center';ctx.fillText('?',gx,gy-34);
    ctx.fillStyle='#fff';ctx.font='bold 12px monospace';ctx.fillText(`QUESTION ${h+1}`,gx,gy-102);
    if(!atGate){ctx.globalAlpha=pulse;ctx.font='bold 11px monospace';ctx.fillText('stand here',gx,gy-118);ctx.globalAlpha=1}
  }else{ctx.font='70px sans-serif';ctx.textAlign='center';ctx.fillText('🏆',gx,gy-30);ctx.fillStyle='#fff';ctx.font='bold 14px monospace';ctx.fillText('SUMMIT',gx,gy-104)}
  // others
  r.players.filter(o=>o.id!==p.id&&o.alive!==false&&o.y!==null&&Date.now()/1000-o.last<45).forEach(o=>{ctx.save();ctx.globalAlpha=.8;astronaut(o.x,o.y,lookClean(o.look,o.id),o.name);if(o.chatting){ctx.font='18px sans-serif';ctx.fillText('💬',o.x,o.y-58)}ctx.restore()});
  astronaut(pos.x,pos.y+2,lookClean(p.look,p.id),p.name,true);
  ctx.restore();
  // tower progress bar on the right
  const bx=rect.width-20,by=70,bh=Math.max(120,rect.height-150);ctx.setTransform(dpr,0,0,dpr,0,0);
  rounded(bx-5,by,10,bh,5,'#00000055','#ffffff55');
  const dot=(n,color,rad)=>{ctx.fillStyle=color;ctx.beginPath();ctx.arc(bx,by+bh-(Math.min(n,floors)/floors)*bh,rad,0,7);ctx.fill()};
  r.players.filter(o=>o.id!==p.id&&Date.now()/1000-o.last<45).forEach(o=>dot(o.completed.length,o.team==='violet'?'#b58cff':o.team==='mint'?'#69f0ae':'#ffffffaa',4));dot(h,'#ffd23f',6);
  ctx.fillStyle='#fff';ctx.font='12px sans-serif';ctx.textAlign='center';ctx.fillText('🏆',bx,by-6);
  // prompt
  if(atGate&&!paused){$('#interact-prompt').classList.remove('hidden');$('#near-label').textContent=`Floor ${h+1} gate`;$('#interact').textContent='Enter · Answer to climb'}else $('#interact-prompt').classList.add('hidden');
  if(!paused&&ts-CLIMB.moveAt>160){CLIMB.moveAt=ts;api('/api/move',auth({x:pos.x,y:pos.y})).catch(()=>{})}
}
