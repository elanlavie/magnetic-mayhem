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
        game.dispatch('/api/host',{**self.host,'action':'startRound'})
        self.imp=next(p for p in self.room['players'].values() if p['role']=='impostor');self.crew=[p for p in self.room['players'].values() if p['role']=='crew'];self.g=self.room['game']
    def tearDown(self):game.DB,game.KEY,game.TEACHER_KEY=self.old;self.temp.cleanup()
    def act(self,p,action,**extra):return game.dispatch('/api/round',{**self.auth[p['id']],'action':action,**extra})
    def open_meeting(self):
        self.g['nextMeetingAt']=0;self.act(self.crew[0],'emergency');self.g['meeting']['voteOpensAt']=time.time()-1
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
    def test_crew_cannot_tag_or_sabotage(self):
        for action in ('tag','sabotage'):
            with self.assertRaises(game.GameError):self.act(self.crew[0],action,target=self.crew[1]['id'])
    def test_tag_cooldown_distance_and_wall_validation(self):
        with self.assertRaises(game.GameError):self.act(self.imp,'tag',target=self.crew[0]['id'])
        self.imp['killReadyAt']=0;self.crew[0].update(x=1300,y=240)
        with self.assertRaises(game.GameError):self.act(self.imp,'tag',target=self.crew[0]['id'])
        self.imp.update(x=650,y=310);self.crew[0].update(x=650,y=360)
        with self.assertRaises(game.GameError):self.act(self.imp,'tag',target=self.crew[0]['id'])
        self.imp.update(x=800,y=460);self.crew[0].update(x=830,y=460);self.act(self.imp,'tag',target=self.crew[0]['id'])
        self.assertFalse(self.crew[0]['alive']);self.assertEqual(len(self.g['bodies']),1)
        with self.assertRaises(game.GameError):self.act(self.imp,'tag',target=self.crew[1]['id'])
    def test_ghost_keeps_learning_but_cannot_intervene(self):
        ghost=self.crew[0];ghost['alive']=False
        for action in ('emergency','report','sabotage','tag','stabilize'):
            with self.assertRaises(game.GameError):self.act(ghost,action)
        qid=ghost['roundTasks'][0];i,j=map(int,qid.split(':'));ghost.update(x=game.POSITIONS[i][0],y=game.POSITIONS[i][1])
        a=game.dispatch('/api/start',{**self.auth[ghost['id']],'topic':i})['player']['active'];self.assertEqual(a['index'],j)
        with patch.object(game,'ai',return_value={'status':'correct','feedback':'Good Energy! ⚡'}):game.dispatch('/api/chat',{**self.auth[ghost['id']],'challenge':a['id'],'requestId':str(uuid.uuid4()),'text':'My explanation'})
        self.assertIn(qid,ghost['roundDone']);self.assertEqual(social.task_counts(self.room)[0],1)
    def test_impostor_chats_do_not_fill_crew_taskbar(self):
        before=social.task_counts(self.room);social.record_task(self.room,self.imp,self.imp['roundTasks'][0]);self.assertEqual(social.task_counts(self.room),before)
    def test_vote_unique_majority_ejects_impostor_and_crew_wins(self):
        meeting=self.open_meeting()
        for p in self.room['players'].values():self.act(p,'vote',meeting=meeting,target=self.imp['id'])
        self.assertEqual(self.g['winner'],'crew');self.assertFalse(self.imp['alive']);self.assertIn('revealedRoles',social.public(self.room))
    def test_ties_and_missing_ballots_skip(self):
        meeting=self.open_meeting();self.act(self.imp,'vote',meeting=meeting,target=self.crew[0]['id']);self.act(self.crew[0],'vote',meeting=meeting,target=self.imp['id']);self.g['meeting']['endsAt']=time.time()-1
        game.dispatch('/api/state',self.auth[self.crew[1]['id']]);self.assertTrue(all(p['alive'] for p in self.room['players'].values()));self.assertIsNone(self.g['lastMeeting']['ejected'])
    def test_duplicate_votes_do_not_count_twice_and_invalid_targets_fail(self):
        m=self.open_meeting()
        with self.assertRaises(game.GameError):self.act(self.crew[0],'vote',meeting=m,target='unknown')
        self.act(self.crew[0],'vote',meeting=m,target='skip');self.act(self.crew[0],'vote',meeting=m,target=self.imp['id']);self.assertEqual(self.g['meeting']['votes'][self.crew[0]['id']],'skip')
    def test_meeting_discussion_timer_prevents_early_voting(self):
        self.g['nextMeetingAt']=0;self.act(self.crew[0],'emergency');m=self.g['meeting']
        with self.assertRaises(game.GameError):self.act(self.crew[0],'vote',meeting=m['id'],target='skip')
        with self.assertRaises(game.GameError):game.dispatch('/api/move',{**self.auth[self.crew[1]['id']],'x':810,'y':460})
    def test_sabotage_repair_and_expiry(self):
        self.g['nextSabotageAt']=0;self.act(self.imp,'sabotage')
        self.crew[0].update(x=800,y=650);self.act(self.crew[0],'stabilize',panel=0)
        self.assertEqual(self.g['sabotage']['fixed'],[0])
        self.crew[1].update(x=1340,y=650);self.act(self.crew[1],'stabilize',panel=1);self.assertIsNone(self.g['sabotage'])
        self.g['nextSabotageAt']=0;self.act(self.imp,'sabotage');self.g['sabotage']['deadline']=time.time()-1;game.dispatch('/api/state',self.auth[self.crew[0]['id']]);self.assertEqual(self.g['winner'],'impostors')
    def test_parity_wins_and_tagged_players_are_hidden(self):
        for victim in self.crew[:2]:self.imp['killReadyAt']=0;self.act(self.imp,'tag',target=victim['id'])
        self.assertEqual(self.g['winner'],'impostors')
        public=game.room_public(self.room);self.assertTrue(all(p['x'] is None for p in public['players'] if not p['alive']))
    def test_all_tasks_include_ghost_tasks_for_victory(self):
        self.crew[0]['alive']=False
        for p in self.crew:
            for qid in p['roundTasks']:social.record_task(self.room,p,qid)
        self.assertEqual(self.g['winner'],'crew')
    def test_meeting_parks_chat_and_pause_shifts_deadlines(self):
        p=self.crew[1];i=int(p['roundTasks'][0].split(':')[0]);p.update(x=game.POSITIONS[i][0],y=game.POSITIONS[i][1]);game.dispatch('/api/start',{**self.auth[p['id']],'topic':i})
        self.open_meeting();self.assertIsNone(p['active']);self.assertTrue(p['conversations'])
        game.dispatch('/api/host',{**self.host,'action':'pause'});self.g['pausedAt']-=20;old=self.g['meeting']['endsAt'];game.dispatch('/api/host',{**self.host,'action':'pause'});self.assertGreaterEqual(self.g['meeting']['endsAt'],old+19)
    def test_written_discussion_is_teacher_option_with_rate_limit(self):
        m=self.open_meeting()
        with self.assertRaises(game.GameError):self.act(self.crew[0],'discuss',meeting=m,text='I saw something')
        self.g['writtenDiscussion']=True;self.act(self.crew[0],'discuss',meeting=m,text='<script>unsafe</script>')
        self.assertEqual(self.g['meeting']['messages'][0]['text'],'<script>unsafe</script>')
        with self.assertRaises(game.GameError):self.act(self.crew[0],'discuss',meeting=m,text='spam')
    def test_restart_preserves_round_roles_and_votes(self):
        m=self.open_meeting();self.act(self.crew[0],'vote',meeting=m,target='skip');roles={p['id']:p['role'] for p in self.room['players'].values()};game.ROOMS.clear();game.load();restored=game.ROOMS[self.host['code']]
        self.assertEqual(roles,{p['id']:p['role'] for p in restored['players'].values()});self.assertEqual(restored['game']['meeting']['votes'][self.crew[0]['id']],'skip')
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
        h=game.dispatch('/api/create',{'mode':'impostorSolo','soloRole':'crew'});j=game.dispatch('/api/join',{'code':h['code'],'name':'Human'});r=game.ROOMS[h['code']];g=r['game'];g['lastBotAt']=time.time()-1
        before=[(p['x'],p['y']) for p in r['players'].values() if p.get('bot')];social.advance(r);after=[(p['x'],p['y']) for p in r['players'].values() if p.get('bot')];self.assertNotEqual(before,after)
        human=r['players'][j['player']['id']];social.meeting(r,human,'Test meeting');g['meeting']['voteOpensAt']=time.time()-3;g['lastBotAt']=time.time()-1;social.advance(r)
        for bot in r['players'].values():
            if bot.get('bot') and bot['role']=='crew':self.assertEqual(g['meeting']['votes'][bot['id']],'skip')

if __name__=='__main__':unittest.main()
