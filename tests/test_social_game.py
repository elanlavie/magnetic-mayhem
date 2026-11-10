import copy,json,math,sys,tempfile,time,unittest,uuid
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server as game
import social_game as social

class SocialTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.old=(game.DB,game.KEY,game.TEACHER_KEY);game.DB=self.temp.name+'/game.sqlite3';game.KEY='test-key';game.TEACHER_KEY='teacher-test';game.ROOMS.clear()
        self.host=game.dispatch('/api/create',{'mode':'infiltration','teacherKey':'teacher-test','impostors':1,'tasksPerCrew':2})
        self.room=game.ROOMS[self.host['code']];self.auth={}
        for name in ('A','B','C','D'):
            data=game.dispatch('/api/join',{'code':self.host['code'],'name':name});self.auth[data['player']['id']]={'code':self.host['code'],'token':data['token']}
        game.dispatch('/api/host',{**self.host,'action':'startRound'});self.room_=game.ROOMS[self.host['code']];self.assertEqual(self.room_['game']['phase'],'briefing');social.begin_play(self.room_)
        self.imp=next(p for p in self.room['players'].values() if p['role']=='impostor');self.crew=[p for p in self.room['players'].values() if p['role']=='crew'];self.g=self.room['game']
    def tearDown(self):game.DB,game.KEY,game.TEACHER_KEY=self.old;self.temp.cleanup()
    def act(self,p,action,**extra):return game.dispatch('/api/round',{**self.auth[p['id']],'action':action,**extra})
    def land(self):social.land_tags(self.room,True)
    def open_meeting(self):
        social.meeting(self.room,self.crew[0],'Test meeting');self.g['meeting']['voteOpensAt']=time.time()-1
        return self.g['meeting']['id']
    def test_role_assignments_and_task_counts(self):
        self.assertEqual(sum(p['role']=='impostor' for p in self.room['players'].values()),1)
        self.assertEqual(social.task_counts(self.room),(0,6));self.assertTrue(all(len(p['roundTasks'])==2 for p in self.room['players'].values()))
    def test_roles_and_ballots_are_private(self):
        snapshot=game.dispatch('/api/state',self.auth[self.crew[0]['id']]);self.assertNotIn('hostRoles',snapshot['room']);self.assertNotIn('partners',snapshot['player'])
        self.assertTrue(all('role' not in p and 'roundTasks' not in p and 'token' not in p for p in snapshot['room']['players']))
        self.assertNotIn('votes',json.dumps(snapshot['room']['game']))
        m=self.open_meeting();self.act(self.imp,'vote',meeting=m,target=self.crew[0]['id']);snap=game.dispatch('/api/state',self.auth[self.crew[1]['id']]);self.assertIsNone(snap['player']['yourVote']);self.assertNotIn('votes',snap['room']['game']['meeting'])
        self.assertEqual(snap['room']['game']['meeting']['voted'],[self.imp['id']])
    def test_crew_cannot_tag_and_sabotage_is_gone(self):
        for action in ('tag','sabotage','stabilize'):
            with self.assertRaises(game.GameError):self.act(self.crew[0],action,target=self.crew[1]['id'])
    def test_tag_cooldown_distance_and_wall_validation(self):
        with self.assertRaises(game.GameError):self.act(self.imp,'tag',target=self.crew[0]['id'])
        self.imp['killReadyAt']=0;self.imp['tagCharge']=2;self.crew[0].update(x=1300,y=240)
        with self.assertRaises(game.GameError):self.act(self.imp,'tag',target=self.crew[0]['id'])
        self.imp.update(x=650,y=310);self.crew[0].update(x=650,y=360)
        with self.assertRaises(game.GameError):self.act(self.imp,'tag',target=self.crew[0]['id'])
        self.imp.update(x=800,y=460,tagCharge=2);self.crew[0].update(x=830,y=460);self.act(self.imp,'tag',target=self.crew[0]['id']);self.assertTrue(self.crew[0]['alive']);self.land()
        self.assertFalse(self.crew[0]['alive']);self.assertEqual(len(self.g['bodies']),1)
        with self.assertRaises(game.GameError):self.act(self.imp,'tag',target=self.crew[1]['id'])
    def test_ghost_keeps_learning_but_cannot_intervene(self):
        ghost=self.crew[0];ghost['alive']=False
        for action in ('emergency','report','tag'):
            with self.assertRaises(game.GameError):self.act(ghost,action)
        qid=ghost['roundTasks'][0];i,j=map(int,qid.split(':'));ghost.update(x=game.POSITIONS[i][0],y=game.POSITIONS[i][1])
        a=game.dispatch('/api/start',{**self.auth[ghost['id']],'topic':i})['player']['active'];self.assertEqual(a['index'],j)
        with patch.object(game,'ai',return_value={'status':'correct','feedback':'Good Energy! ⚡'}):game.dispatch('/api/chat',{**self.auth[ghost['id']],'challenge':a['id'],'requestId':str(uuid.uuid4()),'text':'My explanation'})
        self.assertIn(qid,ghost['roundDone']);self.assertEqual(social.task_counts(self.room)[0],1)
    def test_impostor_chats_do_not_fill_crew_taskbar(self):
        before=social.task_counts(self.room);social.record_task(self.room,self.imp,self.imp['roundTasks'][0]);self.assertEqual(social.task_counts(self.room),before)
    def test_vote_unique_majority_ejects_impostor_and_crew_wins(self):
        meeting=self.open_meeting()
        for p in self.crew:self.act(p,'vote',meeting=meeting,target=self.imp['id'])
        self.act(self.imp,'vote',meeting=meeting,target='skip')
        self.assertEqual(self.g['winner'],'crew');self.assertFalse(self.imp['alive']);self.assertIn('revealedRoles',social.public(self.room))
        lm=self.g['lastMeeting'];self.assertEqual(lm['results'],[{'name':self.imp['name'],'wasImpostor':True}]);self.assertEqual(lm['impostorsLeft'],0);self.assertIn('WAS an impostor',lm['message']);self.assertEqual(social.public(self.room)['impostorsLeft'],0)
    def test_ties_and_missing_ballots_skip(self):
        meeting=self.open_meeting();self.act(self.imp,'vote',meeting=meeting,target=self.crew[0]['id']);self.act(self.crew[0],'vote',meeting=meeting,target=self.imp['id']);self.g['meeting']['endsAt']=time.time()-1
        game.dispatch('/api/state',self.auth[self.crew[1]['id']]);self.assertTrue(all(p['alive'] for p in self.room['players'].values()));self.assertEqual(self.g['lastMeeting']['ejected'],[])
    def test_duplicate_votes_do_not_count_twice_and_invalid_targets_fail(self):
        m=self.open_meeting()
        with self.assertRaises(game.GameError):self.act(self.crew[0],'vote',meeting=m,target='unknown')
        self.act(self.crew[0],'vote',meeting=m,target='skip');self.act(self.crew[0],'vote',meeting=m,target=self.imp['id']);self.assertEqual(self.g['meeting']['votes'][self.crew[0]['id']],[])
    def test_voting_is_open_immediately_and_defaults_are_30_and_30(self):
        social.meeting(self.room,self.crew[0],'Test meeting');m=self.g['meeting']
        self.assertEqual((self.g['discussionSeconds'],self.g['voteSeconds']),(30,30))
        self.act(self.crew[0],'vote',meeting=m['id'],target='skip');self.assertEqual(m['votes'][self.crew[0]['id']],[])  # no waiting for the discussion to end
        self.assertTrue(game.dispatch('/api/move',{**self.auth[self.crew[1]['id']],'x':810,'y':460})['ok'])  # meetings never freeze movement
    def test_no_emergency_or_report_and_scheduled_meeting_needs_a_tag(self):
        for action in ('emergency','report'):
            with self.assertRaises(game.GameError):self.act(self.crew[0],action,target='x')
        self.g['nextMeetingAt']=time.time()-1;game.dispatch('/api/state',self.auth[self.crew[0]['id']])
        self.assertEqual(self.g['phase'],'playing');self.assertGreater(self.g['nextMeetingAt'],time.time()+200)  # nobody tagged: skipped, timer restarts
        self.g['tagsSinceMeeting']=1;self.g['nextMeetingAt']=time.time()-1;game.dispatch('/api/state',self.auth[self.crew[0]['id']])
        self.assertEqual(self.g['phase'],'meeting')
    def test_meeting_interrupts_chats_by_default_and_saves_them(self):
        self.assertTrue(self.g['interruptChats'])
        p=self.crew[1];i=int(p['roundTasks'][0].split(':')[0]);p.update(x=game.POSITIONS[i][0],y=game.POSITIONS[i][1]);game.dispatch('/api/start',{**self.auth[p['id']],'topic':i});self.assertIsNotNone(p['active'])
        m=self.open_meeting();self.assertIsNone(p['active']);self.assertIn(str(i),p['conversations']);self.assertEqual((p['x'],p['y']),(800,460))
        with self.assertRaises(game.GameError):game.dispatch('/api/start',{**self.auth[p['id']],'topic':i})  # no new chats during a meeting
        self.act(p,'vote',meeting=m,target='skip')  # votes right away, no chat to finish
    def test_role_briefing_holds_the_round_clock_until_it_ends(self):
        h=game.dispatch('/api/create',{'mode':'infiltration','teacherKey':'teacher-test','impostors':1,'tasksPerCrew':2,'roundSeconds':600,'briefingSeconds':30});code=h['code'];ids=[]
        for n in 'ABCD':d=game.dispatch('/api/join',{'code':code,'name':n});ids.append({'code':code,'token':d['token']})
        game.dispatch('/api/host',{**h,'action':'startRound'});r=game.ROOMS[code];g=r['game']
        self.assertEqual(g['phase'],'briefing');self.assertEqual(g['roundEndsAt'],0);self.assertGreater(g['briefingEndsAt'],time.time()+20)
        with self.assertRaises(game.GameError):game.dispatch('/api/start',{**ids[0],'topic':0})  # no chats while reading roles
        self.assertTrue(all(p['role'] in ('crew','impostor') for p in r['players'].values()))  # roles already assigned for the briefing
        g['briefingEndsAt']=time.time()-1;game.dispatch('/api/state',ids[0])
        self.assertEqual(g['phase'],'playing');self.assertGreater(g['roundEndsAt'],time.time()+500)  # the 10-minute timer starts only now
    def test_wrongly_ejected_crew_is_revealed_as_not_an_impostor(self):
        m=self.open_meeting()
        for p in (self.imp,self.crew[1]):self.act(p,'vote',meeting=m,targets=[self.crew[0]['id']])
        self.g['meeting']['endsAt']=time.time()-1;game.dispatch('/api/state',self.auth[self.crew[1]['id']])
        lm=self.g['lastMeeting'];self.assertEqual(lm['results'],[{'name':self.crew[0]['name'],'wasImpostor':False}]);self.assertEqual(lm['impostorsLeft'],1);self.assertIn('NOT an impostor',lm['message']);self.assertIn('1 impostor left',lm['message'])
    def test_everyone_skipping_the_briefing_starts_the_round_early(self):
        h=game.dispatch('/api/create',{'mode':'infiltration','teacherKey':'teacher-test','impostors':1,'tasksPerCrew':2,'briefingSeconds':60});ids=[]
        for n in 'ABCD':d=game.dispatch('/api/join',{'code':h['code'],'name':n});ids.append({'code':h['code'],'token':d['token']})
        game.dispatch('/api/host',{**h,'action':'startRound'});r=game.ROOMS[h['code']];g=r['game']
        for a in ids[:3]:game.dispatch('/api/round',{**a,'action':'ready'})
        self.assertEqual(g['phase'],'briefing');self.assertEqual((social.public(r)['briefReady'],social.public(r)['briefHumans']),(3,4))
        game.dispatch('/api/round',{**ids[3],'action':'ready'});self.assertEqual(g['phase'],'playing')
    def test_bots_never_report_bodies_only_the_schedule_calls_meetings(self):
        h=game.dispatch('/api/create',{'mode':'impostorSolo','soloRole':'crew'});j=game.dispatch('/api/join',{'code':h['code'],'name':'Human'});r=game.ROOMS[h['code']];g=r['game'];social.begin_play(r)
        bot=next(p for p in r['players'].values() if p.get('bot') and p['role']=='crew')
        g['bodies'].append({'id':'x','name':'Ghost','x':bot['x'],'y':bot['y']})
        for _ in range(5):g['lastBotAt']=time.time()-1;social.advance(r)
        self.assertEqual(g['phase'],'playing');self.assertEqual(g['meetingCount'],0)
    def test_vote_threshold_uses_impostors_left(self):
        self.g['impostorCount']=3;self.g['impostorsEjected']=2
        social.meeting(self.room,None,'t');self.assertEqual(self.g['meeting']['needed'],2);self.assertEqual(self.g['meeting']['maxVotes'],1)
    def test_auto_tag_delay_shrinks_with_more_players(self):
        self.assertEqual([social.auto_tag_delay(n) for n in (3,4,6,8,10,14,30)],[30,30,22,15,11,8,8])
        self.assertTrue(all(social.auto_tag_delay(n)>=social.auto_tag_delay(n+1) for n in range(3,40)))
    def test_collecting_items_counts_for_leaderboard(self):
        p=self.crew[0];cell=game.cell_pool(self.room)[0];p['x'],p['y']=game.cell_positions()[cell]
        game.dispatch('/api/cell',{**self.auth[p['id']],'cell':cell})
        self.assertEqual(p['stats']['items'],1)
        summary=social.summarize(self.room);self.assertIn('items',[b['key'] for b in summary['boards']])
    def test_tag_delay_zero_is_instant(self):
        self.g['tagDelay']=0;self.imp.update(x=800,y=460,tagCharge=2,killReadyAt=0);self.crew[0].update(x=830,y=460)
        self.act(self.imp,'tag',target=self.crew[0]['id']);self.assertFalse(self.crew[0]['alive'])
    def test_tag_is_delayed_and_announced(self):
        self.imp.update(x=800,y=460,tagCharge=2,killReadyAt=0);self.crew[0].update(x=830,y=460)
        self.act(self.imp,'tag',target=self.crew[0]['id'])
        t=self.crew[0];self.assertTrue(t['alive']);self.assertEqual(self.g['penalty'],0);self.assertEqual(self.g['tagFeed'],[])
        delay=t['pendingTag']['at']-time.time();d=social.auto_tag_delay(sum(1 for x in self.room['players'].values() if x.get('alive',True)));self.assertTrue(.7*d-.5<=delay<=1.3*d)
        social.advance(self.room);self.assertTrue(t['alive'])  # not yet
        t['pendingTag']['at']=time.time()-1;social.advance(self.room)
        self.assertFalse(t['alive']);self.assertEqual(self.g['tagFeed'][-1]['name'],t['name']);self.assertEqual(self.g['penalty'],social.KILL_PENALTY)
    def test_meeting_frequency_is_a_teacher_option(self):
        self.assertEqual(self.g['meetingSeconds'],240)
        h=game.dispatch('/api/create',{'mode':'infiltration','teacherKey':'teacher-test','meetingSeconds':120});self.assertEqual(game.ROOMS[h['code']]['game']['meetingSeconds'],120)
        h=game.dispatch('/api/create',{'mode':'infiltration','teacherKey':'teacher-test','meetingSeconds':0});self.assertEqual(game.ROOMS[h['code']]['game']['meetingSeconds'],0)
    def test_multi_vote_threshold_and_limits(self):
        m=self.open_meeting();need=self.g['meeting']['needed'];self.assertEqual(need,2)
        self.assertEqual(self.g['meeting']['maxVotes'],self.g['impostorCount'])
        with self.assertRaises(game.GameError):self.act(self.crew[1],'vote',meeting=m,targets=[self.imp['id'],self.crew[2]['id']])  # only as many picks as impostors left
        self.g['meeting']['maxVotes']=3
        with self.assertRaises(game.GameError):self.act(self.crew[0],'vote',meeting=m,targets=[self.crew[0]['id']])  # not yourself
        with self.assertRaises(game.GameError):self.act(self.crew[0],'vote',meeting=m,targets=[x['id'] for x in self.room['players'].values()][:4])
        self.act(self.imp,'vote',meeting=m,targets=[self.crew[0]['id']])  # the impostor alone cannot reach the bar
        self.act(self.crew[1],'vote',meeting=m,targets=[self.imp['id'],self.crew[2]['id']]);self.act(self.crew[2],'vote',meeting=m,targets=[self.imp['id']])
        self.g['meeting']['endsAt']=time.time()-1;game.dispatch('/api/state',self.auth[self.crew[1]['id']])
        self.assertEqual(self.g['lastMeeting']['ejected'],[self.imp['id']]);self.assertTrue(self.crew[0]['alive'] and self.crew[2]['alive'])
    def test_at_most_three_ejected_and_ties_over_the_cap_stay(self):
        for i in range(6):self.room['players'][f'x{i}']={**self.crew[0],'id':f'x{i}','alive':True,'role':'crew','name':f'X{i}'}
        m=self.open_meeting();mt=self.g['meeting'];mt['needed']=2
        cands=['x0','x1','x2','x3']
        for n,v in enumerate([self.imp]+self.crew):mt['votes'][v['id']]=[c for k,c in enumerate(cands) if k!=n%4]
        mt['endsAt']=time.time()-1;game.dispatch('/api/state',self.auth[self.crew[1]['id']]);self.assertEqual(self.g['lastMeeting']['ejected'],[])  # four-way tie over the cap: everyone stays
    def test_top_three_ejected_when_clear(self):
        for i in range(6):self.room['players'][f'x{i}']={**self.crew[0],'id':f'x{i}','alive':True,'role':'crew','name':f'X{i}'}
        m=self.open_meeting();mt=self.g['meeting'];mt['needed']=2
        for v in list(self.room['players'].values())[:6]:mt['votes'][v['id']]=[x for x in ('x0','x1','x2') if x!=v['id']]
        for v in list(self.room['players'].values())[6:]:mt['votes'][v['id']]=['x0','x1','x3'] if v['id'] not in ('x0','x1','x3') else []
        mt['endsAt']=time.time()-1;game.dispatch('/api/state',self.auth[self.crew[1]['id']]);self.assertEqual(len(self.g['lastMeeting']['ejected']),3)
    def test_parity_wins_and_tagged_players_are_hidden(self):
        for victim in self.crew[:2]:self.imp['killReadyAt']=0;self.imp['tagCharge']=2;self.act(self.imp,'tag',target=victim['id']);self.land()
        self.assertEqual(self.g['winner'],'impostors')
        public=game.room_public(self.room);self.assertTrue(all(p['x'] is None for p in public['players'] if not p['alive']))
    def test_all_tasks_include_ghost_tasks_for_victory(self):
        self.crew[0]['alive']=False
        for p in self.crew:
            for qid in p['roundTasks']:social.record_task(self.room,p,qid)
        self.assertEqual(self.g['winner'],'crew')
    def test_async_meeting_does_not_interrupt_chat_and_vote_waits_for_chat_end(self):
        self.g['interruptChats']=False;p=self.crew[1];i=int(p['roundTasks'][0].split(':')[0]);p.update(x=game.POSITIONS[i][0],y=game.POSITIONS[i][1]);game.dispatch('/api/start',{**self.auth[p['id']],'topic':i})
        m=self.open_meeting();self.assertIsNotNone(p['active'])
        with self.assertRaises(game.GameError):self.act(p,'vote',meeting=m,target='skip')
        game.dispatch('/api/leave',self.auth[p['id']]);self.act(p,'vote',meeting=m,target='skip');self.assertEqual(self.g['meeting']['votes'][p['id']],[])
        game.dispatch('/api/host',{**self.host,'action':'pause'});self.g['pausedAt']-=20;old=self.g['meeting']['endsAt'];game.dispatch('/api/host',{**self.host,'action':'pause'});self.assertGreaterEqual(self.g['meeting']['endsAt'],old+19)
    def finish_chat(self,p,topic=None):
        """Complete one real conversation (Sonnet mocked) and return the question id."""
        p['blockedUntil']=0
        qid=next(q for q in p['roundTasks'] if q not in p.get('roundDone',[])) if topic is None else None
        i=int(qid.split(':')[0]) if qid else topic;p.update(x=game.POSITIONS[i][0],y=game.POSITIONS[i][1])
        a=game.dispatch('/api/start',{**self.auth[p['id']],'topic':i})['player']['active']
        with patch.object(game,'ai',return_value={'status':'correct','feedback':'Good Energy! ⚡'}):game.dispatch('/api/chat',{**self.auth[p['id']],'challenge':a['id'],'requestId':str(uuid.uuid4()),'text':'My explanation'})
        game.dispatch('/api/leave',self.auth[p['id']])  # closing the chat, as the UI does
        return f"{a['topic']}:{a['index']}"
    def test_impostor_must_finish_conversations_before_tagging(self):
        self.imp.update(killReadyAt=0,x=800,y=460);self.crew[0].update(x=830,y=460)
        with self.assertRaises(game.GameError):self.act(self.imp,'tag',target=self.crew[0]['id'])
        self.finish_chat(self.imp);self.assertEqual(self.imp['tagCharge'],2)  # one chat powers two tags
        self.imp.update(x=800,y=460);self.act(self.imp,'tag',target=self.crew[0]['id']);self.land();self.assertFalse(self.crew[0]['alive']);self.assertEqual(self.imp['tagCharge'],1)
    def test_extra_chat_after_tasks_earns_shield_that_blocks_one_tag(self):
        c=self.crew[0];c['roundDone']=list(c['roundTasks']);before=social.task_counts(self.room)
        self.finish_chat(c,topic=int(c['roundTasks'][0].split(':')[0]));self.assertEqual(c['shield'],1);self.assertEqual(social.task_counts(self.room),before)
        self.imp.update(killReadyAt=0,tagCharge=2,x=800,y=460);c.update(x=830,y=460,safeUntil=0)
        self.act(self.imp,'tag',target=c['id']);self.assertTrue(c['alive']);self.assertEqual(c['shield'],0);self.assertEqual(self.g['bodies'],[])
        self.assertTrue(any('shield' in n['text'].lower() for n in c['notices']));self.assertTrue(any('blocked' in n['text'].lower() for n in self.imp['notices']))
        self.assertEqual(self.imp['tagCharge'],1);self.assertTrue(self.imp['killReadyAt']>time.time())
        self.assertNotIn('notices',json.dumps(game.room_public(self.room)))
    def test_assigned_chats_give_no_shield_and_shields_cap_at_two(self):
        c=self.crew[0];self.finish_chat(c);self.assertEqual(c.get('shield',0),0)
        c['roundDone']=list(c['roundTasks'])
        for _ in range(4):self.finish_chat(c,topic=int(c['roundTasks'][0].split(':')[0]))
        self.assertEqual(c['shield'],2)
    def test_safe_zone_and_no_instant_reentry(self):
        c=self.crew[0];self.imp.update(killReadyAt=0,tagCharge=2,x=800,y=460);c.update(x=830,y=460)
        p=c;i=int(c['roundTasks'][0].split(':')[0]);p.update(x=game.POSITIONS[i][0],y=game.POSITIONS[i][1]);game.dispatch('/api/start',{**self.auth[p['id']],'topic':i})
        self.imp.update(x=p['x']+30,y=p['y'])
        with self.assertRaises(game.GameError):self.act(self.imp,'tag',target=p['id'])  # mid-chat is safe
        game.dispatch('/api/leave',self.auth[p['id']])
        with self.assertRaises(game.GameError):self.act(self.imp,'tag',target=p['id'])  # brief grace after leaving
        with self.assertRaises(game.GameError):game.dispatch('/api/start',{**self.auth[p['id']],'topic':i})  # cannot hop straight back in
        p['safeUntil']=0;self.act(self.imp,'tag',target=p['id']);self.land();self.assertFalse(p['alive'])
    def test_impostor_count_follows_among_us_ratio_and_target(self):
        self.assertEqual([social.impostors_for(n) for n in (4,7,8,10,12,30)],[1,2,2,2,3,8])
        total=social.task_counts(self.room)[1];self.assertEqual(social.target_for(self.room,10),8)
    def test_round_timer_gives_impostors_the_win_and_crew_target_wins(self):
        self.g['roundEndsAt']=time.time()-1;social.advance(self.room);self.assertEqual(self.g['winner'],'impostors')
    def test_crew_wins_at_target_share_including_ghosts(self):
        crew=[p for p in self.room['players'].values() if p.get('role')=='crew'];total=sum(len(p['roundTasks']) for p in crew)
        self.g['crewTargetPct']=50;need=social.target_for(self.room,total)
        crew[0]['alive']=False
        done=0
        for p in crew:
            for q in p['roundTasks']:
                if done<need:p.setdefault('roundDone',[]).append(q);done+=1
        social.victory(self.room);self.assertEqual(self.g['winner'],'crew')
    def test_tags_cost_progress_and_summary_has_leaderboards(self):
        crew=self.crew[0];self.imp.update(killReadyAt=0,tagCharge=2,x=800,y=460);crew.update(x=830,y=460,safeUntil=0)
        crew['roundDone']=list(crew['roundTasks'])[:2];before=social.task_counts(self.room)[0]
        self.act(self.imp,'tag',target=crew['id']);self.land();self.assertEqual(self.g['penalty'],social.KILL_PENALTY)
        self.assertLessEqual(social.task_counts(self.room)[0],before)
        social.finish(self.room,'impostors','test');s=self.g['summary']
        self.assertEqual(s['tags'],1);tags=next(b for b in s['boards'] if b['key']=='tags')
        self.assertEqual(tags['entries'][0]['id'],self.imp['id']);self.assertEqual(tags['entries'][0]['value'],1)
        self.assertIn(self.imp['id'],s['stats'])
    def test_written_discussion_is_teacher_option_with_rate_limit(self):
        m=self.open_meeting()
        with self.assertRaises(game.GameError):self.act(self.crew[0],'discuss',meeting=m,text='I saw something')
        self.g['writtenDiscussion']=True;self.act(self.crew[0],'discuss',meeting=m,text='<script>unsafe</script>')
        self.assertEqual(self.g['meeting']['messages'][0]['text'],'<script>unsafe</script>')
        with self.assertRaises(game.GameError):self.act(self.crew[0],'discuss',meeting=m,text='spam')
    def test_restart_preserves_round_roles_and_votes(self):
        m=self.open_meeting();self.act(self.crew[0],'vote',meeting=m,target='skip');roles={p['id']:p['role'] for p in self.room['players'].values()};game.ROOMS.clear();game.load();restored=game.ROOMS[self.host['code']]
        self.assertEqual(roles,{p['id']:p['role'] for p in restored['players'].values()});self.assertEqual(restored['game']['meeting']['votes'][self.crew[0]['id']],[])
    def test_late_join_rejected_and_teacher_view_is_authorized(self):
        with self.assertRaises(game.GameError):game.dispatch('/api/join',{'code':self.host['code'],'name':'Late'})
        with self.assertRaises(game.GameError):game.dispatch('/api/host',{'code':self.host['code'],'host':self.auth[self.crew[0]['id']]['token']})
        self.assertEqual(game.dispatch('/api/host',self.host)['room']['hostRoles'][self.imp['id']],'impostor')
    def test_minimum_players_and_lobby_lock(self):
        host=game.dispatch('/api/create',{'mode':'infiltration','teacherKey':'teacher-test','impostors':2});r=game.ROOMS[host['code']]
        self.assertEqual(r['game']['phase'],'lobby')
        with self.assertRaises(game.GameError):game.dispatch('/api/host',{**host,'action':'startRound'})
        j=game.dispatch('/api/join',{'code':host['code'],'name':'Waiting'})
        with self.assertRaises(game.GameError):game.dispatch('/api/start',{'code':host['code'],'token':j['token'],'topic':0})
    def test_solo_bots_are_explicit_and_role_choice_works(self):
        h=game.dispatch('/api/create',{'mode':'impostorSolo','soloRole':'impostor'});j=game.dispatch('/api/join',{'code':h['code'],'name':'Human'});r=game.ROOMS[h['code']]
        self.assertEqual(len(r['players']),6);self.assertEqual(j['player']['role'],'impostor');self.assertEqual(sum(bool(p.get('bot')) for p in r['players'].values()),5)
        self.assertTrue(j['room']['game']['botPractice']);self.assertTrue(j['room']['ai']);self.assertTrue(j['room']['game']['writtenDiscussion'])
        with self.assertRaises(game.GameError):game.dispatch('/api/join',{'code':h['code'],'name':'Another human'})
    def test_bot_paths_reach_every_station_without_crossing_walls(self):
        for target in game.POSITIONS:
            path=social.bot_path((800,460),target,game.WALLS);self.assertTrue(path)
            previous=(800,460)
            for point in path:self.assertTrue(social.visible_line(previous,point,game.WALLS));previous=point
            self.assertLess(math.dist(path[-1],target),20)
    def test_bot_movement_and_votes_use_observations(self):
        h=game.dispatch('/api/create',{'mode':'impostorSolo','soloRole':'crew'});j=game.dispatch('/api/join',{'code':h['code'],'name':'Human'});r=game.ROOMS[h['code']];g=r['game'];social.begin_play(r);g['lastBotAt']=time.time()-1
        before=[(p['x'],p['y']) for p in r['players'].values() if p.get('bot')];social.advance(r);after=[(p['x'],p['y']) for p in r['players'].values() if p.get('bot')];self.assertNotEqual(before,after)
        human=r['players'][j['player']['id']];social.meeting(r,human,'Test meeting');g['meeting']['voteOpensAt']=time.time()-3;g['lastBotAt']=time.time()-1;social.advance(r)
        for bot in r['players'].values():
            if bot.get('bot') and bot['role']=='crew':self.assertEqual(g['meeting']['votes'][bot['id']],[])

if __name__=='__main__':unittest.main()
