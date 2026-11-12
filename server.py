"""Imposter. Standard-library server; optional pypdf/python-docx imports."""
import quizparse
import urllib.parse, base64, copy, hashlib, io, json, math, os, re, secrets, sqlite3, threading, time
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.request import Request, urlopen
import social_game as social
import game_types
import accounts

ROOT=Path(__file__).parent
BUILTIN=json.loads((ROOT/'public/curriculum.json').read_text())
DB=os.environ.get('GAME_DB',str(ROOT/'game.sqlite3'))
TEACHER_KEY=os.environ.get('TEACHER_KEY','')
LOCK=threading.RLock()
ROOMS={}
POSITIONS=[(250,240),(800,220),(1350,240),(260,650),(800,650),(1340,650),(800,1010)]
social.STATIONS=POSITIONS
social.CREDITED=lambda room,p:accounts.hw_credited(DB,p['email'],room['assignmentId']) if room.get('assignmentId') and p.get('email') else set()

def _record_round(rec):
    try:accounts.record_round(DB,rec)
    except Exception:pass
social.RECORDER=_record_round

WALLS=[(40,40,500,18),(40,40,18,360),(520,40,18,290),(40,390,180,18),(330,390,210,18),(600,40,400,18),(600,40,18,280),(980,40,18,280),(600,330,130,18),(870,330,130,18),(1060,40,500,18),(1060,40,18,290),(1540,40,18,360),(1060,390,210,18),(1380,390,180,18),(40,500,500,18),(40,500,18,360),(520,580,18,280),(40,840,180,18),(330,840,210,18),(1060,500,500,18),(1060,580,18,280),(1540,500,18,360),(1060,840,210,18),(1380,840,180,18),(580,890,18,220),(1000,890,18,220),(580,1090,440,18)]
RELAY_ROUTES=[{'name':'📦 Cargo dash','points':[(630,430),(400,450),(250,560),(400,450),(800,460)]},
              {'name':'🛰️ Starboard sprint','points':[(980,440),(1200,450),(1350,560),(1200,450),(800,460)]},
              {'name':'🚀 Reactor run','points':[(750,550),(850,760),(920,1030),(850,760),(800,460)]}]
NAME_ADJECTIVES=['Cosmic','Dancing','Curious','Electric','Galactic','Bouncy','Stellar','Sunny']
NAME_ANIMALS=[('🦊','Fox'),('🐧','Penguin'),('🦦','Otter'),('🐼','Panda'),('🦉','Owl'),('🐸','Frog'),('🐙','Octopus'),('🦋','Butterfly')]

def explorer_name(room):
    used={p['name'] for p in room['players'].values()}
    names=[f'{emoji} {adj} {animal}' for adj in NAME_ADJECTIVES for emoji,animal in NAME_ANIMALS]
    return secrets.choice([name for name in names if name not in used])

LOOK_COLORS=['Red','Orange','Yellow','Lime','Green','Teal','Cyan','Blue','Indigo','Purple','Pink','Magenta','Brown','Tan','White','Charcoal']
LOOK_SHAPES=['blob','bunny','cat','bot'];LOOK_FACES=['happy','sleepy','wink','wow'];LOOK_HATS=['none','antenna','sprout','cap','phones','crown']
def clean_look(v,room=None,me=None):
    """A player's character: shape, face, hat and a color that is unique within the room (the next free color if theirs is taken)."""
    v=v if isinstance(v,dict) else {}
    pick=lambda key,opts,default:v.get(key) if v.get(key) in opts else default
    look={'color':pick('color',LOOK_COLORS,None),'shape':pick('shape',LOOK_SHAPES,'blob'),'face':pick('face',LOOK_FACES,'happy'),'hat':pick('hat',LOOK_HATS,'none')}
    if room is not None:
        taken={(p.get('look') or {}).get('color') for p in room['players'].values() if p is not me}
        if look['color'] is None or look['color'] in taken:
            start=LOOK_COLORS.index(look['color']) if look['color'] in LOOK_COLORS else secrets.randbelow(len(LOOK_COLORS))
            order=LOOK_COLORS[start:]+LOOK_COLORS[:start]
            look['color']=next((c for c in order if c not in taken),look['color'] or LOOK_COLORS[start])
    elif look['color'] is None:look['color']=LOOK_COLORS[0]
    return look

GRADES=['6th grade','7th grade','8th grade','9th grade','10th grade','11th grade','12th grade','Intro college']
def clean_grade(v):
    v=str(v or '').strip()
    return v if v in GRADES else '9th grade'

GameError=social.SocialError
social.BOT_WALLS=WALLS
social.BOT_STATIONS=POSITIONS

def save():
    with sqlite3.connect(DB) as db:
        db.execute('create table if not exists rooms (code text primary key, data text not null)')
        for code,r in ROOMS.items(): db.execute('insert or replace into rooms values (?,?)',(code,json.dumps(r)))

def load():
    with sqlite3.connect(DB) as db:
        db.execute('create table if not exists rooms (code text primary key, data text not null)')
        for code,data in db.execute('select code,data from rooms'):
            r=json.loads(data)
            if time.time()-r['created']<7*86400:
                r.setdefault('gameType',game_types.DEFAULT)
                r['followup']=min(30,r.get('followup',30))
                for p in r['players'].values():
                    if p.get('active'): p['active']['busy']=False
                    for a in p.get('conversations',{}).values(): a['busy']=False
                ROOMS[code]=r

