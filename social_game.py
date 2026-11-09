"""Server-authoritative classroom social-deduction rounds.

Private roles, assignments and ballots never enter the public room payload.
"""
import math
import heapq
import secrets
import time

class SocialError(Exception):
    pass

KILL_COOLDOWN=20
KILL_PENALTY=2
MAX_EJECT=3
MAX_SUSPECTS=3
MAX_SHIELDS=2

def configure(room,options):
    room['game']={'phase':'lobby','round':0,'impostorCount':1,
                  'tasksPerCrew':max(1,min(7,int(options.get('tasksPerCrew',5)))),
                  'roundSeconds':(0 if not int(options.get('roundSeconds',0) or 0) else max(120,min(3600,int(options['roundSeconds'])))),'crewTargetPct':max(50,min(100,int(options.get('crewTargetPct',80)))),'roundEndsAt':0,
                  'meetingSeconds':(0 if int(options.get('meetingSeconds',240) or 0)==0 else max(60,min(900,int(options.get('meetingSeconds',240))))),
                  'briefingSeconds':max(10,min(120,int(options.get('briefingSeconds',60) or 60))),'briefingEndsAt':0,'impostorsEjected':0,
                  'interruptChats':bool(options.get('interruptChats',True)),
                  'discussionSeconds':max(15,min(180,int(options.get('discussionSeconds',30)))),
                  'voteSeconds':max(15,min(300,int(options.get('voteSeconds',30)))),
                  'questionsPerTag':1,
                  'writtenDiscussion':bool(options.get('writtenDiscussion',False)),'winner':None,'reason':'','meeting':None,'bodies':[],
                  'lastMeeting':None,'nextMeetingAt':0}

MIN_PLAYERS=4
TAGS_PER_CHAT=2
SAFE_AFTER_CHAT=4

def impostors_for(n):
    """Among Us style proportions: 1 impostor for small groups, 2 from 7 players, then about one per 3.5 players."""
    return max(1,int(n/3.5))

def park(player):
    if player.get('active'):
        player.setdefault('conversations',{})[str(player['active']['topic'])]=player['active']
        player['active']=None

def start(room):
    g=room['game'];n=len(room['players']);g['impostorCount']=impostors_for(n);needed=MIN_PLAYERS
    if g['phase'] not in ('lobby','ended'):raise SocialError('Finish the current round before starting another.')
    if n<needed:raise SocialError(f'Join at least {needed} players to start.')
    if room['paused'] or room.get('closed'):raise SocialError('Resume and reopen the room before starting.')
    impostors=set(secrets.SystemRandom().sample(list(room['players']),g['impostorCount']))
    preferred=room.get('soloRole') if room.get('botPractice') else None
    human=next((p['id'] for p in room['players'].values() if not p.get('bot')),None)
    if preferred=='impostor':impostors={human}
    elif preferred=='crew':impostors={secrets.choice([p['id'] for p in room['players'].values() if p.get('bot')])}
    now=time.time();g.update(impostorsEjected=0,briefingEndsAt=now+g['briefingSeconds'],startedAt=now,penalty=0,tagCount=0,meetingCount=0,summary=None,phase='briefing',round=g['round']+1,winner=None,reason='',meeting=None,bodies=[],lastMeeting=None,nextMeetingAt=0,roundEndsAt=0)
    for p in room['players'].values():
        park(p)
        p.update(role='impostor' if p['id'] in impostors else 'crew',alive=True,
                 roundTasks=[f'{i}:{secrets.randbelow(len(t["questions"]))}' for i,t in enumerate(room['pack']['topics'])],
                 roundDone=[],killReadyAt=now+KILL_COOLDOWN,socialRound=g['round'],conversations={},x=800,y=460,botPath=[],botTarget=None,botWaitingUntil=0,botSuspect=None,
                 briefReady=False,tagCharge=0,shield=0,notices=[],botChargeAt=0,stats={'tags':0,'answers':0,'distance':0.0,'goodVotes':0,'votes':0},safeUntil=0,blockedTopic=None,blockedUntil=0)
    return g

