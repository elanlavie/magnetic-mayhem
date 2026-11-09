"""Server-authoritative classroom social-deduction rounds.

Private roles, assignments and ballots never enter the public room payload.
"""
import math
import heapq
import secrets
import time

class SocialError(Exception):
    pass

PANELS=[(800,650),(1340,650)]
KILL_COOLDOWN=30
SABOTAGE_COOLDOWN=60
SABOTAGE_DURATION=90
MEETING_COOLDOWN=30
MAX_SHIELDS=2

def configure(room,options):
    room['game']={'phase':'lobby','round':0,'impostorCount':max(1,min(3,int(options.get('impostors',1)))),
                  'tasksPerCrew':max(1,min(12,int(options.get('tasksPerCrew',5)))),
                  'discussionSeconds':max(15,min(180,int(options.get('discussionSeconds',30)))),
                  'voteSeconds':max(15,min(300,int(options.get('voteSeconds',90)))),
                  'questionsPerTag':max(1,min(5,int(options.get('questionsPerTag',2)))),
                  'writtenDiscussion':bool(options.get('writtenDiscussion',False)),'winner':None,'reason':'','meeting':None,'sabotage':None,'bodies':[],
                  'lastMeeting':None,'nextMeetingAt':0,'nextSabotageAt':0}

def park(player):
    if player.get('active'):
        player.setdefault('conversations',{})[str(player['active']['topic'])]=player['active']
        player['active']=None

def start(room):
    g=room['game'];n=len(room['players']);needed=g['impostorCount']*3+1
    if g['phase'] not in ('lobby','ended'):raise SocialError('Finish the current round before starting another.')
    if n<needed:raise SocialError(f'Join at least {needed} players for {g["impostorCount"]} impostor(s).')
    if room['paused'] or room.get('closed'):raise SocialError('Resume and reopen the room before starting.')
    all_tasks=[f'{i}:{j}' for i,t in enumerate(room['pack']['topics']) for j in range(len(t['questions']))]
    impostors=set(secrets.SystemRandom().sample(list(room['players']),g['impostorCount']))
    preferred=room.get('soloRole') if room.get('botPractice') else None
    human=next((p['id'] for p in room['players'].values() if not p.get('bot')),None)
    if preferred=='impostor':impostors={human}
    elif preferred=='crew':impostors={secrets.choice([p['id'] for p in room['players'].values() if p.get('bot')])}
    now=time.time();g.update(phase='playing',round=g['round']+1,winner=None,reason='',meeting=None,sabotage=None,bodies=[],lastMeeting=None,nextMeetingAt=now+MEETING_COOLDOWN,nextSabotageAt=now+20)
    for p in room['players'].values():
        park(p)
        p.update(role='impostor' if p['id'] in impostors else 'crew',alive=True,emergencies=1,
                 roundTasks=secrets.SystemRandom().sample(all_tasks,min(g['tasksPerCrew'],len(all_tasks))),
                 roundDone=[],killReadyAt=now+KILL_COOLDOWN,socialRound=g['round'],conversations={},x=800,y=460,botPath=[],botTarget=None,botWaitingUntil=0,botSuspect=None,
                 tagCharge=0,shield=0,notices=[],botChargeAt=0)
    return g

def finish(room,winner,reason):
    g=room['game'];g.update(phase='ended',winner=winner,reason=reason,meeting=None,sabotage=None)

def task_counts(room):
    crew=[p for p in room['players'].values() if p.get('role')=='crew']
    return sum(len(set(p.get('roundDone',[]))&set(p.get('roundTasks',[]))) for p in crew),sum(len(p.get('roundTasks',[])) for p in crew)

def victory(room):
    g=room['game']
    if room.get('paused') or room.get('closed') or g['phase'] not in ('playing','meeting'):return
    done,total=task_counts(room)
    living=[p for p in room['players'].values() if p.get('alive',True)]
    impostors=sum(p.get('role')=='impostor' for p in living);crew=sum(p.get('role')=='crew' for p in living)
    if not impostors:finish(room,'crew','All impostors were voted out. 🛰️')
    elif impostors>=crew:finish(room,'impostors','Impostors reached parity with the living crew. ⚡')
    elif total and done>=total:finish(room,'crew','The crew completed every assigned science conversation! 🧠')

