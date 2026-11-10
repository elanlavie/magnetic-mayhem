// Imposter characters: a round critter with a shape, face, hat and one of 16 colors.
const LOOK_COLORS={Red:'#e5484d',Orange:'#f5882b',Yellow:'#f7d23e',Lime:'#9bd93c',Green:'#2fa764',Teal:'#20b2aa',Cyan:'#3cc8f0',Blue:'#3d6fe0',Indigo:'#5b4bdb',Purple:'#9b59d6',Pink:'#f472b6',Magenta:'#d6338a',Brown:'#8a5a3c',Tan:'#d9b88f',White:'#f2f2f2',Charcoal:'#3a3f4b'};
const LOOK_SHAPES=['blob','bunny','cat','bot'],LOOK_FACES=['happy','sleepy','wink','wow'],LOOK_HATS=['none','antenna','sprout','cap','phones','crown'];
const LOOK_LABELS={blob:'Blob',bunny:'Bunny',cat:'Cat',bot:'Bot',happy:'Happy',sleepy:'Sleepy',wink:'Wink',wow:'Wow',none:'No hat',antenna:'Antenna',sprout:'Sprout',cap:'Cap',phones:'Headphones',crown:'Crown'};
function lookShade(hex,k){const n=parseInt(hex.slice(1),16),f=v=>Math.max(0,Math.min(255,Math.round(v*k)));return `rgb(${f(n>>16)},${f(n>>8&255)},${f(n&255)})`}
function lookDefault(seed=''){let h=0;for(const ch of String(seed))h=(h*31+ch.charCodeAt(0))>>>0;const names=Object.keys(LOOK_COLORS);return{color:names[h%names.length],shape:LOOK_SHAPES[h>>3&3],face:LOOK_FACES[h>>5&3],hat:LOOK_HATS[h>>7&3]}}
function lookRandom(){const pick=a=>a[Math.floor(Math.random()*a.length)];return{color:pick(Object.keys(LOOK_COLORS)),shape:pick(LOOK_SHAPES),face:pick(LOOK_FACES),hat:pick(LOOK_HATS)}}
function lookClean(l,seed){const d=lookDefault(seed);l=l||{};return{color:LOOK_COLORS[l.color]?l.color:d.color,shape:LOOK_SHAPES.includes(l.shape)?l.shape:d.shape,face:LOOK_FACES.includes(l.face)?l.face:d.face,hat:LOOK_HATS.includes(l.hat)?l.hat:d.hat}}
// Draws a critter centred on (x,y). About 44px wide and 56px tall at scale 1.
function drawCritter(c,x,y,look,t=0,s=1,ghost=false){
 const base=LOOK_COLORS[look.color]||'#999',dark=lookShade(base,.62),light=lookShade(base,1.18),bob=t?Math.sin(t/260)*1.6:0;
 c.save();c.translate(x,y+bob);c.scale(s,s);if(ghost)c.globalAlpha=.5;c.lineJoin='round';c.lineCap='round';
 c.fillStyle='#0005';c.beginPath();c.ellipse(0,25-bob,17,5.5,0,0,7);c.fill();
 const fill=(col,stroke=dark)=>{c.fillStyle=col;c.fill();if(stroke){c.strokeStyle=stroke;c.lineWidth=2;c.stroke()}};
 const ear=(ex,tilt,inner)=>{c.save();c.translate(ex,-23);c.rotate(tilt);c.beginPath();c.ellipse(0,-9,5.2,12,0,0,7);fill(base);c.beginPath();c.ellipse(0,-9,2.4,8,0,0,7);c.fillStyle=inner;c.fill();c.restore()};
 if(look.shape==='bunny'){ear(-9,-.18,'#ffc2d4');ear(9,.18,'#ffc2d4')}
 if(look.shape==='cat'){for(const m of[-1,1]){c.beginPath();c.moveTo(m*5,-21);c.lineTo(m*17,-35);c.lineTo(m*18,-13);c.closePath();fill(base);c.beginPath();c.moveTo(m*8,-20);c.lineTo(m*15,-30);c.lineTo(m*15,-16);c.closePath();c.fillStyle='#ffc2d4';c.fill()}}
 for(const m of[-1,1]){c.beginPath();c.ellipse(m*9,22,6.5,4.6,0,0,7);fill(dark,null)}
 for(const m of[-1,1]){c.beginPath();c.ellipse(m*20,5+Math.sin(t/200+m)*(t?1.5:0),5,7,m*.4,0,7);fill(base)}
 c.beginPath();if(look.shape==='bot')c.roundRect(-19,-22,38,44,13);else c.ellipse(0,-1,19,23,0,0,7);fill(base);
 c.beginPath();if(look.shape==='bot')c.roundRect(-12,2,24,15,8);else c.ellipse(0,9,11,11,0,0,7);c.fillStyle=light;c.globalAlpha*=.55;c.fill();c.globalAlpha=ghost?.5:1;
 if(look.shape==='bot'){c.fillStyle=dark;for(const m of[-1,1]){c.beginPath();c.arc(m*19,-2,3,0,7);c.fill()}}
 const eye=(ex,kind)=>{if(kind==='arc'){c.beginPath();c.arc(ex,-5,4.6,Math.PI*1.1,Math.PI*1.9);c.strokeStyle='#2a1a16';c.lineWidth=2.4;c.stroke();return}
  const r=kind==='wow'?6.8:5.6;c.beginPath();c.arc(ex,-6,r,0,7);c.fillStyle='#fff';c.fill();c.strokeStyle=dark;c.lineWidth=1.2;c.stroke();c.beginPath();c.arc(ex+.6,-5.6,r*.55,0,7);c.fillStyle='#2a1a16';c.fill();c.beginPath();c.arc(ex+1.9,-7.4,1.5,0,7);c.fillStyle='#fff';c.fill()};
 const f=look.face;eye(-7.5,f==='sleepy'?'arc':f==='wow'?'wow':'eye');eye(7.5,f==='sleepy'||f==='wink'?'arc':f==='wow'?'wow':'eye');
 c.fillStyle='#ff8fa866';for(const m of[-1,1]){c.beginPath();c.ellipse(m*12.5,2.5,3.2,2,0,0,7);c.fill()}
 c.strokeStyle='#2a1a16';c.lineWidth=2;c.beginPath();if(f==='wow'){c.ellipse(0,6.5,2.4,3,0,0,7);c.fillStyle='#5a2a2a';c.fill()}else{c.arc(0,2.6,4.2,.2,Math.PI-.2);c.stroke()}
 const top=look.shape==='bot'?-22:-24;
 if(look.hat==='antenna'){c.strokeStyle=dark;c.lineWidth=2.4;c.beginPath();c.moveTo(0,top+2);c.lineTo(0,top-9);c.stroke();c.beginPath();c.arc(0,top-11,3.6,0,7);c.fillStyle='#ffd23f';c.fill();c.strokeStyle='#b88a00';c.lineWidth=1.4;c.stroke()}
 if(look.hat==='sprout'){c.strokeStyle='#3f8f3a';c.lineWidth=2.4;c.beginPath();c.moveTo(0,top+2);c.quadraticCurveTo(1,top-5,0,top-9);c.stroke();for(const m of[-1,1]){c.beginPath();c.ellipse(m*5,top-9,5.2,2.8,m*-.5,0,7);c.fillStyle='#6fcf62';c.fill();c.strokeStyle='#3f8f3a';c.lineWidth=1.2;c.stroke()}}
 if(look.hat==='cap'){c.beginPath();c.moveTo(-17,top+8);c.quadraticCurveTo(-16,top-7,0,top-7);c.quadraticCurveTo(16,top-7,17,top+8);c.closePath();c.fillStyle='#2b3a67';c.fill();c.strokeStyle='#18213f';c.lineWidth=1.6;c.stroke();c.beginPath();c.ellipse(11,top+8,12,3.2,.08,0,7);c.fillStyle='#3d52a0';c.fill();c.stroke();c.beginPath();c.arc(0,top-5.5,2,0,7);c.fillStyle='#ffd23f';c.fill()}
 if(look.hat==='phones'){c.strokeStyle='#2c2c36';c.lineWidth=3.2;c.beginPath();c.arc(0,-2,21.5,Math.PI*1.07,Math.PI*1.93);c.stroke();for(const m of[-1,1]){c.beginPath();c.roundRect(m*20-4,-8,8,13,3);c.fillStyle='#ff5a64';c.fill();c.strokeStyle='#2c2c36';c.lineWidth=1.6;c.stroke()}}
 if(look.hat==='crown'){c.beginPath();c.moveTo(-10,top+4);c.lineTo(-11,top-8);c.lineTo(-5,top-2);c.lineTo(0,top-11);c.lineTo(5,top-2);c.lineTo(11,top-8);c.lineTo(10,top+4);c.closePath();c.fillStyle='#ffd23f';c.fill();c.strokeStyle='#b88a00';c.lineWidth=1.6;c.stroke();c.beginPath();c.arc(0,top-2,1.8,0,7);c.fillStyle='#e5484d';c.fill()}
 c.restore()}