BOARDS=[('tags','🏷️ Most tags','tags'),('answers','🧠 Most questions answered','answers'),('distance','👟 Furthest traveled','steps'),('goodVotes','🕵️ Best detective (accurate votes)','correct votes'),('votes','🗳️ Most suspects flagged','votes')]

def summarize(room):
    g=room['game'];humans=[p for p in room['players'].values() if not p.get('bot') and p.get('stats')]
    boards=[]
    for key,title,unit in BOARDS:
        rows=[(p['name'],p['id'],p['stats'].get(key,0)) for p in humans]
        if key=='distance':rows=[(n,i,round(v/40)) for n,i,v in rows]
        rows=sorted([r for r in rows if r[2]>0],key=lambda r:-r[2])[:3]
        boards.append({'key':key,'title':title,'unit':unit,'entries':[{'id':i,'name':n,'value':v} for n,i,v in rows]})
    stats={p['id']:{**p['stats'],'distance':round(p['stats'].get('distance',0)/40)} for p in humans}
    return {'seconds':round(time.time()-g.get('startedAt',time.time())),'tags':g.get('tagCount',0),'meetings':g.get('meetingCount',0),'boards':boards,'stats':stats}

def finish(room,winner,reason):
    g=room['game'];g.update(phase='ended',winner=winner,reason=reason,meeting=None)
    try:g['summary']=summarize(room)
    except Exception:g['summary']=None

def target_for(room,total):
    return max(1,math.ceil(total*room['game'].get('crewTargetPct',80)/100))

def task_counts(room):
    crew=[p for p in room['players'].values() if p.get('role')=='crew']
    return max(0,sum(len(set(p.get('roundDone',[]))&set(p.get('roundTasks',[]))) for p in crew)-room['game'].get('penalty',0)),sum(len(p.get('roundTasks',[])) for p in crew)

def victory(room):
    g=room['game']
    if room.get('paused') or room.get('closed') or g['phase'] not in ('playing','meeting'):return
    done,total=task_counts(room)
    living=[p for p in room['players'].values() if p.get('alive',True)]
    impostors=sum(p.get('role')=='impostor' for p in living);crew=sum(p.get('role')=='crew' for p in living)
    if not impostors:finish(room,'crew','All impostors were voted out. 🛰️')
    elif impostors>=crew:finish(room,'impostors','Impostors reached parity with the living crew. ⚡')
    elif total and done>=target_for(room,total):finish(room,'crew','The crew reached its science target! 🧠')
    elif g.get('roundEndsAt') and time.time()>=g['roundEndsAt']:finish(room,'impostors','Time ran out before the crew reached its target. ⏱️')

def begin_play(room):
    """The role briefing is over: the round clock, tag cooldowns and meeting schedule start now."""
    g=room['game'];now=time.time()
    g.update(phase='playing',startedAt=now,nextMeetingAt=now+g['meetingSeconds'] if g['meetingSeconds'] else 0,roundEndsAt=now+g['roundSeconds'] if g['roundSeconds'] else 0)
    for p in room['players'].values():p['killReadyAt']=now+KILL_COOLDOWN

def shift_clocks(room,seconds):
    g=room['game']
    for k in ('nextMeetingAt','roundEndsAt','briefingEndsAt'):
        if g.get(k):g[k]+=seconds
    if g.get('meeting'):
        for k in ('started','voteOpensAt','endsAt'):g['meeting'][k]+=seconds
    for p in room['players'].values():
        if p.get('killReadyAt'):p['killReadyAt']+=seconds
        if p.get('botWaitingUntil'):p['botWaitingUntil']+=seconds