def shift_clocks(room,seconds):
    g=room['game']
    for k in ('nextMeetingAt','nextSabotageAt'):
        if g.get(k):g[k]+=seconds
    if g.get('sabotage'):g['sabotage']['deadline']+=seconds
    if g.get('meeting'):
        for k in ('started','voteOpensAt','endsAt'):g['meeting'][k]+=seconds
    for p in room['players'].values():
        if p.get('killReadyAt'):p['killReadyAt']+=seconds
        if p.get('botWaitingUntil'):p['botWaitingUntil']+=seconds

def resolve_meeting(room):
    g=room['game'];m=g['meeting'];living=[p for p in room['players'].values() if p.get('alive',True)]
    tally={}
    for voter in living:
        choice=m['votes'].get(voter['id'],'skip');tally[choice]=tally.get(choice,0)+1
    top=max(tally.values(),default=0);leaders=[k for k,v in tally.items() if v==top]
    ejected=leaders[0] if len(leaders)==1 and leaders[0]!='skip' else None
    if ejected:room['players'][ejected]['alive']=False
    name=room['players'][ejected]['name'] if ejected else None
    g['lastMeeting']={'id':m['id'],'ejected':ejected,'name':name,'tally':tally,
                      'message':f'{name} was voted out and can keep learning as a ghost. 👻' if ejected else 'No one was voted out. Ties and skip votes keep everyone aboard. 🛰️'}
    if g.get('sabotage'):g['sabotage']['deadline']+=time.time()-m['started']
    g.update(phase='playing',meeting=None,bodies=[],nextMeetingAt=time.time()+MEETING_COOLDOWN)
    for p in room['players'].values():p.update(x=800,y=460,killReadyAt=time.time()+KILL_COOLDOWN,botPath=[],botTarget=None)
    victory(room)

def advance(room):
    g=room.get('game')
    if not g or room.get('paused') or room.get('closed'):return False
    now=time.time();changed=bot_tick(room)
    if room['paused']:return changed
    if g['phase']=='meeting':
        m=g['meeting'];living=[p for p in room['players'].values() if p.get('alive',True)]
        if now>=m['endsAt'] or (now>=m['voteOpensAt'] and all(p['id'] in m['votes'] for p in living)):
            resolve_meeting(room);changed=True
    if g['phase']=='playing' and g.get('sabotage') and now>=g['sabotage']['deadline']:
        finish(room,'impostors','The reactor overload was not stabilized in time. ⚠️');changed=True
    before=g['phase'];victory(room)
    return changed or before!=g['phase']

def visible_line(a,b,walls):
    # Segment/rectangle intersection prevents tagging and reporting through walls.
    ax,ay=a;bx,by=b
    for x,y,w,h in walls:
        low,high=0.,1.
        for origin,delta,minimum,maximum in ((ax,bx-ax,x,x+w),(ay,by-ay,y,y+h)):
            if abs(delta)<1e-8:
                if not minimum<=origin<=maximum:low,high=1.,0.;break
            else:
                u,v=(minimum-origin)/delta,(maximum-origin)/delta
                low=max(low,min(u,v));high=min(high,max(u,v))
        if low<=high:return False
    return True

def near(a,b,radius,walls):
    return math.dist((a['x'],a['y']),(b['x'],b['y']))<=radius and visible_line((a['x'],a['y']),(b['x'],b['y']),walls)

def notify(player,text):
    notes=player.setdefault('notices',[]);notes.append({'id':secrets.token_hex(4),'text':text});del notes[:-5]

def conversation_completed(room,player,qid):
    """Reward a correct conversation. Call BEFORE record_task so we can tell extra chats from assigned ones."""
    g=room.get('game')
    if not g or g['phase'] not in ('playing','meeting') or not player.get('alive',True):return
    need=g['questionsPerTag']
    if player.get('role')=='impostor':
        before=player.get('tagCharge',0);player['tagCharge']=min(5,before+1)
        if before<need<=player['tagCharge']:notify(player,'⚡ Tag powered up! Find an isolated crewmate.')
        return
    if set(player.get('roundTasks',[]))<=set(player.get('roundDone',[])) and player.get('shield',0)<MAX_SHIELDS:
        player['shield']=player.get('shield',0)+1
        notify(player,f'🛡️ Bonus chat complete! Shield ready ({player["shield"]}/{MAX_SHIELDS}). It blocks one tag attempt.')

def meeting(room,caller,reason):
    # Meetings never interrupt a conversation: players keep chatting and vote between chats.
    g=room['game'];now=time.time()
    g['meeting']={'id':secrets.token_hex(8),'caller':caller['name'],'reason':reason,'started':now,
                  'voteOpensAt':now+g['discussionSeconds'],'endsAt':now+g['discussionSeconds']+g['voteSeconds'],'votes':{},'messages':[],'botSpoke':[]}
    g['phase']='meeting'