// Character picker: preview, 16 colors, shape/face/hat. taken = colors other players already use.
function mountLookPicker(root,look,taken=[],onChange=()=>{}){
 look=lookClean(look);const opt=(group,arr)=>`<div class="look-group" data-g="${group}">${arr.map(v=>`<button type="button" class="look-opt${look[group]===v?' on':''}" data-v="${v}">${LOOK_LABELS[v]}</button>`).join('')}</div>`;
 root.innerHTML=`<div class="look-picker"><canvas class="look-preview" width="150" height="170" aria-label="Character preview"></canvas><div class="look-controls"><div class="look-swatches" role="radiogroup" aria-label="Color">${Object.keys(LOOK_COLORS).map(n=>`<button type="button" class="swatch${look.color===n?' on':''}" data-color="${n}" style="background:${LOOK_COLORS[n]}" ${taken.includes(n)&&look.color!==n?'disabled':''} aria-label="${n}${taken.includes(n)?' (taken)':''}" title="${n}${taken.includes(n)?' (taken)':''}"></button>`).join('')}</div><div class="look-name"></div>${opt('shape',LOOK_SHAPES)}${opt('face',LOOK_FACES)}${opt('hat',LOOK_HATS)}<button type="button" class="small look-random">🎲 Surprise me</button></div></div>`;
 const cv=root.querySelector('canvas'),c=cv.getContext('2d');let raf=0;
 const frame=ts=>{if(!document.body.contains(cv))return;c.clearRect(0,0,150,170);drawCritter(c,75,92,look,ts,2.1);raf=requestAnimationFrame(frame)};frame(0);
 const sync=()=>{root.querySelectorAll('.swatch').forEach(b=>b.classList.toggle('on',b.dataset.color===look.color));root.querySelectorAll('.look-opt').forEach(b=>b.classList.toggle('on',look[b.parentElement.dataset.g]===b.dataset.v));root.querySelector('.look-name').textContent=look.color+' '+LOOK_LABELS[look.shape].toLowerCase();onChange({...look})};
 root.querySelectorAll('.swatch').forEach(b=>b.onclick=()=>{look.color=b.dataset.color;sync()});
 root.querySelectorAll('.look-opt').forEach(b=>b.onclick=()=>{look[b.parentElement.dataset.g]=b.dataset.v;sync()});
 root.querySelector('.look-random').onclick=()=>{const free=Object.keys(LOOK_COLORS).filter(n=>!taken.includes(n)),r=lookRandom();if(free.length)r.color=free[Math.floor(Math.random()*free.length)];Object.assign(look,r);sync()};
 sync();return()=>({...look})}