def resolve_meeting(room):
    g=room['game'];m=g['meeting'];living=[p for p in room['players'].values() if p.get('alive',True)]
    tally={}
    for voter in living:
        picks=m['votes'].get(voter['id'],[])
        for choice in picks:tally[choice]=tally.get(choice,0)+1
        if voter.get('stats') and voter.get('role')=='crew':
            good=sum(1 for c in picks if room['players'].get(c,{}).get('role')=='impostor')
            voter['stats']['votes']+=len(picks);voter['stats']['goodVotes']+=good-(len(picks)-good)
    needed=m['needed']
    ranked=sorted(((v,k) for k,v in tally.items() if v>=needed),reverse=True)
    ejected=[k for v,k in ranked]
    if len(ejected)>MAX_EJECT:
        cut=ranked[MAX_EJECT-1][0];above=[k for v,k in ranked if v>cut];tied=[k for v,k in ranked if v==cut]
        ejected=above+tied if len(above)+len(tied)<=MAX_EJECT else above  # a tie that would exceed the cap keeps everyone tied aboard
    for k in ejected:room['players'][k]['alive']=False
    names=[room['players'][k]['name'] for k in ejected]
    results=[{'name':room['players'][k]['name'],'wasImpostor':room['players'][k].get('role')=='impostor'} for k in ejected]
    g['impostorsEjected']=g.get('impostorsEjected',0)+sum(1 for x in results if x['wasImpostor'])
    left=max(0,g['impostorCount']-g['impostorsEjected'])
    said=' '.join(f'{x["name"]} {"WAS an impostor! 🕵️" if x["wasImpostor"] else "was NOT an impostor. 🧑‍🚀"}' for x in results)
    tail=f' {left} impostor{"" if left==1 else "s"} left.'
    g['lastMeeting']={'id':m['id'],'ejected':ejected,'names':names,'name':', '.join(names) or None,'tally':tally,'needed':needed,'results':results,'impostorsLeft':left,'at':time.time(),
                      'message':(f'{said}{tail} Voted-out players keep learning as ghosts. 👻') if names else f'Nobody reached {needed} votes, so nobody was voted out.{tail}'}
    if g.get('roundEndsAt'):g['roundEndsAt']+=time.time()-m['started']
    g.update(phase='playing',meeting=None,bodies=[],tagsSinceMeeting=0,nextMeetingAt=time.time()+g['meetingSeconds'] if g['meetingSeconds'] else 0)
    for p in room['players'].values():p.update(x=800,y=460,killReadyAt=time.time()+KILL_COOLDOWN,botPath=[],botTarget=None)
    victory(room)

def advance(room):
    g=room.get('game')
    if not g or room.get('paused') or room.get('closed'):return False
    now=time.time();changed=bot_tick(room)
    if room['paused']:return changed
    if g['phase']=='briefing':
        humans=[p for p in room['players'].values() if not p.get('bot')]
        if now>=g.get('briefingEndsAt',0) or (humans and all(p.get('briefReady') for p in humans)):begin_play(room);changed=True
    if g['phase']=='meeting':
        m=g['meeting'];living=[p for p in room['players'].values() if p.get('alive',True)]
        if now>=m['endsAt'] or all(p['id'] in m['votes'] for p in living):
            resolve_meeting(room);changed=True
    if g['phase']=='playing' and g.get('meetingSeconds') and now>=g.get('nextMeetingAt',0):
        if g.get('tagsSinceMeeting',0):
            n=g['tagsSinceMeeting'];meeting(room,None,f'Scheduled meeting. {n} crewmate{"s were" if n>1 else " was"} tagged since the last one. Share what you saw.')
        else:g['nextMeetingAt']=now+g['meetingSeconds']
        changed=True
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
        before=player.get('tagCharge',0);player['tagCharge']=min(6,before+TAGS_PER_CHAT)
        if before<need<=player['tagCharge']:notify(player,'⚡ Tags powered up! Find an isolated crewmate who is not in a chat.')
        return
    if set(player.get('roundTasks',[]))<=set(player.get('roundDone',[])) and player.get('shield',0)<MAX_SHIELDS:
        player['shield']=player.get('shield',0)+1
        notify(player,f'🛡️ Bonus chat complete! Shield ready ({player["shield"]}/{MAX_SHIELDS}). It blocks one tag attempt.')