def action(room,player,data,walls):
    g=room['game']
    if not player.get('bot'):advance(room)
    kind=data.get('action');now=time.time()
    if room.get('paused') or room.get('closed'):raise SocialError('The teacher has paused or closed this room.')
    if kind=='discuss':
        if g['phase']!='meeting' or data.get('meeting')!=g['meeting']['id']:raise SocialError('This meeting has ended.')
        if not g.get('writtenDiscussion'):raise SocialError('This meeting uses spoken classroom discussion.')
        if not player.get('alive',True):raise SocialError('Ghosts can observe, but cannot contribute to the living crew discussion.')
        if now-player.get('lastDiscussionAt',0)<2:raise SocialError('Give others a moment to respond.')
        text=str(data.get('text','')).strip()[:400]
        if not text:raise SocialError('Write a message first.')
        m=g['meeting'];m['messages'].append({'name':player['name'],'text':text});m['messages']=m['messages'][-60:];player['lastDiscussionAt']=now;return
    if kind=='vote':
        if g['phase']!='meeting' or data.get('meeting')!=g['meeting']['id']:raise SocialError('This meeting has ended.')
        m=g['meeting']
        if not player.get('alive',True):raise SocialError('Ghosts can observe meetings, but cannot vote.')
        if player.get('active'):raise SocialError('Finish or leave your current chat, then cast your vote. Your chat is saved.')
        if now<m['voteOpensAt']:raise SocialError('Discuss what you saw first. Voting opens shortly.')
        choice=str(data.get('target','skip'))
        if choice!='skip' and (choice not in room['players'] or not room['players'][choice].get('alive',True)):raise SocialError('Choose a living player or Skip.')
        if player['id'] in m['votes']:return
        m['votes'][player['id']]=choice;advance(room);return
    if g['phase']!='playing':raise SocialError('Wait for the teacher to start, or for this meeting to finish.')
    if not player.get('alive',True):raise SocialError('You are a ghost. Your science tasks still help the crew; game interventions are disabled.')
    if kind=='tag':
        if player.get('role')!='impostor':raise SocialError('Only impostors can tag players out.')
        if player.get('active'):raise SocialError('Leave your conversation before tagging someone.')
        if now<player.get('killReadyAt',0):raise SocialError('Your tag cooldown is still running.')
        need=g['questionsPerTag'];charge=player.get('tagCharge',0)
        if charge<need:raise SocialError(f'Power up your tag: finish {need-charge} more science conversation(s) first.')
        target=room['players'].get(str(data.get('target','')))
        if not target or target['id']==player['id'] or not target.get('alive',True) or target.get('role')!='crew':raise SocialError('Choose a nearby living crewmate.')
        if not near(player,target,85,walls):raise SocialError('Get closer with a clear path to tag this crewmate.')
        player['tagCharge']=max(0,charge-need)
        if target.get('shield',0)>0:
            target['shield']-=1;player['killReadyAt']=now+KILL_COOLDOWN/2
            notify(target,'🛡️ Your shield blocked a tag attempt! Someone nearby is the impostor. Remember who was close.')
            notify(player,'🛡️ That crewmate had a shield. Your tag was blocked.')
            return
        for witness in room['players'].values():
            if witness.get('bot') and witness.get('alive',True) and witness['id'] not in (player['id'],target['id']) and near(witness,player,230,walls):witness['botSuspect']=player['id']
        target['alive']=False;g['bodies'].append({'id':target['id'],'name':target['name'],'x':target['x'],'y':target['y']})
        player['killReadyAt']=now+KILL_COOLDOWN;victory(room)
    elif kind=='report':
        body=next((b for b in g['bodies'] if b['id']==data.get('target')),None)
        if not body or not near(player,body,115,walls):raise SocialError('Move near a downed explorer to report them.')
        meeting(room,player,f'{player["name"]} reported {body["name"]}. Share what you saw.')
    elif kind=='emergency':
        if g.get('sabotage'):raise SocialError('Stabilize the reactor before calling an emergency meeting. Reports still work.')
        if now<g['nextMeetingAt']:raise SocialError('Emergency meetings are on cooldown.')
        if not player.get('emergencies',0):raise SocialError('You already used your emergency meeting this round.')
        if math.dist((player['x'],player['y']),(800,460))>125:raise SocialError('Return to the arrival pad to call an emergency meeting.')
        player['emergencies']-=1;meeting(room,player,'Emergency meeting. Discuss observations, then vote privately.')
    elif kind=='sabotage':
        if player.get('role')!='impostor':raise SocialError('Only impostors can sabotage the station.')
        if g.get('sabotage') or now<g['nextSabotageAt']:raise SocialError('Sabotage is on cooldown.')
        g['sabotage']={'deadline':now+SABOTAGE_DURATION,'fixed':[]};g['nextSabotageAt']=now+SABOTAGE_DURATION+SABOTAGE_COOLDOWN
    elif kind=='stabilize':
        sabotage=g.get('sabotage');panel=int(data.get('panel',-1))
        if not sabotage or panel not in range(len(PANELS)):raise SocialError('No reactor panel needs attention.')
        if math.dist((player['x'],player['y']),PANELS[panel])>125:raise SocialError('Move closer to the glowing reactor panel.')
        if panel not in sabotage['fixed']:sabotage['fixed'].append(panel)
        if len(sabotage['fixed'])==len(PANELS):g['sabotage']=None;g['nextSabotageAt']=now+SABOTAGE_COOLDOWN
    else:raise SocialError('Unknown round action.')