def safe_url(u):
    u=str(u or '').strip()
    return u if re.match(r'^https://[^\s<>"\']{3,490}$',u) else ''


BAD_SVG=re.compile(r'<script|on\w+\s*=|href|<image|foreignobject|<style|javascript:|<!',re.I)
def clean_svg(s):
    s=str(s or '').strip()
    if not s.lower().startswith('<svg') or len(s)>8000 or BAD_SVG.search(s): return ''
    if 'xmlns' not in s[:200]: s=s.replace('<svg','<svg xmlns="http://www.w3.org/2000/svg"',1)
    return s
def svg_url(s): return 'data:image/svg+xml;utf8,'+urllib.parse.quote(s)

def trim_pack(pack,n):
    """Keep n questions, spread evenly across topics, so every student answers exactly that many."""
    total=sum(len(t['questions']) for t in pack['topics'])
    if n>=total: return pack
    keep=[0]*len(pack['topics']);left=n
    while left>0:
        for i,t in enumerate(pack['topics']):
            if left>0 and keep[i]<len(t['questions']): keep[i]+=1;left-=1
    topics=[]
    for t,k in zip(pack['topics'],keep):
        if k: t['questions']=t['questions'][:k];topics.append(t)
    pack['topics']=topics
    return pack

def resolve_question(q,vi):
    """Question text for one student: the base question or one of its number variants."""
    vs=q.get('variants') or []
    out={k:v for k,v in q.items() if k!='variants'}
    if 0<=vi-1<len(vs): out.update({k:v for k,v in vs[vi-1].items() if v is not None and v!=''})
    return out

def clean_choices(q):
    ch=q.get('choices');ok=q.get('correct')
    if isinstance(ch,list) and 2<=len(ch)<=5 and all(isinstance(c,str) and 1<=len(c.strip())<=300 for c in ch) and isinstance(ok,int) and not isinstance(ok,bool) and 0<=ok<len(ch):
        q['choices']=[re.sub(r'[<>]','',c.strip()) for c in ch]
    else:
        q.pop('choices',None);q.pop('correct',None)

def clean_format(v):
    return {'mc':True,'free':False}  # every question is multiple choice

def answer_mode(pack,q):
    if not q.get('choices'): raise GameError('This question has no answer choices. Open the game setup and rewrite it as multiple choice.')
    return 'mc'

def validate_pack(pack):
    if not isinstance(pack,dict) or not isinstance(pack.get('title'),str): raise GameError('Pack needs a title.')
    if not isinstance(pack.get('topics'),list) or not 1<=len(pack['topics'])<=7: raise GameError('Use 1–7 topic stations per pack.')
    pack['format']=clean_format(pack.get('format'));pack.pop('context',None)
    for t in pack['topics']:
        if not isinstance(t.get('name'),str) or not 1<=len(t['name'])<=60: raise GameError('Each topic needs a short name.')
        if not isinstance(t.get('questions'),list) or not 1<=len(t['questions'])<=6: raise GameError('Each topic needs 1–6 challenges.')
        for q in t['questions']:
            if any(not isinstance(q.get(k),str) or not 1<=len(q[k])<=3500 for k in ('prompt','answer')): raise GameError('Every question needs a prompt and a short explanation of the answer.')
            q['hint']=str(q.get('hint') or '')[:3500]
        sim=t.get('sim');url=safe_url(sim.get('url')) if isinstance(sim,dict) else ''
        if url: t['sim']={'url':url,'title':str(sim.get('title') or 'Simulation')[:80]}
        else: t.pop('sim',None)
        for q in t['questions']:
            img=safe_url(q.get('image'))
            if img: q['image']=img
            else: q.pop('image',None)
            dg=clean_svg(q.get('diagram'))
            if dg: q['diagram']=dg
            else: q.pop('diagram',None)
            clean_choices(q)
            if 'choices' not in q: raise GameError('Every question needs 2 to 5 answer choices and one marked correct: “'+q['prompt'][:50]+'”.')
            if q.get('level') not in ('easy','medium','hard'): q.pop('level',None)
            vs=[]
            for v in (q.get('variants') or [])[:4]:
                if isinstance(v,dict) and all(isinstance(v.get(k),str) and 1<=len(v[k])<=3500 for k in ('prompt','answer')):
                    item={k:v[k] for k in ('prompt','answer')};item['hint']=str(v.get('hint') or '')[:3500]
                    clean_choices(v)
                    if 'choices' not in v: continue
                    item['choices']=v['choices'];item['correct']=v['correct']
                    d2=clean_svg(v.get('diagram'))
                    if d2: item['diagram']=d2
                    vs.append(item)
            if vs: q['variants']=vs
            else: q.pop('variants',None)
        t['icon']=str(t.get('icon','✦'))[:8]; t['color']='#91e8a4'
    return pack

def think_seconds(q,mode='free'):
    """Timer for one question: 30 s for multiple choice, 60 s when the student must explain. A question's own 'seconds' overrides.
    Students spend a ⚡ for +30 s, and an expired timer just sends them back to the map with the chat saved."""
    try:
        if q.get('seconds'): return max(30,min(150,int(q['seconds'])))
    except (TypeError,ValueError): pass
    return 30 if mode=='mc' else 60