def meeting(room,caller,reason):
    # Meetings never interrupt a conversation: players keep chatting and vote between chats.
    g=room['game'];now=time.time()
    living=[p for p in room['players'].values() if p.get('alive',True)]
    g['meeting']={'id':secrets.token_hex(8),'caller':'The station','needed':max(2,min(g['impostorCount']+1,len(living)//2+1)),'reason':reason,'started':now,
                  'voteOpensAt':now+g['discussionSeconds'],'endsAt':now+g['discussionSeconds']+g['voteSeconds'],'votes':{},'messages':[],'botSpoke':[]}
    g['phase']='meeting';g['meetingCount']=g.get('meetingCount',0)+1
    if g.get('interruptChats',True):
        # In-person style: everyone stops, chats are saved, and the class gathers at the pad to talk and vote together.
        for p in room['players'].values():
            if p.get('active'):p.setdefault('conversations',{})[str(p['active']['topic'])]=p['active'];p['active']=None
            p.update(x=800,y=460)

def action(room,player,data,walls):
    g=room['game']
    if not player.get('bot'):advance(room)
    kind=data.get('action');now=time.time()
    if room.get('paused') or room.get('closed'):raise SocialError('The teacher has paused or closed this room.')
    if kind=='ready':
        if g['phase']=='briefing':player['briefReady']=True;advance(room)
        return
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
        picks=data.get('targets',[data.get('target','skip')]) if isinstance(data.get('targets',[]),list) else []
        picks=list(dict.fromkeys(str(c) for c in picks if str(c)!='skip' and c))
        if len(picks)>MAX_SUSPECTS:raise SocialError(f'Pick at most {MAX_SUSPECTS} suspects.')
        if player['id'] in picks:raise SocialError('You cannot vote for yourself.')
        for choice in picks:
            if choice not in room['players'] or not room['players'][choice].get('alive',True):raise SocialError('Choose living players, or skip.')
        if player['id'] in m['votes']:return
        m['votes'][player['id']]=picks;advance(room);return
    if g['phase']!='playing':raise SocialError('The round starts when the role briefing ends.' if g['phase']=='briefing' else 'Wait for the teacher to start, or for this meeting to finish.')
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
        if target.get('active') or now<target.get('safeUntil',0) or now<target.get('botWaitingUntil',0):raise SocialError('That crewmate is in a chat or just left one. Wait for them to move.')
        player['tagCharge']=max(0,charge-need)
        if target.get('shield',0)>0:
            target['shield']-=1;player['killReadyAt']=now+KILL_COOLDOWN/2
            notify(target,'🛡️ Your shield blocked a tag attempt! Someone nearby is the impostor. Remember who was close.')
            notify(player,'🛡️ That crewmate had a shield. Your tag was blocked.')
            return
        for witness in room['players'].values():
            if witness.get('bot') and witness.get('alive',True) and witness['id'] not in (player['id'],target['id']) and near(witness,player,230,walls):witness['botSuspect']=player['id']
        player.get('stats',{})['tags']=player.get('stats',{}).get('tags',0)+1;g['tagCount']=g.get('tagCount',0)+1;g['tagsSinceMeeting']=g.get('tagsSinceMeeting',0)+1;g['penalty']=g.get('penalty',0)+KILL_PENALTY
        target['alive']=False;g['bodies'].append({'id':target['id'],'name':target['name'],'x':target['x'],'y':target['y']})
        player['killReadyAt']=now+KILL_COOLDOWN;victory(room)
    else:raise SocialError('Unknown round action.')

def next_question(room,player,topic):
    for qid in player.get('roundTasks',[]):
        if qid not in player.get('roundDone',[]) and int(qid.split(':')[0])==topic:return int(qid.split(':')[1])
    return None

def record_task(room,player,qid):
    if room.get('game',{}).get('phase') not in ('playing','meeting'):return
    if qid in player.get('roundTasks',[]) and qid not in player.setdefault('roundDone',[]):
        player['roundDone'].append(qid)
        if player.get('stats'):player['stats']['answers']+=1
    victory(room)

def public(room):
    g=room['game'];now=time.time();done,total=task_counts(room)
    result={k:g[k] for k in ('phase','round','impostorCount','tasksPerCrew','discussionSeconds','voteSeconds','winner','reason','bodies','lastMeeting','nextMeetingAt','meetingSeconds','interruptChats','briefingSeconds','briefingEndsAt','impostorsEjected','writtenDiscussion','questionsPerTag','roundSeconds','crewTargetPct','roundEndsAt')}
    result['summary']=g.get('summary') if g['phase']=='ended' else None;result['crewPenalty']=g.get('penalty',0);result['impostorsLeft']=max(0,g['impostorCount']-g.get('impostorsEjected',0));result['briefReady']=sum(1 for p in room['players'].values() if not p.get('bot') and p.get('briefReady'));result['briefHumans']=sum(1 for p in room['players'].values() if not p.get('bot'))
    result.update(botPractice=bool(room.get('botPractice')),serverNow=now,crewTasksDone=done,crewTasksTotal=total,crewTasksTarget=target_for(room,total) if total else 0,minimumPlayers=MIN_PLAYERS,impostorsIfStartedNow=impostors_for(len(room['players'])))
    m=g.get('meeting');result['meeting']=None
    if m:
        result['meeting']={k:m[k] for k in ('id','caller','reason','started','voteOpensAt','endsAt','needed')}
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
                choice=[suspect] if room['players'].get(suspect,{}).get('alive') else []
                if p.get('role')=='impostor':choice=[x['id'] for x in room['players'].values() if x.get('alive',True) and x.get('role')=='crew'][:1]
                m['votes'][p['id']]=choice;changed=True
            continue
        if g['phase']!='playing':continue
        if p.get('role')=='impostor' and p.get('alive',True):
            targets=[t for t in room['players'].values() if t.get('alive',True) and t.get('role')=='crew']
            if targets and now>=p.get('killReadyAt',0):
                if p.get('tagCharge',0)<g['questionsPerTag']:
                    # Bots "study" for a while to power up their tag, like a human impostor must.
                    if not p.get('botChargeAt'):p['botChargeAt']=now+15+secrets.randbelow(15)
                    elif now>=p['botChargeAt']:p['tagCharge']=p.get('tagCharge',0)+TAGS_PER_CHAT;p['botChargeAt']=0;changed=True
                else:
                    t=min(targets,key=lambda t:math.dist((p['x'],p['y']),(t['x'],t['y'])))
                    if near(p,t,85,BOT_WALLS):
                        action(room,p,{'action':'tag','target':t['id']},BOT_WALLS);changed=True
                    else:bot_walk(p,(t['x'],t['y']),dt)
                    if g['phase']!='playing':break
                    continue
            continue
        todo=[q for q in p.get('roundTasks',[]) if q not in p.get('roundDone',[])]
        if not todo:continue
        qid=todo[0];target=BOT_STATIONS[int(qid.split(':')[0])]
        if math.dist((p['x'],p['y']),target)<=85:
            if not p.get('botWaitingUntil'):p['botWaitingUntil']=now+18+secrets.randbelow(18)
            if now>=p['botWaitingUntil']:
                p.setdefault('roundDone',[]).append(qid);p['botWaitingUntil']=0;changed=True
        else:bot_walk(p,target,dt)
    return changed