def next_question(room,player,topic):
    for qid in player.get('roundTasks',[]):
        if qid not in player.get('roundDone',[]) and int(qid.split(':')[0])==topic:return int(qid.split(':')[1])
    return None

def record_task(room,player,qid):
    if room.get('game',{}).get('phase') not in ('playing','meeting'):return
    if qid in player.get('roundTasks',[]) and qid not in player.setdefault('roundDone',[]):player['roundDone'].append(qid)
    victory(room)

def public(room):
    g=room['game'];now=time.time();done,total=task_counts(room)
    result={k:g[k] for k in ('phase','round','impostorCount','tasksPerCrew','discussionSeconds','voteSeconds','winner','reason','bodies','lastMeeting','nextMeetingAt','nextSabotageAt','writtenDiscussion','questionsPerTag')}
    result.update(botPractice=bool(room.get('botPractice')),serverNow=now,crewTasksDone=done,crewTasksTotal=total,minimumPlayers=g['impostorCount']*3+1)
    result['sabotage']=g['sabotage']
    m=g.get('meeting');result['meeting']=None
    if m:
        result['meeting']={k:m[k] for k in ('id','caller','reason','started','voteOpensAt','endsAt')}
        result['meeting']['voted']=list(m['votes'])
        result['meeting']['messages']=m.get('messages',[])
    if g['phase']=='ended':result['revealedRoles']={p['id']:p.get('role') for p in room['players'].values()}
    return result

def private(room,player):
    if not room.get('game'):return {}
    g=room['game'];m=g.get('meeting');extra={'yourVote':m['votes'].get(player['id']) if m else None,'notices':player.get('notices',[]),'tagCharge':player.get('tagCharge',0),'shield':player.get('shield',0)}
    if player.get('role')=='impostor':extra['partners']=[{'id':p['id'],'name':p['name']} for p in room['players'].values() if p.get('role')=='impostor' and p['id']!=player['id']]
    return extra

# Computer-controlled practice players. These simulate game participation, never
# student assessment or the Sonnet tutor. Only observations inform their votes.
BOT_WALLS=[]
BOT_STATIONS=[]

def bot_path(start,end,walls):
    step=20
    def free(n):
        x,y=n[0]*step,n[1]*step
        return 25<=x<=1575 and 25<=y<=1125 and not any(a-15<x<a+w+15 and b-15<y<b+h+15 for a,b,w,h in walls)
    source=(round(start[0]/step),round(start[1]/step));dest=(round(end[0]/step),round(end[1]/step))
    if not free(dest) or not free(source):return []
    queue=[(0,source)];cost={source:0};parent={}
    while queue:
        _,node=heapq.heappop(queue)
        if node==dest:
            out=[]
            while node!=source:out.append((node[0]*step,node[1]*step));node=parent[node]
            return list(reversed(out))
        for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)):
            nxt=node[0]+dx,node[1]+dy;new=cost[node]+1
            if free(nxt) and new<cost.get(nxt,10**9):
                cost[nxt]=new;parent[nxt]=node;heapq.heappush(queue,(new+abs(nxt[0]-dest[0])+abs(nxt[1]-dest[1]),nxt))
    return []