def public_pack(pack):
    p=copy.deepcopy(pack)
    for t in p['topics']:
        t['count']=len(t.pop('questions'))
    return p

def room_public(r):
    players=[]
    for p in r['players'].values():
        item={k:p[k] for k in ('id','name','team','x','y','completed','score','cells','repairs','last')}
        item.update(alive=p.get('alive',True),bot=bool(p.get('bot')),look=p.get('look'))
        if r.get('game'):
            nowt=time.time();item.update(chatting=bool(p.get('active')) or nowt<p.get('botWaitingUntil',0),safe=nowt<p.get('safeUntil',0))
        if r.get('game') and not item['alive']:item['x']=item['y']=None
        players.append(item)
    teams={team:sorted({i for member in r['players'].values() if member['team']==team for i in member['repairs']}) for team in ('crew','mint','violet')}
    cell_pool(r);result={'cells':list(r['cellPool']['active']),'winner':r.get('winner'),'teamRepairs':teams,'code':r['code'],'mode':r['mode'],'gameType':r.get('gameType',game_types.DEFAULT),'pack':public_pack(r['pack']),'players':players,'paused':r['paused'],'closed':r.get('closed',False),'autoNames':r.get('autoNames',False),'first':r['first'],'unlimited':r.get('unlimited',False),'followup':min(30,r['followup']),'created':r['created'],'allowStudy':r.get('allowStudy',False)}
    if r.get('gameType')=='climb':result['floors']=climb_floors(r);result['summit']=climb_summit(r);result['energy']=r.get('energy',70)
    if r.get('game'):result['game']=social.public(r)
    return result

CELL_RESPAWN=45
CELLS_PER_PLAYER=0.75
def pickup_kind(i): return 'time'  # hints are unlimited; the only token left on the map adds thinking time
def spend(p,kind):
    """Use a matching token first (💡 hint / ⏱️ time), else a spare ⚡ cell."""
    key={'hint':'hints','time':'times'}[kind]
    if p.get(key,0)>0: p[key]-=1; return True
    if p['cells']>0: p['cells']-=1; return True
    return False

def cell_pool(r):
    """Shared ⚡ cells on the map: about three for every four players, so they stay scarce. A collected cell reappears elsewhere after a while."""
    now=time.time();pool=r.setdefault('cellPool',{'active':[],'respawn':[]});spots=len(cell_positions())
    target=min(spots,max(3,math.ceil(len(r['players'])*CELLS_PER_PLAYER)))
    due=[t for t in pool['respawn'] if t<=now];pool['respawn']=[t for t in pool['respawn'] if t>now]
    def add():
        free=[i for i in range(spots) if i not in pool['active']]
        if free and len(pool['active'])<target:pool['active'].append(secrets.choice(free))
    for _ in due:add()
    for _ in range(max(0,target-len(pool['active'])-len(pool['respawn']))):add()
    return pool['active']

def private_player(p):
    return {k:v for k,v in p.items() if k not in ('token','cache','cellAt')}

def get(rq):
    r=ROOMS.get(str(rq.get('code','')).upper())
    if not r: raise GameError('Room not found. Check the code or start a new game.')
    p=next((x for x in r['players'].values() if secrets.compare_digest(x['token'],str(rq.get('token','')))),None)
    if not p: raise GameError('Please join this room first.')
    if accounts.enabled() and r.get('classId') and p.get('email') and not accounts.has_access(DB,p['email'],r['classId']):raise GameError('You are no longer in this class.')
    return r,p

def teacher(rq):
    if TEACHER_KEY and not secrets.compare_digest(TEACHER_KEY,str(rq.get('teacherKey',''))): raise GameError('Teacher access code is incorrect.')

def teacher_gate(d):
    if accounts.enabled():accounts.need_teacher(accounts.user_for(DB,d))
    else:teacher(d)

def unique_name(r,base):
    used={p['name'] for p in r['players'].values()};name=base;i=2
    while name in used:name=f'{base} {i}';i+=1
    return name

def log_chat(r,p,a,role,text):
    if not(accounts.enabled() and r.get('classId') and p.get('email')):return None
    topic=r['pack']['topics'][a['topic']]['name']
    return accounts.log_message(DB,r['classId'],r['code'],p['email'],p.get('realName') or p['name'],f"{a['topic']}:{a['index']}",f"{topic} · chat {a['index']+1}",role,text)

def screen_chat(r,p,mid,category):
    if mid and category:accounts.flag_message(DB,r['classId'],mid,p['email'],p.get('realName') or p['name'],category)

CLIMB_W=900;CLIMB_MAX_Y=40000;CLIMB_CAP=40;CLIMB_PX=300  # pixels of tower per question
def climb_floors(r):
    """The tower has one floor per question, up to a sensible height."""
    return min(CLIMB_CAP,sum(len(t['questions']) for t in r['pack']['topics']))

def climb_summit(r):
    """How high the top of the tower is, in pixels above the start."""
    return climb_floors(r)*CLIMB_PX

def climb_done(r,p):
    """Questions that no longer need asking: for homework, the ones that earned credit; otherwise everything finished this round."""
    return accounts.hw_credited(DB,p['email'],r['assignmentId']) if r.get('assignmentId') and p.get('email') else set(p['completed'])

