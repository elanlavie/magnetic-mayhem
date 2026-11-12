// Tower climb: an energy platformer. Moving and jumping burn energy; a good explanation to the tutor refills it.
// Uses the same tutor chat, timers, saved games and review as the station game (see server.py climb_pick).
const CLIMB={W:900,G:2100,JUMP:800,JUMP2:700,SPEED:300,HALF:22,JCOST:8,WCOST:4,vx:0,vy:0,ground:false,coyote:0,buf:0,dj:1,jumpPrev:false,room:'',h:-1,energy:0,cp:0,zoneSeen:0,best:0,tower:null,wasActive:false,moveAt:0,hudAt:0,hurt:0,celebrated:false,flash:0,rings:[]};
const ZONES=[
  {name:'Meadow Base',top:[205,60,62],bot:[190,55,78],plat:'#58b368',edge:'#a8e6a3'},
  {name:'Cloud Deck',top:[215,55,48],bot:[205,60,70],plat:'#6b9ad8',edge:'#c4dcff'},
  {name:'Storm Ridge',top:[250,40,28],bot:[235,45,44],plat:'#8a6fc0',edge:'#d6c4ff'},
  {name:'Star Summit',top:[265,45,10],bot:[255,45,24],plat:'#d8a93e',edge:'#ffe9a8'}
];
const climbOn=()=>state?.room?.gameType==='climb';
const climbFloors=()=>Math.max(1,state.room.floors||state.room.pack.topics.reduce((n,t)=>n+t.questions.length,0));
const climbHeight=()=>Math.min(climbFloors(),state.player.completed.length);
const climbSummit=()=>state.room.summit||climbFloors()*300;
const climbEnergyPer=()=>state.room.energy||70;
const metersOf=y=>Math.max(0,Math.round(-y/10));
function rng(seed){let a=seed>>>0;return()=>{a=(a+0x6D2B79F5)>>>0;let t=a;t=Math.imul(t^t>>>15,t|1);t^=t+Math.imul(t^t>>>7,t|61);return((t^t>>>14)>>>0)/4294967296}}
// The tower is built from the room code, so every player in a room climbs the same one.
function buildTower(code,summit){
  let seed=7;for(const c of code)seed=(seed*31+c.charCodeAt(0))>>>0;const rnd=rng(seed);
  const plats=[{x:50,y:0,w:800,cp:0}],hazards=[],cps=[{x:450,y:0}];
  let y=0,cx=450,zi=1;
  for(;;){
    let dy=95+rnd()*40;const gap=y+summit;if(gap>140&&gap-dy<95)dy=gap-95;let ny=gap<=140?-summit:y-dy;const boundary=zi<=3?-summit*zi/4:null;
    if(boundary!==null&&ny<=boundary){ny=boundary;plats.push({x:50,y:ny,w:800,cp:zi});cps.push({x:450,y:ny});cx=450;zi++;y=ny;continue}
    if(ny<=-summit){plats.push({x:200,y:-summit,w:500,summit:true});break}
    const zone=Math.min(3,Math.floor(4*-ny/summit)),w=Math.round(190-zone*18-rnd()*20),dx=(rnd()*2-1)*200;
    cx=Math.max(w/2+30,Math.min(CLIMB.W-w/2-30,cx+dx));
    const q={x:cx-w/2,y:ny,w,zone};plats.push(q);y=ny;
    if(zone>=1&&rnd()<.16+.07*zone)hazards.push({cx:cx,y:ny-40,amp:w/2+22,sp:1.1+rnd()*1.1,ph:rnd()*6.3});
  }
  return{plats,hazards,cps,summit};
}
function climbSaveEnergy(){try{storageSet('mm-energy-'+CLIMB.room+'-'+state.player.id,{e:CLIMB.energy,d:CLIMB.h})}catch{}}
function climbLoadEnergy(h){
  let saved=null;try{saved=storageGet('mm-energy-'+CLIMB.room+'-'+state.player.id,null)}catch{}
  CLIMB.energy=saved&&Number.isFinite(saved.e)?Math.max(0,saved.e+Math.max(0,h-(saved.d||0))*climbEnergyPer()):climbEnergyPer()*(1+h);
}
function climbRespawn(why){
  const c=CLIMB.tower.cps[CLIMB.cp];pos.x=c.x;pos.y=c.y-CLIMB.HALF;CLIMB.vx=CLIMB.vy=0;CLIMB.ground=true;CLIMB.dj=1;if(why)toast(why);
}
function climbHud(){
  if(!state)return;const climb=climbOn(),r=state.room,p=state.player;
  $('#relay-start')?.classList.toggle('hidden',climb);$('#cell-count')?.classList.toggle('hidden',climb);$('#boost-hud')?.classList.toggle('hidden',climb);
  const pill=document.querySelector('.live-pill');if(pill)pill.textContent=climb?'● TOWER':'● SECTOR 09';
  const mb=document.querySelector('.map-bottom');if(mb)mb.innerHTML=climb?'<span>← → &nbsp; MOVE</span><span>↑ / SPACE &nbsp; JUMP · AGAIN IN AIR = DOUBLE</span><span>ENTER &nbsp; ANSWER FOR ⚡ ENERGY</span>':'<span>WASD / ↑↓←→ &nbsp; MOVE</span><span>ENTER &nbsp; INTERACT</span><span>SPACE &nbsp; DASH · RECHARGES</span><span>⚡ COLLECT CELLS</span>';
  $('#world')?.setAttribute('aria-label',climb?'Tower. Move with left and right arrows, jump with up arrow or space, double jump in the air, and press Enter to answer a question for energy.':'Space station. Move using WASD or arrow keys; press Enter near a station to interact.');
  $('#viewport')?.classList.toggle('climb',climb);
  const jb=document.querySelector('.dashbtn');if(jb){if(jb.dataset.orig===undefined)jb.dataset.orig=jb.innerHTML;jb.innerHTML=climb?'⬆️<small>JUMP</small>':jb.dataset.orig;jb.setAttribute('aria-label',climb?'Jump':'Dash')}
  const swap=(id,station,tower)=>{const e=document.getElementById(id);if(e)e.innerHTML=climb?tower:station};
  swap('side-eyebrow','STATION STATUS','TOWER PROGRESS');swap('side-title','Bring it back<br>to life.','Climb to<br>the top.');
  swap('side-face','🧑‍🔧','🧗');swap('side-card-title','🛠️ Ship engineer','🧗 Tower guide');
  swap('side-card-text','Run supplies 📦, collect energy ⚡, and repair the station 🔧. Chat whenever you want; leave whenever you want.','Moving and jumping use energy. Answer a question any time and explain your thinking to refill it, then keep climbing.');
  $('#boost-meter')?.classList.toggle('hidden',climb);$('#objectivesbtn')?.classList.toggle('hidden',climb);
  if(!climb)return;
  const h=climbHeight(),floors=climbFloors();
  $('#mission-label').textContent=r.mode==='solo'?'SOLO CLIMB':`${r.mode==='race'?p.team.toUpperCase()+' TEAM RACE':'TOWER CLIMB'} · ${r.code}`;
  $('#station-list').innerHTML=r.pack.topics.map((t,i)=>{const done=p.completed.filter(x=>x.startsWith(i+':')).length,n=t.questions.length;return `<div class="station-entry ${done>=n?'complete':''}" style="--rc:${roomColor(i)}"><span class="indicator">${done>=n?'✓':i+1}</span><span>${esc(t.name)}</span><small>${done}/${n}</small></div>`}).join('');
  climbMini();
}
function climbRules(){
  const per=climbEnergyPer();
  modal(`<div class="rules"><div class="eyebrow">TOWER CLIMB</div><h2>Climb as high as you can.</h2><ul><li>Move with <b>← →</b>. Jump with <b>↑</b> or <b>Space</b>, and press jump again in the air for a <b>double jump</b>. On a touch screen use the on-screen buttons.</li><li>Moving and jumping use up your <b>⚡ energy</b>. Standing still is free.</li><li>Out of energy? Press <b>Enter</b> any time to answer a question. Explain your thinking, and a good explanation refills your energy.</li><li>Watch for spiky orbs. If one touches you, you go back to the last checkpoint floor.</li><li>${state.room.mode==='race'?'The first team to reach the top wins.':'See how high your class can get together.'}</li></ul><button class="primary" onclick="closeModal()">Start climbing</button></div>`);
}
async function climbEnter(){
  if(!state||state.player.active)return;
  if(climbHeight()>=climbFloors())return toast('🏆 You answered everything. Your energy never runs out, so go for the top!');
  keys.clear();
  try{const epoch=++encounterEpoch;reqId=null;const data=await api('/api/start',auth({topic:climbHeight()%state.room.pack.topics.length}));if(epoch===encounterEpoch){state=data;syncEncounter(true);$('#answer').focus()}}catch(e){toast(e.message)}
}
function drawClimb(ts,dt,paused){
  const r=state.room,p=state.player,h=climbHeight(),floors=climbFloors(),summit=climbSummit(),per=climbEnergyPer(),maxE=per*3;
  dt=Math.min(dt,.05);
  if(CLIMB.room!==r.code||!CLIMB.tower||CLIMB.tower.summit!==summit){
    CLIMB.room=r.code;CLIMB.tower=buildTower(r.code,summit);CLIMB.h=h;CLIMB.cp=0;CLIMB.zoneSeen=0;CLIMB.celebrated=false;climbLoadEnergy(h);
    if(typeof p.y==='number'&&p.y<-5&&p.y>-summit-200){pos.x=p.x;pos.y=p.y;CLIMB.vx=CLIMB.vy=0;CLIMB.ground=false;const z=Math.min(3,Math.floor(4*-(p.y+CLIMB.HALF)/summit));CLIMB.cp=z;CLIMB.zoneSeen=z}else climbRespawn();
    CLIMB.best=Math.max(CLIMB.best,metersOf(pos.y+CLIMB.HALF));climbHud()}
  if(h>CLIMB.h){const gain=(h-CLIMB.h)*per;CLIMB.energy=Math.min(maxE,CLIMB.energy+gain);CLIMB.flash=ts+900;toast(h>=floors?'🏆 You answered everything! Unlimited energy. Go for the top!':`⚡ +${gain} energy! Keep climbing.`);CLIMB.h=h;climbSaveEnergy();climbHud()}
  if(p.active)CLIMB.wasActive=true;else if(CLIMB.wasActive){CLIMB.wasActive=false}
  const T=CLIMB.tower,plats=T.plats,free=h>=floors;
  if(free)CLIMB.energy=maxE;
  if(!paused){
    const left=keys.has('a')||keys.has('arrowleft'),right=keys.has('d')||keys.has('arrowright'),jump=keys.has('w')||keys.has('arrowup')||keys.has(' ');
    const canMove=CLIMB.energy>0;
    let want=((right?1:0)-(left?1:0))*CLIMB.SPEED;if(!canMove)want=0;
    if(want!==0&&!free)CLIMB.energy=Math.max(0,CLIMB.energy-CLIMB.WCOST*dt);
    CLIMB.vx+=(want-CLIMB.vx)*Math.min(1,dt*(CLIMB.ground?18:9));
    if(jump&&!CLIMB.jumpPrev)CLIMB.buf=.12;CLIMB.jumpPrev=jump;CLIMB.buf=Math.max(0,CLIMB.buf-dt);CLIMB.coyote=CLIMB.ground?.1:Math.max(0,CLIMB.coyote-dt);
    if(CLIMB.buf>0&&CLIMB.energy>=CLIMB.JCOST*.5){
      if(CLIMB.coyote>0){CLIMB.vy=-CLIMB.JUMP;CLIMB.buf=0;CLIMB.coyote=0;CLIMB.ground=false;if(!free)CLIMB.energy=Math.max(0,CLIMB.energy-CLIMB.JCOST)}
      else if(CLIMB.dj>0){CLIMB.vy=-CLIMB.JUMP2;CLIMB.buf=0;CLIMB.dj--;if(!free)CLIMB.energy=Math.max(0,CLIMB.energy-CLIMB.JCOST);CLIMB.rings.push({x:pos.x,y:pos.y+CLIMB.HALF,t:ts})}
    }
    const prevFeet=pos.y+CLIMB.HALF;CLIMB.vy=Math.min(1300,CLIMB.vy+CLIMB.G*dt);pos.x=Math.max(16,Math.min(CLIMB.W-16,pos.x+CLIMB.vx*dt));pos.y+=CLIMB.vy*dt;
    const feet=pos.y+CLIMB.HALF;CLIMB.ground=false;
    if(CLIMB.vy>=0)for(const q of plats){if(Math.abs(q.y-feet)>80)continue;if(pos.x>q.x-12&&pos.x<q.x+q.w+12&&prevFeet<=q.y+5&&feet>=q.y){pos.y=q.y-CLIMB.HALF;CLIMB.vy=0;CLIMB.ground=true;CLIMB.dj=1;break}}
    const cpY=T.cps[CLIMB.cp].y;if(pos.y>cpY+CLIMB.HALF+420)climbRespawn('🪂 Back to your checkpoint!');
    // zones and checkpoints
    const fm=-(pos.y+CLIMB.HALF),z=Math.min(3,Math.max(0,Math.floor(4*fm/summit)));
    if(z>CLIMB.zoneSeen){CLIMB.zoneSeen=z;CLIMB.cp=z;toast(`📍 Zone ${z+1}: ${ZONES[z].name}. Checkpoint saved.`)}
    CLIMB.best=Math.max(CLIMB.best,metersOf(pos.y+CLIMB.HALF));
    // hazards
    for(const hz of T.hazards){if(Math.abs(hz.y-pos.y)>60)continue;const hx=hz.cx+Math.sin(ts/1000*hz.sp+hz.ph)*hz.amp;if(Math.hypot(hx-pos.x,hz.y-pos.y)<CLIMB.HALF+13){CLIMB.hurt=ts+500;climbRespawn('💥 Zapped! Back to your checkpoint floor.');break}}
    if(Math.round(ts/1000)!==CLIMB.saveSec){CLIMB.saveSec=Math.round(ts/1000);if(CLIMB.saveSec%3===0)climbSaveEnergy()}
    if(!CLIMB.celebrated&&pos.y+CLIMB.HALF<=-summit+4&&CLIMB.ground){CLIMB.celebrated=true;toast('🏆 You reached the top!');if(typeof celebrate==='function')celebrate(1)}
  }
  // camera
  const rect=canvas.getBoundingClientRect(),dpr=Math.min(devicePixelRatio||1,2);
  if(canvas.width!==Math.round(rect.width*dpr)||canvas.height!==Math.round(rect.height*dpr)){canvas.width=Math.round(rect.width*dpr);canvas.height=Math.round(rect.height*dpr)}
  ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,rect.width,rect.height);
  const scale=Math.max(.55,Math.min(rect.width/CLIMB.W,rect.height/540,1.15)),viewH=rect.height/scale,viewW=rect.width/scale;
  const camX=(CLIMB.W-viewW)/2,camY=pos.y-viewH*.6,mid=-(pos.y);
  const zf=Math.max(0,Math.min(3,4*mid/summit)),zi=Math.min(3,Math.floor(zf)),zn=Math.min(3,zi+1),zt=zf-zi;
  const mix=(a,b,k)=>a.map((v,n)=>v+(b[n]-v)*k),hsl=c=>`hsl(${c[0]},${c[1]}%,${c[2]}%)`;
  const g=ctx.createLinearGradient(0,0,0,rect.height);g.addColorStop(0,hsl(mix(ZONES[zi].top,ZONES[zn].top,zt)));g.addColorStop(1,hsl(mix(ZONES[zi].bot,ZONES[zn].bot,zt)));ctx.fillStyle=g;ctx.fillRect(0,0,rect.width,rect.height);
  const alt=Math.min(1,mid/summit);
  ctx.save();ctx.scale(scale,scale);ctx.translate(-camX,-camY);
  // stars and clouds drift slowly with the camera
  for(let i=0;i<40;i++){const sx=(i*263)%CLIMB.W,par=.35+(i%3)*.12,ax=sx+Math.sin(ts/4000+i)*14;const yy=camY+(((i*397+(-camY*par))%viewH+viewH)%viewH);ctx.globalAlpha=alt>.55?.7:.28;ctx.fillStyle='#fff';ctx.beginPath();if(alt>.55)ctx.arc(ax,yy,2,0,7);else ctx.ellipse(ax,yy,50,13,0,0,7);ctx.fill()}ctx.globalAlpha=1;
  // side walls and height markers every 50 m
  ctx.fillStyle='#00000030';ctx.fillRect(camX-300,camY-50,300,viewH+100);ctx.fillRect(CLIMB.W,camY-50,300+Math.max(0,viewW-CLIMB.W),viewH+100);
  ctx.font='bold 11px monospace';ctx.textAlign='left';
  for(let m=Math.max(50,Math.floor(metersOf(-camY-viewH)/50)*50);m<=metersOf(-camY)+50&&m*10<=summit;m+=50){const yy=-m*10;ctx.fillStyle='#ffffff30';ctx.fillRect(0,yy,CLIMB.W,1);ctx.fillStyle='#ffffff88';ctx.fillText(m+' m',6,yy-4)}
  // platforms
  for(const q of plats){
    if(q.y<camY-60||q.y>camY+viewH+60)continue;
    const Z=ZONES[q.zone!==undefined?q.zone:(q.cp!==undefined?q.cp:3)];
    rounded(q.x,q.y,q.w,q.cp!==undefined||q.summit?26:16,6,q.cp!==undefined?'#4a3b5e':Z.plat,'#ffffff66');ctx.fillStyle=Z.edge;ctx.fillRect(q.x+4,q.y,q.w-8,4);
    if(q.cp!==undefined){ctx.fillStyle='#ffffffdd';ctx.font='bold 12px monospace';ctx.textAlign='center';ctx.fillText(q.cp===0?'START':`ZONE ${q.cp+1} · ${ZONES[q.cp].name.toUpperCase()} · ${metersOf(q.y)} m`,q.x+q.w/2,q.y+19)}
    if(q.summit){ctx.fillStyle='#2b1a15';ctx.font='bold 12px monospace';ctx.textAlign='center';ctx.fillText(`TOP · ${Math.round(summit/10)} m`,q.x+q.w/2,q.y+19);ctx.font='64px sans-serif';ctx.fillText('🏆',q.x+q.w/2,q.y-14)}
  }
  // hazards
  for(const hz of T.hazards){
    if(hz.y<camY-60||hz.y>camY+viewH+60)continue;const hx=hz.cx+Math.sin(ts/1000*hz.sp+hz.ph)*hz.amp;
    ctx.save();ctx.translate(hx,hz.y);ctx.rotate(ts/500+hz.ph);ctx.shadowColor='#ff3b5c';ctx.shadowBlur=14;ctx.fillStyle='#ff3b5c';ctx.beginPath();for(let k=0;k<16;k++){const a=k*Math.PI/8,rr=k%2?9:16;ctx.lineTo(Math.cos(a)*rr,Math.sin(a)*rr)}ctx.closePath();ctx.fill();ctx.fillStyle='#fff';ctx.beginPath();ctx.arc(0,0,4,0,7);ctx.fill();ctx.restore();
  }
  // double-jump rings
  CLIMB.rings=CLIMB.rings.filter(o=>ts-o.t<350);for(const o of CLIMB.rings){const k=(ts-o.t)/350;ctx.globalAlpha=1-k;ctx.strokeStyle='#fff';ctx.lineWidth=3;ctx.beginPath();ctx.ellipse(o.x,o.y,10+30*k,4+8*k,0,0,7);ctx.stroke()}ctx.globalAlpha=1;
  // others
  r.players.filter(o=>o.id!==p.id&&o.alive!==false&&o.y!==null&&Date.now()/1000-o.last<45).forEach(o=>{ctx.save();ctx.globalAlpha=.8;astronaut(o.x,o.y,lookClean(o.look,o.id),o.name);if(o.chatting){ctx.font='18px sans-serif';ctx.fillText('💬',o.x,o.y-58)}ctx.restore()});
  if(ts<CLIMB.hurt&&Math.floor(ts/80)%2)ctx.globalAlpha=.35;
  astronaut(pos.x,pos.y+2,lookClean(p.look,p.id),p.name,true);ctx.globalAlpha=1;
  ctx.restore();
  ctx.setTransform(dpr,0,0,dpr,0,0);
  // energy bar, height and zone
  const frac=free?1:Math.min(1,CLIMB.energy/(per*1.5)),low=!free&&CLIMB.energy<per*.3,empty=!free&&CLIMB.energy<=0,flash=ts<CLIMB.flash;
  const oy=44,hw=rect.width<500?132:200,bw=hw-20;rounded(10,oy,hw,50,10,'#000000a0','#ffffff55');
  ctx.fillStyle='#fff';ctx.font='bold 11px monospace';ctx.textAlign='left';ctx.fillText(free?'⚡ UNLIMITED ENERGY':empty?'⚡ OUT OF ENERGY':'⚡ ENERGY',20,oy+18);
  rounded(20,oy+24,bw,12,6,'#ffffff30',null);
  ctx.fillStyle=empty||low?(Math.floor(ts/260)%2?'#ff6b6b':'#ffb3b3'):flash?'#fff':'#ffd23f';if(frac>0){ctx.beginPath();ctx.roundRect?ctx.roundRect(20,oy+24,Math.max(8,bw*frac),12,6):ctx.rect(20,oy+24,Math.max(8,bw*frac),12);ctx.fill()}
  const mNow=metersOf(pos.y+CLIMB.HALF);
  ctx.textAlign='left';ctx.fillStyle='#fff';ctx.font='bold 13px monospace';rounded(10,oy+56,hw,26,10,'#000000a0','#ffffff55');ctx.fillStyle='#fff';ctx.fillText(rect.width<500?`▲ ${mNow} m · ★ ${CLIMB.best}`:`▲ ${mNow} m  ·  best ${CLIMB.best} m`,20,oy+74);
  ctx.textAlign='center';ctx.font='bold 12px monospace';ctx.fillStyle='#ffffffcc';ctx.fillText(`ZONE ${zi+1} · ${ZONES[zi].name.toUpperCase()}`,rect.width/2,22);
  // tower progress bar on the right
  const bx=rect.width-20,by=70,bh=Math.max(120,rect.height-150);
  rounded(bx-5,by,10,bh,5,'#00000055','#ffffff55');
  const dot=(y,color,rad)=>{const f=Math.max(0,Math.min(1,-y/summit));ctx.fillStyle=color;ctx.beginPath();ctx.arc(bx,by+bh-f*bh,rad,0,7);ctx.fill()};
  for(let k=1;k<4;k++){ctx.fillStyle='#ffffff55';ctx.fillRect(bx-7,by+bh-bh*k/4,14,2)}
  r.players.filter(o=>o.id!==p.id&&o.y!==null&&Date.now()/1000-o.last<45).forEach(o=>dot(o.y,o.team==='violet'?'#b58cff':o.team==='mint'?'#69f0ae':'#ffffffaa',4));dot(pos.y+CLIMB.HALF,'#ffd23f',6);
  ctx.fillStyle='#fff';ctx.font='12px sans-serif';ctx.textAlign='center';ctx.fillText('🏆',bx,by-6);
  // answer button
  if(!paused){$('#interact-prompt').classList.remove('hidden');$('#near-label').textContent=empty?'Out of energy':'Need energy?';$('#interact').textContent=h>=floors?'🏆 Everything answered':(rect.width<500?'⚡ Answer':'Enter · Answer for ⚡')}else $('#interact-prompt').classList.add('hidden');
  if(!paused&&ts-CLIMB.moveAt>160){CLIMB.moveAt=ts;api('/api/move',auth({x:pos.x,y:pos.y})).catch(()=>{})}
  if(ts-CLIMB.hudAt>300){CLIMB.hudAt=ts;climbMini()}
}
function climbMini(){
  if(!state||!climbOn())return;const p=state.player,r=state.room,summit=climbSummit(),floors=climbFloors(),h=climbHeight(),empty=CLIMB.energy<=0&&h<floors;
  const rc=$('#repair-count');if(rc)rc.textContent=`🧗 ${CLIMB.best} m`;
  const fill=$('#overall-fill');if(fill)fill.style.width=`${Math.min(100,100*CLIMB.best*10/summit)}%`;
  const pc=$('#progress-copy');if(pc)pc.textContent=`${CLIMB.best} m of ${Math.round(summit/10)} m · ${h} / ${floors} questions answered`;
  const no=$('#next-objective');if(no)no.textContent=empty?'⚡ Out of energy. Press Enter to answer a question and keep climbing.':`🎯 Reach the top (${Math.round(summit/10)} m). Answer questions to refill your energy.`;
  const cp=$('#crew-panel');if(cp){const climbers=[{name:p.name,m:CLIMB.best,team:p.team},...r.players.filter(x=>x.id!==p.id&&x.y!==null).map(x=>({name:x.name,m:metersOf(x.y+CLIMB.HALF),team:x.team}))].sort((a,b)=>b.m-a.m);
    const teamLines=r.mode==='race'?['violet','mint'].map(team=>`${team==='violet'?'🟣':'🟢'} ${team}: top climber ${Math.max(0,...climbers.filter(x=>x.team===team).map(x=>x.m))} m`).join('<br>'):climbers.slice(0,8).map(x=>`${esc(x.name)} · ${x.m} m`).join('<br>');
    cp.innerHTML=(r.winner?`<strong>${esc(r.winner).toUpperCase()} TEAM REACHED THE TOP!</strong><br>`:'')+teamLines}
}