def bot_walk(p,target,dt):
    marker=(round(target[0]/20)*20,round(target[1]/20)*20)
    if p.get('botTarget')!=list(marker) or not p.get('botPath'):
        p['botPath']=bot_path((p['x'],p['y']),marker,BOT_WALLS);p['botTarget']=list(marker)
    budget=135*dt
    while p['botPath'] and budget>0:
        x,y=p['botPath'][0];dist=math.dist((p['x'],p['y']),(x,y))
        if dist<=budget:p['x'],p['y']=x,y;p['botPath'].pop(0);budget-=dist
        else:p['x']+=(x-p['x'])/dist*budget;p['y']+=(y-p['y'])/dist*budget;break

def bot_tick(room):
    if not room.get('botPractice') or room.get('paused'):return False
    g=room['game'];now=time.time();last=g.get('lastBotAt',now-.5)
    if now-last<.3:return False
    g['lastBotAt']=now;dt=min(1,now-last);changed=False
    for p in list(room['players'].values()):
        if not p.get('bot'):continue
        p['last']=now
        if g['phase']=='meeting':
            if not p.get('alive',True):continue
            m=g['meeting'];suspect=p.get('botSuspect')
            if p['id'] not in m.get('botSpoke',[]):
                candidate=room['players'].get(suspect,{})
                message=f'I saw {candidate["name"]} near the tag. What did you see?' if candidate.get('alive') else 'I did not see a tag clearly. I will skip unless someone has evidence.'
                if p.get('role')=='impostor':message='I was moving between stations. Did anyone see the tag?'
                m.setdefault('messages',[]).append({'name':p['name'],'text':message});m.setdefault('botSpoke',[]).append(p['id']);changed=True
            if now>=m['voteOpensAt']+2 and p['id'] not in m['votes']:
                choice=suspect if room['players'].get(suspect,{}).get('alive') else 'skip'
                if p.get('role')=='impostor':choice=next((x['id'] for x in room['players'].values() if x.get('alive',True) and x.get('role')=='crew'),'skip')
                m['votes'][p['id']]=choice;changed=True
            continue
        if g['phase']!='playing':continue
        if p.get('role')=='impostor' and p.get('alive',True):
            targets=[t for t in room['players'].values() if t.get('alive',True) and t.get('role')=='crew']
            if targets and now>=p.get('killReadyAt',0):
                if p.get('tagCharge',0)<g['questionsPerTag']:
                    # Bots "study" for a while to power up their tag, like a human impostor must.
                    if not p.get('botChargeAt'):p['botChargeAt']=now+15+secrets.randbelow(15)
                    elif now>=p['botChargeAt']:p['tagCharge']=p.get('tagCharge',0)+1;p['botChargeAt']=0;changed=True
                else:
                    t=min(targets,key=lambda t:math.dist((p['x'],p['y']),(t['x'],t['y'])))
                    if near(p,t,85,BOT_WALLS):
                        action(room,p,{'action':'tag','target':t['id']},BOT_WALLS);changed=True
                    else:bot_walk(p,(t['x'],t['y']),dt)
                    if g['phase']!='playing':break
                    continue
            if now>=g.get('nextSabotageAt',0) and not g.get('sabotage'):
                action(room,p,{'action':'sabotage'},BOT_WALLS);changed=True
        if g.get('sabotage') and p.get('alive',True) and p.get('role')!='impostor':
            remaining=[i for i in range(len(PANELS)) if i not in g['sabotage']['fixed']]
            if remaining:
                i=min(remaining,key=lambda i:math.dist((p['x'],p['y']),PANELS[i]))
                if math.dist((p['x'],p['y']),PANELS[i])<=100:action(room,p,{'action':'stabilize','panel':i},BOT_WALLS);changed=True
                else:bot_walk(p,PANELS[i],dt)
            continue
        bodies=[b for b in g.get('bodies',[]) if p.get('alive',True) and p.get('role')=='crew' and near(p,b,115,BOT_WALLS)]
        if bodies:meeting(room,p,f'{p["name"]} reported {bodies[0]["name"]}. Discuss the evidence.');changed=True;break
        todo=[q for q in p.get('roundTasks',[]) if q not in p.get('roundDone',[])]
        if not todo:continue
        qid=todo[0];target=BOT_STATIONS[int(qid.split(':')[0])]
        if math.dist((p['x'],p['y']),target)<=85:
            if not p.get('botWaitingUntil'):p['botWaitingUntil']=now+18+secrets.randbelow(18)
            if now>=p['botWaitingUntil']:
                p.setdefault('roundDone',[]).append(qid);p['botWaitingUntil']=0;changed=True
        else:bot_walk(p,target,dt)
    return changed