def chat_pick(r,p):
    """Homework chat: the next question without credit, preferring ones not yet tried this time. Returns (topic,index) or None when every question has credit."""
    credited=accounts.hw_credited(DB,p['email'],r['assignmentId']) if p.get('email') else set()
    todo=[(t,i) for t,topic in enumerate(r['pack']['topics']) for i in range(len(topic['questions'])) if f'{t}:{i}' not in credited]
    fresh=[x for x in todo if f'{x[0]}:{x[1]}' not in p['completed']]
    pick=(fresh or todo or [None])[0]
    return pick

def climb_pick(r,p,topic):
    """Use the gate's topic if it still has unanswered questions, otherwise any topic that does."""
    done=climb_done(r,p);topics=r['pack']['topics'];order=[topic]+[i for i in range(len(topics)) if i!=topic] if 0<=topic<len(topics) else list(range(len(topics)))
    for i in order:
        if any(f'{i}:{j}' not in done for j in range(len(topics[i]['questions']))):return i
    return None

def hw_info(r,p):
    total=sum(len(t['questions']) for t in r['pack']['topics']);done=len(accounts.hw_credited(DB,p['email'],r['assignmentId'])) if p.get('email') else 0
    return {'title':r['pack'].get('title',''),'total':total,'done':min(total,done),'earned':bool(p.get('hwNew'))}

def snapshot(r,p): return {'room':room_public(r),'player':{**private_player(p),**social.private(r,p),**({'hw':hw_info(r,p)} if r.get('assignmentId') else {})}}

