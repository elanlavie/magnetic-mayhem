/* DOM/canvas simulation, not a replacement for real browser testing. */
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const {createCanvas}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/\x40napi-rs/canvas');
const root=require('path').resolve(__dirname,'..');
async function run(offline){
 const elements=new Map(),events={},pending=[];const image=createCanvas(970,650);let context;
 class Element{constructor(id){this.id=id;this.value='';this.checked=false;this.disabled=false;this.dataset={};this.style={};this.tagName='DIV';this._html='';this.children=[];this.classList={s:new Set(['hidden']),add(...a){a.forEach(x=>this.s.add(x))},remove(...a){a.forEach(x=>this.s.delete(x))},contains(x){return this.s.has(x)},toggle(x,v){if(v===undefined)v=!this.s.has(x);v?this.s.add(x):this.s.delete(x)}};this.width=970;this.height=650}
 set innerHTML(s){this._html=s;for(const match of s.matchAll(/\bid="([^"]+)"/g)){const el=new Element(match[1]);elements.set('#'+match[1],el)}}get innerHTML(){return this._html}focus(){document.activeElement=this}append(x){this.children.push(x)}addEventListener(k,fn){this[k+'Listener']=fn}getClientRects(){return[1]}getBoundingClientRect(){return{width:970,height:650}}getContext(){return image.getContext('2d')}querySelectorAll(){return[]}click(){return this.onclick?.()}setPointerCapture(){}
 }
 const el=s=>{if(!elements.has(s))elements.set(s,new Element(s));return elements.get(s)};
 const document={activeElement:null,querySelector:el,querySelectorAll:s=>[],createElement:id=>new Element(id),addEventListener:(k,fn)=>events[k]=fn};const data=new Map();
 const sandbox={console,document,localStorage:{getItem:k=>data.get(k)||null,setItem:(k,v)=>data.set(k,v)},location:{protocol:offline?'file:':'http:',search:'',origin:'http://localhost:8000',pathname:'/'},window:{scrollTo(){},addEventListener(){},MM_BUILTIN:JSON.parse(fs.readFileSync(root+'/public/curriculum.json'))},crypto:require('crypto').webcrypto,URL,URLSearchParams,Blob,fetch:(url,args)=>fetch('http://localhost:8000'+url,args),devicePixelRatio:1,setTimeout:(fn)=>{pending.push(fn);return 1},clearTimeout(){},setInterval(){},requestAnimationFrame(){},confirm:()=>true,navigator:{}};
 context=vm.createContext(sandbox);vm.runInContext(fs.readFileSync(root+'/public/app.js','utf8'),context);
 for(let i=0;i<20;i++)await new Promise(r=>setTimeout(r,20));
 assert(vm.runInContext('Boolean(config)',context),'config loads');
 await vm.runInContext('soloSetup()',context);el('#nickname').value='Ada';el('#solo-pack').value='builtin';el('#relaxed').checked=false;
 await el('#startsolo').onclick();assert.equal(vm.runInContext('view',context),'game');
 vm.runInContext('draw(1000)',context);const before=vm.runInContext('pos.x',context);vm.runInContext("keys.add('d');draw(1050);keys.clear()",context);assert(vm.runInContext('pos.x',context)>before,'movement changes position');
 // Walk to station 4 through open corridor using API movement, then synchronize the local avatar.
 await vm.runInContext(`(async()=>{for(const [x,y] of [[640,460],[480,460],[320,460],[250,460],[250,360],[250,240]])await api('/api/move',auth({x,y}));pos.x=250;pos.y=240;near=0;await interact()})()`,context);
 assert(vm.runInContext('Boolean(state.player.active)',context),'encounter opens');assert(!el('#encounter').classList.contains('hidden'));
 vm.runInContext('startTimer(60);renderTimer()',context);assert.equal(el('#timer').textContent,'1:00');
 vm.runInContext('startTimer(0);renderTimer()',context);assert(!el('#timeup').classList.contains('hidden'),'timer prompts without submitting');
 await vm.runInContext("sendChat('hint')",context);assert.equal(vm.runInContext('state.player.active.attempts',context),0);assert(vm.runInContext('awaitReady',context),'feedback waits for readiness');
 const answer=vm.runInContext('config.builtin.topics[0].questions[0].answer',context);el('#answer').value=answer;await vm.runInContext('sendChat()',context);assert(vm.runInContext('state.player.active.done',context));assert.equal(vm.runInContext('state.player.score',context),1);
 await el('#returnmap').onclick();assert.equal(vm.runInContext('state.player.active',context),null);
 vm.runInContext('draw(2000)',context);fs.writeFileSync('/tmp/mm-map-'+(offline?'offline':'server')+'.png',image.toBuffer('image/png'));
 console.log((offline?'standalone':'server')+': setup, movement, encounter, timer, hints, readiness, scoring, return-to-map passed');
}
(async()=>{await run(false);await run(true)})().catch(e=>{console.error(e);process.exit(1)});
