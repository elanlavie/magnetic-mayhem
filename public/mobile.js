// Phone helpers: a small status strip over the map, so players never scroll away from the game to see timers and progress.
(function(){
  const vp=document.getElementById('viewport');if(!vp)return;
  const hud=document.createElement('div');hud.id='mini-hud';vp.appendChild(hud);
  const clock=s=>`${Math.floor(s/60)}:${String(Math.max(0,s)%60).padStart(2,'0')}`;
  function tick(){
    if(typeof state==='undefined'||!state||view!=='game'){return}
    const r=state.room,p=state.player,g=r.game,parts=[];
    if(r.gameType==='climb'){
      // the tower draws its own energy and height readout on the map
    }else if(g&&typeof socialSeconds==='function'){
      if(g.phase==='lobby')parts.push('⏳ waiting for teacher');
      else{
        parts.push(`🧠 ${g.crewTasksDone}/${g.crewTasksTarget}`);
        if(g.phase==='playing'&&g.meetingSeconds&&g.nextMeetingAt){const s=socialSeconds(g.nextMeetingAt);parts.push(`<span class="${s<20?'warn':''}">🚨 ${clock(s)}</span>`)}
        if(g.phase!=='lobby'&&g.roundEndsAt)parts.push(`⏱️ ${clock(socialSeconds(g.roundEndsAt))}`);
        if(p.alive===false)parts.push('👻');
      }
    }
    hud.innerHTML=parts.map(x=>x.startsWith('<span')?x:`<span>${x}</span>`).join('');
  }
  setInterval(tick,400);
})();