def dispatch(path,d):
    if path=='/api/config': return {'teacherProtected':bool(TEACHER_KEY),'builtin':None if accounts.enabled() else BUILTIN,'gameTypes':game_types.public(),**accounts.public_config()}
    if path.startswith('/api/auth/') or path.startswith('/api/class/') or path.startswith('/api/library/') or path.startswith('/api/pack/') or path.startswith('/api/folder/') or path=='/api/balance' or path.startswith('/api/hw/'):
        if not accounts.enabled():raise GameError('Classes are not enabled on this server.')
        if path=='/api/pack/save':
            if not isinstance(d.get('pack'),dict):raise GameError('Nothing to save yet.')
            d={**d,'pack':validate_pack(copy.deepcopy(d['pack']))}
        result=accounts.dispatch(DB,path,d)
        if path=='/api/library/pack':result['pack']=validate_pack(result['pack'])
        return result
    if path=='/api/extract':
        teacher_gate(d)
        try:
            raw=base64.b64decode(d.get('data',''),validate=True)
            if len(raw)>4_000_000: raise GameError('Use a file smaller than 4 MB.')
            name=d.get('name','').lower()
            if name.endswith('.pdf'):
                from pypdf import PdfReader
                text='\n'.join(p.extract_text() or '' for p in PdfReader(io.BytesIO(raw)).pages[:35])
            elif name.endswith('.docx'):
                from docx import Document
                text='\n'.join(p.text for p in Document(io.BytesIO(raw)).paragraphs)
            else: text=raw.decode('utf-8-sig')
            if not text.strip(): raise GameError('No text found. Paste the text or use a searchable document.')
            return {'text':text[:40000]}
        except GameError: raise
        except ImportError: raise GameError('Install optional document dependencies from requirements.txt or paste the text.')
        except Exception: raise GameError('This file could not be read. Try pasting its text.')
    if path=='/api/parse':
        teacher_gate(d)
        res=quizparse.parse_questions(d.get('text',''),d.get('title',''))
        if not res['topics']:raise GameError('No questions were found. '+(' '.join(res['problems'][:2]) or 'Write each question with lettered choices and an Answer: line. See the example below the box.'))
        return res
    if path=='/api/create':
        homework=None
        if d.get('assignmentId'):
            if not accounts.enabled():raise GameError('Homework needs classes to be enabled.')
            homework=accounts.hw_for_play(DB,accounts.user_for(DB,d)['email'],d['assignmentId'])
            gt=d.get('gameType') if d.get('gameType') in ('chat','climb','station') else 'chat'
            d={**d,'mode':'impostorSolo' if gt=='station' else 'solo','gameType':gt,'classId':homework['classId'],'pack':homework['pack'],'packId':None,'source':'','first':30,'followup':30,'unlimited':True}
        source=ROOMS.get(str(d.get('source','')).upper()) if d.get('mode') in ('solo','impostorSolo') else None
        if d.get('source') and (not source or source.get('closed') or not source.get('allowStudy',False)): raise GameError('Study code not found, closed, or solo study is disabled.')
        if source: d={**d,'gameType':source.get('gameType',game_types.DEFAULT),'pack':source['pack'],'first':source['first'],'unlimited':source.get('unlimited',False),'followup':min(30,source['followup']),'autoNames':source.get('autoNames',False)}
        mode=d.get('mode','coop')
        if mode not in ('solo','coop','race','infiltration','impostorSolo'):raise GameError('Unknown game mode.')
        game_type=str(d.get('gameType') or game_types.DEFAULT)
        class_id=owner=None;saved_pack=None
        if accounts.enabled():
            user=accounts.user_for(DB,d)
            if d.get('packId'):
                saved_pack=accounts.pack_for(DB,user['email'],d['packId'],str(d.get('classId','')));d={**d,'pack':saved_pack}
            class_id=str(source['classId']) if source and source.get('classId') else str(d.get('classId',''))
            if not class_id:raise GameError('Choose one of your classes first.')
            if mode in ('solo','impostorSolo'):
                if not accounts.has_access(DB,user['email'],class_id):raise GameError('Join this class from your teacher\u2019s invite link first.')
            else:
                accounts.need_teacher(user)
                if not accounts.is_owner(DB,user['email'],class_id):raise accounts.AuthError('Class not found.',404)
            owner=user['email']
            if user['role']!='teacher' and not source and not saved_pack and not homework:raise GameError('Ask your teacher for a study code to practice on your own.')
            if not d.get('pack'):raise GameError('Add your questions before creating a game.')
        elif mode not in ('solo','impostorSolo'): teacher(d)
        if saved_pack and not source and not d.get('gameType'):
            saved_type=str((saved_pack.get('settings') or {}).get('gameType') or '')
            if saved_type in game_types.GAME_TYPES:game_type=saved_type
        if game_type=='climb' and mode=='impostorSolo':mode='solo';d={**d,'mode':'solo'}  # no practice-bot version of the tower
        problem=game_types.check(game_type,mode)
        if problem:raise GameError(problem)
        pack=validate_pack(copy.deepcopy(d.get('pack') or BUILTIN));pack.pop('settings',None)  # saved-game settings are for the teacher's list, not for students
        if d.get('tasksPerCrew'):
            try: pack['topics']=pack['topics'][:max(1,min(7,int(d['tasksPerCrew'])))]
            except (TypeError,ValueError): pass
        with LOCK:
            if len(ROOMS)>300: raise GameError('Server room limit reached.')
            code=''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(6))
            host=secrets.token_urlsafe(24)
            r={'code':code,'host':host,'classId':class_id,'owner':owner,'gameType':game_type,'assignmentId':homework['id'] if homework else None,'mode':d.get('mode','coop'),'pack':pack,'players':{},'created':time.time(),'paused':False,'closed':False,'allowStudy':bool(d.get('allowStudy',True)),'autoNames':bool(d.get('autoNames',False)),'grade':clean_grade(d.get('grade') or (pack.get('grade') if isinstance(pack,dict) else None)),'first':max(10,min(180,int(d.get('first',30)))),'unlimited':bool(d.get('unlimited',False)),'followup':max(10,min(30,int(d.get('followup',30))))}
            if mode in ('infiltration','impostorSolo'):
                r['mode']='infiltration';r['botPractice']=mode=='impostorSolo';r['soloRole']=d.get('soloRole','random')
                social.configure(r,{**d,**({'impostors':1,'writtenDiscussion':True} if r['botPractice'] else {})})
            if game_type=='climb':
                try:r['energy']=max(40,min(300,int(d.get('energy') or (source or {}).get('energy') or 70)))
                except (TypeError,ValueError):r['energy']=70
            ROOMS[code]=r; save()
            return {'code':code,'host':host}
    if path=='/api/join':
        with LOCK:
            r=ROOMS.get(str(d.get('code','')).upper())
            if not r: raise GameError('Room not found. Check the code.')
            if r.get('closed'): raise GameError('The teacher has closed this room.')
            identity=None
            if accounts.enabled():
                if not r.get('classId'):raise GameError('This room is not part of a class.')
                identity=accounts.user_for(DB,d)
                if not accounts.has_access(DB,identity['email'],r['classId']):raise GameError('Join this class from your teacher\u2019s invite link first.')
                again=next((x for x in r['players'].values() if x.get('email')==identity['email'] and not x.get('bot')),None)
                if again:return {**snapshot(r,again),'token':again['token']}
            if r.get('game') and r['game']['phase'] not in ('lobby','ended'):raise GameError('This round has started. Wait for the next lobby.')
            if r.get('botPractice') and any(not p.get('bot') for p in r['players'].values()):raise GameError('This is a private solo practice round.')
            if len(r['players'])>=40 or (r['mode']=='solo' and r['players']): raise GameError('This room is full.')
            if identity and not r.get('autoNames'):name=unique_name(r,accounts.game_name(DB,identity['email'],r['classId'],identity['name']))
            else:name=explorer_name(r) if r.get('autoNames') else (str(d.get('name','Explorer')).strip()[:24] or 'Explorer')
            pid=secrets.token_hex(6); token=secrets.token_urlsafe(24)
            team='crew' if r['mode']!='race' else ('violet' if sum(x['team']=='violet' for x in r['players'].values())<=sum(x['team']=='mint' for x in r['players'].values()) else 'mint')
            p={'id':pid,'token':token,'name':name,'team':team,'x':800,'y':460,'completed':[],'score':0,'cells':2,'repairs':[],'last':time.time(),'active':None,'history':[],'cache':{},'studied':[],'conversations':{},'relay':None,'relayRecords':{}}
            if identity:p['email']=identity['email'];p['realName']=identity['name']
            p['look']=clean_look(d.get('look'),r);r['players'][pid]=p
            if r.get('botPractice'):
                r['autoNames']=True
                for _ in range(5):
                    bot=copy.deepcopy(p);bot.update(id=secrets.token_hex(6),token=secrets.token_urlsafe(24),name=explorer_name(r),bot=True,look=clean_look({'shape':secrets.choice(LOOK_SHAPES),'face':secrets.choice(LOOK_FACES),'hat':secrets.choice(LOOK_HATS)},r));bot.pop('email',None);bot.pop('realName',None)
                    r['players'][bot['id']]=bot
                social.start(r)
            save(); return {**snapshot(r,p),'token':token}
    if path=='/api/host':
        with LOCK:
            r=ROOMS.get(d.get('code',''))
            if not r or not secrets.compare_digest(r['host'],str(d.get('host',''))): raise GameError('Teacher session not found.')
            action=d.get('action')
            if action=='startRound':
                if not r.get('game'):raise GameError('Select Imposter mission to start rounds.')
                social.start(r)
            if action=='endRound' and r.get('game'):social.finish(r,'teacher','The teacher ended this round. Your learning is saved.')
            if action=='removePlayer':
                if not r.get('game') or r['game']['phase']!='lobby':raise GameError('Players can only be removed before the round starts.')
                r['players'].pop(str(d.get('player','')),None)
            if action=='pause':
                r['paused']=not r['paused']
                if r.get('game'):
                    if r['paused']:r['game']['pausedAt']=time.time()
                    else:social.shift_clocks(r,time.time()-r['game'].pop('pausedAt',time.time()))
            if action=='close': r['closed']=True
            changed=social.advance(r)
            if action or changed: save()
            result=room_public(r)
            if r.get('game'):result['hostRoles']={p['id']:p.get('role','waiting') for p in r['players'].values()}
            if r.get('classId'):result['hostIdentities']={p['id']:p.get('realName','') for p in r['players'].values() if p.get('email')}
            return {'room':result}
    with LOCK:
        r,p=get(d); p['last']=time.time()
        if social.advance(r):save()
        if path=='/api/state': return snapshot(r,p)
        if path=='/api/look':
            want=(d.get('look') or {}).get('color') if isinstance(d.get('look'),dict) else None
            new=clean_look(d.get('look'),r,p)
            if want in LOOK_COLORS and new['color']!=want:
                owner=next((x['name'] for x in r['players'].values() if x is not p and (x.get('look') or {}).get('color')==want),'someone')
                raise GameError(f'{want} is taken by {owner}. Pick another color.')
            p['look']=new;save();return snapshot(r,p)
        if path=='/api/leave':
            if p['active']:
                p.setdefault('conversations',{})[str(p['active']['topic'])]=p['active']
                if r.get('game'): p.update(safeUntil=time.time()+social.SAFE_AFTER_CHAT,blockedTopic=p['active']['topic'],blockedUntil=time.time()+20)
            p['active']=None; save(); return snapshot(r,p)
        if r['paused'] or r.get('closed'): raise GameError('This game is paused or closed by the teacher.')
        if path=='/api/round':
            if not r.get('game'):raise GameError('This room is not an imposter round.')
            social.action(r,p,d,WALLS);save();return snapshot(r,p)
        if r.get('game') and r['game']['phase'] in ('lobby','briefing'):raise GameError('Wait for the teacher to start the round. Your chat is saved.' if r['game']['phase']=='lobby' else 'Read your role briefing: the round starts in a moment.')
        if r.get('game') and r['game']['phase']=='meeting' and r['game'].get('interruptChats',True) and path in ('/api/start','/api/chat','/api/hint'):raise GameError('Meeting in progress: talk it over with your class and vote. Your chats are saved.')
        if path=='/api/move':
            if not p['active']:
                x=float(d.get('x',p['x'])); y=float(d.get('y',p['y']))
                if not math.isfinite(x+y): raise GameError('Invalid location.')
                if r.get('gameType')=='climb':
                    if 0<=x<=CLIMB_W and -CLIMB_MAX_Y<=y<=400 and math.hypot(x-p['x'],y-p['y'])<=900:
                        p['x'],p['y']=x,y;p['lastMovementAt']=time.time()
                        if r['mode']=='race' and not r.get('winner') and y<=-climb_summit(r):r['winner']=p['team']  # first team to reach the top
                    return {'ok':True,'x':p['x'],'y':p['y']}
                dist=math.hypot(x-p['x'],y-p['y'])
                speed_ok=not r.get('game') or dist<=520*min(1.2,max(0,time.time()-p.get('lastMovementAt',time.time()-.4)))+18
                if speed_ok and dist<=180 and 25<=x<=1575 and 25<=y<=1125 and not any(a-14<x<a+w+14 and b-14<y<b+h+14 for a,b,w,h in WALLS): p['x'],p['y']=x,y;p['lastMovementAt']=time.time();(p['stats'].__setitem__('distance',p['stats']['distance']+dist) if r.get('game') and p.get('stats') and r['game']['phase']=='playing' else None)
            return {'ok':True,'x':p['x'],'y':p['y']}
        if path=='/api/start':
            if p['active']: return snapshot(r,p)
            topic=int(d.get('topic',-1));forced=None
            if r.get('gameType')=='chat':
                pick=chat_pick(r,p)
                if pick is None: raise GameError('All done! Every question in this assignment has credit.')
                topic,forced=pick
            if not 0<=topic<len(r['pack']['topics']): raise GameError('Unknown station.')
            if r.get('gameType')=='climb':
                topic=climb_pick(r,p,topic)
                if topic is None: raise GameError('You reached the summit! Every question is done.')
            elif r.get('gameType')!='chat' and math.dist([p['x'],p['y']],POSITIONS[topic])>125: raise GameError('Move closer to the station to interact.')
            if r.get('game') and str(topic) in r['game'].get('locks',{}): raise GameError('This room is locked for a moment. Visit another room, or press Interact to unlock it if you are not in a chat.')
            if r.get('game') and p.get('blockedTopic')==topic and time.time()<p.get('blockedUntil',0): raise GameError('Visit a different station first, then come back.')
            if p.get('blockedTopic')!=topic: p['blockedTopic']=None
            previous=p.setdefault('conversations',{}).get(str(topic))
            if previous and not previous['done']:
                p['active']=p['conversations'].pop(str(topic)); save(); return snapshot(r,p)
            t=r['pack']['topics'][topic]
            qi=social.next_question(r,p,topic) if r.get('game') else None
            if r.get('gameType')=='climb':
                done=climb_done(r,p);left=[i for i in range(len(t['questions'])) if f'{topic}:{i}' not in done];qi=secrets.choice(left)
            if forced is not None:qi=forced
            if qi is None:qi=None if any(x.startswith(f'{topic}:') for x in p['completed']) else secrets.randbelow(len(t['questions']))
            practice=qi is None
            if qi is None: qi=secrets.randbelow(len(t['questions']))
            base=t['questions'][qi];vi=secrets.randbelow(len(base.get('variants') or [])+1);q=resolve_question(base,vi)
            answer_mode(r['pack'],q);perm=list(range(len(q['choices'])));secrets.SystemRandom().shuffle(perm)  # a fresh answer order every time
            p['active']={'id':secrets.token_hex(8),'topic':topic,'index':qi,'vi':vi,'prompt':q['prompt'],'choices':[q['choices'][i] for i in perm],'perm':perm,'mode':'mc','image':q.get('image') or '','think':think_seconds(q,'mc'),'messages':[{'role':'assistant','text':q['prompt']}],'attempts':0,'repair':False,'done':False,'busy':False,'practice':practice}
            p['hwNew']=False;save(); return snapshot(r,p)
        if path in ('/api/relay','/api/repair') and r.get('game'):raise GameError('In imposter mode, answer your assigned questions to advance the crew task bar.')
        if path=='/api/relay':
            records=p.setdefault('relayRecords',{})
            if d.get('action')=='start':
                if math.dist([p['x'],p['y']],(800,460))>125: raise GameError('Return to the 🚀 arrival pad to start a supply relay.')
                if p.get('relay'): return snapshot(r,p)
                route=int(d.get('route',len(records)%len(RELAY_ROUTES)))
                if not 0<=route<len(RELAY_ROUTES): raise GameError('Unknown relay route.')
                p['relay']={'route':route,'checkpoint':0,'started':time.time()}
            else:
                relay=p.get('relay')
                if not relay: return snapshot(r,p)
                route=RELAY_ROUTES[relay['route']]
                if int(d.get('checkpoint',-1))!=relay['checkpoint']: return snapshot(r,p)
                if p['active'] or math.dist([p['x'],p['y']],route['points'][relay['checkpoint']])>65: raise GameError('Reach the glowing 📦 checkpoint first.')
                relay['checkpoint']+=1
                if relay['checkpoint']==len(route['points']):
                    elapsed=round(time.time()-relay['started'],1); key=str(relay['route']); old=records.get(key)
                    records[key]=min(old,elapsed) if old is not None else elapsed
                    if old is None: p['cells']+=2
                    p['lastRelay']={'name':route['name'],'seconds':elapsed,'reward':0 if old is not None else 2}
                    p['relay']=None
            save(); return snapshot(r,p)
        if path=='/api/repair':
            station=int(d.get('topic',-1))
            if not 0<=station<len(r['pack']['topics']): raise GameError('Unknown station.')
            if math.dist([p['x'],p['y']],POSITIONS[station])>125: raise GameError('Move closer to this system.')
            if station in p['repairs']: return snapshot(r,p)
            if not any(x.startswith(f'{station}:') for x in p['completed']): raise GameError('Complete this station’s explanations first.')
            if p['cells']<2: raise GameError('Collect two floating energy cells first.')
            p['cells']-=2; p['repairs'].append(station)
            for mate in r['players'].values():
                if mate['id']!=p['id'] and mate['team']==p['team']: mate['cells']+=1
            if r['mode']=='race' and not r.get('winner'):
                shared={i for member in r['players'].values() if member['team']==p['team'] for i in member['repairs']}
                if len(shared)==len(r['pack']['topics']): r['winner']=p['team']
            save(); return snapshot(r,p)
        if path=='/api/cell':
            cell=int(d.get('cell',-1)); cells=cell_positions(); active=cell_pool(r)
            if cell not in range(len(cells)) or cell not in active: return {'ok':False}
            if math.dist([p['x'],p['y']],cells[cell])>50: return {'ok':False}
            active.remove(cell); r['cellPool']['respawn'].append(time.time()+CELL_RESPAWN)
            key='hints' if pickup_kind(cell)=='hint' else 'times'; p[key]=p.get(key,0)+1
            if p.get('stats') is not None: p['stats']['items']=p['stats'].get('items',0)+1
            save(); return {'ok':True,'cells':p['cells'],'hints':p.get('hints',0),'times':p.get('times',0),'kind':pickup_kind(cell)}
        if path=='/api/moretime':
            a=p['active']
            if not a or a['id']!=d.get('challenge') or a['done']: raise GameError('There is no open question to extend.')
            if not spend(p,'time'): raise GameError('More thinking time uses 1 ⏱️ token. Collect one on the map first.')
            save(); return snapshot(r,p)
        if path!='/api/chat': raise GameError('Unknown action.')
        a=p['active']; rid=str(d.get('requestId',''))[:80]
        if rid in p['cache']: return snapshot(r,p)
        if not a or a['id']!=d.get('challenge'): raise GameError('This challenge has changed. Refresh your view.')
        if a['done']: return snapshot(r,p)
        q=resolve_question(copy.deepcopy(r['pack']['topics'][a['topic']]['questions'][a['index']]),a.get('vi',0))
        perm=a.get('perm')
        if perm and len(perm)==len(q.get('choices') or []):  # choices were shuffled for this student
            q['correct']=perm.index(q['correct']);q['choices']=[q['choices'][i] for i in perm]
        answer_mode(r['pack'],q)
        picked=d.get('choice')
        if not isinstance(picked,int) or isinstance(picked,bool) or not 0<=picked<len(q['choices']): raise GameError('Pick an answer first.')
        ok=picked==q['correct'];chat_round=p.get('socialRound')
        text='My choice: '+'ABCDE'[picked]+') '+q['choices'][picked]
        log_chat(r,p,a,'student',text)
        feedback=('✅ Yes! '+q['answer'][:600]) if ok else ('Not quite. The answer was '+'ABCDE'[q['correct']]+') '+q['choices'][q['correct']]+'.\n'+q['answer'][:700])
        log_chat(r,p,a,'tutor',feedback[:3500])
        with LOCK:
            a['messages'].append({'role':'user','text':text})
            miss=not ok
            if ok:p['rightN']=p.get('rightN',0)+1
            if miss: a['attempts']+=1;a['repair']=True  # a miss shows the answer and earns nothing; the question comes back later
            points=0 if miss else 1
            a['points']=points;a['celebrate']=points>0
            qid=f"{a['topic']}:{a['index']}"
            if ok and qid not in p['completed'] and (not a.get('practice') or r.get('game')):
                p['completed'].append(qid); p['score']+=points; p['cells']+=0 if miss else 1
                p['history'].append({'question':qid,'points':points,'supported':miss,'topic':r['pack']['topics'][a['topic']]['name']})
            if ok and r.get('game') and chat_round==p.get('socialRound'):
                social.conversation_completed(r,p,qid);social.record_task(r,p,qid)
            a['done']=True
            if r.get('assignmentId') and p.get('email') and not miss:
                p['hwNew']=qid not in accounts.hw_credited(DB,p['email'],r['assignmentId']);accounts.hw_credit(DB,p['email'],r['assignmentId'],qid)
            a['messages'].append({'role':'assistant','text':feedback[:3500]})
            p['cache'][rid]=True
            if len(p['cache'])>120: p['cache'].pop(next(iter(p['cache'])))
            save(); return snapshot(r,p)

