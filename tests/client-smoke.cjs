/* Client event/state regression checks. Rendering is verified separately in Chrome. */
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const root=require('path').resolve(__dirname,'..'),builtin=JSON.parse(fs.readFileSync(root+'/public/curriculum.json'));
const elements=new Map(),events={},store=new Map();
class Element{
 constructor(id){this.id=id;this.value='';this.checked=false;this.disabled=false;this.dataset={};this.style={};this.tagName='DIV';this.children=[];this.classList={s:new Set(['hidden']),add(...a){a.forEach(x=>this.s.add(x))},remove(...a){a.forEach(x=>this.s.delete(x))},contains(x){return this.s.has(x)},toggle(x,v){if(v===undefined)v=!this.s.has(x);v?this.s.add(x):this.s.delete(x)}};}
 set innerHTML(s){this.html=s;for(const m of s.matchAll(/\bid="([^"]+)"/g))elements.set('#'+m[1],new Element(m[1]));}get innerHTML(){return this.html||'';}
 focus(){document.activeElement=this;}append(e){this.children.push(e);}addEventListener(k,fn){this[k+'Listener']=fn;}getClientRects(){return[1];}getBoundingClientRect(){return{width:970,height:650};}getContext(){return{};}click(){return this.onclick?.();}
}
const el=s=>{if(!elements.has(s))elements.set(s,new Element(s));return elements.get(s);};
const document={activeElement:null,querySelector:el,querySelectorAll:()=>[],createElement:id=>new Element(id),addEventListener:(k,fn)=>events[k]=fn};
const pack=JSON.parse(JSON.stringify(builtin));pack.topics.forEach(t=>{t.count=t.questions.length;delete t.questions;});
let current={room:{code:'TEST',mode:'solo',pack,players:[],ai:true,first:30,followup:30,paused:false,closed:false,teamRepairs:{crew:[]}},player:{id:'p',name:'Tester',team:'crew',x:800,y:460,completed:[],score:0,cells:0,repairs:[],active:null,history:[],studied:[],relayRecords:{}}};
let suspended=null,chatCount=0;
const sandbox={console,document,location:{protocol:'http:',search:'',origin:'http://localhost',pathname:'/'},window:{scrollTo(){},addEventListener(){}},localStorage:{getItem:k=>store.get(k)||null,setItem:(k,v)=>store.set(k,v)},crypto:require('crypto').webcrypto,URL,URLSearchParams,Blob,Date,devicePixelRatio:1,setTimeout,clearTimeout,setInterval(){},requestAnimationFrame(){},confirm:()=>true,navigator:{},fetch:async(path,args)=>{const d=JSON.parse(args?.body||'{}');let result=current;
 if(path==='/api/config')result={live:true,model:'claude-sonnet-5-5',builtin};
 if(path==='/api/create'){assert(!('live' in d),'no AI-off switch in solo request');result={code:'TEST'};}
 if(path==='/api/join')result={...current,token:'test-token'};
 if(path==='/api/move')result={ok:true,x:d.x,y:d.y};
 if(path==='/api/start')current.player.active=suspended||{id:'challenge',topic:0,index:0,messages:[{role:'assistant',text:'A conceptual question.'}],done:false,busy:false,attempts:0};
 if(path==='/api/leave'){suspended=current.player.active;current.player.active=null;}
 if(path==='/api/chat'){chatCount++;current.player.active.messages.push({role:'user',text:d.text},{role:'assistant',text:'A focused follow-up. 💡'});}
 return{ok:true,json:async()=>JSON.parse(JSON.stringify(result))};}};
const context=vm.createContext(sandbox);vm.runInContext(fs.readFileSync(root+'/public/social.js','utf8'),context);vm.runInContext(fs.readFileSync(root+'/public/app.js','utf8'),context);
const flush=async()=>{for(let i=0;i<8;i++)await new Promise(r=>setImmediate(r));};
(async()=>{
 await flush();await vm.runInContext('soloSetup()',context);el('#solo-style').value='solo';el('#nickname').value='Tester';el('#solo-pack').value='builtin';await el('#startsolo').onclick();assert.equal(vm.runInContext('view',context),'game');assert(!el('#modal').classList.contains('hidden'),'rules appear at launch');
 await el('#begin-exploring').onclick();vm.runInContext('near=0',context);await vm.runInContext('interact()',context);
 el('#answer').value='a concise idea';let prevented=false;el('#answer').keydownListener({key:'Enter',shiftKey:false,isComposing:false,keyCode:13,preventDefault(){prevented=true;}});await flush();assert(prevented);assert.equal(chatCount,1);assert(vm.runInContext('timerActive',context),'follow-up countdown starts automatically');assert(vm.runInContext('timerRemaining',context)<=30000);
 el('#answer').keydownListener({key:'Enter',shiftKey:true,isComposing:false,keyCode:13,preventDefault(){throw Error('Shift+Enter must remain a newline');}});assert.equal(chatCount,1);
 el('#answer').keydownListener({key:'Enter',shiftKey:false,isComposing:true,keyCode:229,preventDefault(){throw Error('Do not submit IME composition');}});assert.equal(chatCount,1);
 el('#answer').value='unfinished draft';events.keydown({key:'Escape',preventDefault(){}});await flush();assert(el('#encounter').classList.contains('hidden'));assert.equal(vm.runInContext('state.player.active',context),null);
 await vm.runInContext('interact()',context);assert.equal(el('#answer').value,'unfinished draft');assert.equal(vm.runInContext('state.player.active.messages.length',context),3);
 el('#encounter').onclick({target:el('#encounter')});await flush();assert(el('#encounter').classList.contains('hidden'),'backdrop closes chat');
 console.log('Client checks passed: always-on solo, onboarding, Enter, Shift+Enter, IME, automatic timer, Escape, backdrop, saved draft and conversation.');
})().catch(e=>{console.error(e);process.exitCode=1;});