def cell_positions(): return [(130,450),(400,450),(630,430),(980,440),(1200,450),(1450,450),(100,920),(370,920),(650,810),(940,810),(1210,920),(1490,930),(750,550),(850,760),(680,1030),(920,1030),(250,560),(1350,560),(420,730),(1180,730),(760,120)]

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*a,**kw): super().__init__(*a,directory=str(ROOT/'public'),**kw)
    def log_message(self,*args): pass
    def end_headers(self):
        self.send_header('X-Content-Type-Options','nosniff'); self.send_header('Referrer-Policy','same-origin')
        self.send_header('Cache-Control','no-store'); super().end_headers()
    def do_GET(self):
        if self.path=='/api/config': self.respond(200,dispatch('/api/config',{}))
        else: super().do_GET()
    def respond(self,status,data):
        body=json.dumps(data).encode(); self.send_response(status); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_POST(self):
        try:
            origin=self.headers.get('Origin')
            if origin and origin.split('://',1)[-1]!=self.headers.get('Host'): raise GameError('Cross-site requests are not accepted.')
            n=int(self.headers.get('Content-Length','0'))
            if n>6_000_000: raise GameError('Request too large.')
            d=json.loads(self.rfile.read(n) or '{}')
            result=dispatch(self.path,d); self.respond(200,result)
        except GameError as e: self.respond(400,{'error':str(e)})
        except accounts.AuthError as e: self.respond(e.status,{'error':str(e)})
        except (ValueError,KeyError,TypeError,OverflowError): self.respond(400,{'error':'Invalid request. Check the supplied values.'})
        except Exception as e:
            print(type(e).__name__,str(e)[:200],flush=True); self.respond(500,{'error':'Something went wrong. Your saved progress remains available.'})

if __name__=='__main__':
    load(); port=int(os.environ.get('PORT','8000'))
    print(f'Imposter: http://localhost:{port}',flush=True)
    ThreadingHTTPServer(('0.0.0.0',port),Handler).serve_forever()
