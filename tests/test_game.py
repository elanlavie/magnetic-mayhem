import io
import sys, tempfile, unittest, copy, json, threading, uuid
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server as game

class GameTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); game.DB=self.temp.name+'/test.sqlite'; game.ROOMS.clear(); self.oldkey=game.KEY; self.oldteacher=game.TEACHER_KEY; game.KEY='test-key'; game.TEACHER_KEY='teacher-test'
        self.real_ai=game.ai
        self.ai_patch=patch.object(game,'ai',side_effect=self.fake_ai);self.ai_patch.start()
        self.created=game.dispatch('/api/create',{'mode':'coop','pack':copy.deepcopy(game.BUILTIN),'teacherKey':'teacher-test'})
        self.auth={'code':self.created['code']}
        j=game.dispatch('/api/join',{**self.auth,'name':'Ada'}); self.auth['token']=j['token']; self.p=game.ROOMS[self.auth['code']]['players'][j['player']['id']]; self.p['cells']=0  # tests count cells from zero; real players start with 2
    def tearDown(self): self.ai_patch.stop(); game.KEY=self.oldkey; game.TEACHER_KEY=self.oldteacher; self.temp.cleanup()
    @staticmethod
    def fake_ai(system,data,max_tokens=650):
        if data.get('request_type') in ('hint','solution'): return {'status':'help','feedback':'💡 Test hint.'}
        text=data.get('student','')
        if text==data['question']['answer']: return {'status':'correct','feedback':'⚡ Test explanation accepted.'}
        return {'status':'incorrect' if 'unicorn' in text else 'help','feedback':'💬 Test follow-up.'}
    def start(self,topic=0):
        self.p['x'],self.p['y']=game.POSITIONS[topic]
        return game.dispatch('/api/start',{**self.auth,'topic':topic})['player']['active']
    def chat(self,text='',kind='answer',rid=None):
        if kind=='hint' and not self.p['cells']:self.p['cells']=1  # a hint spends one ⚡ cell
        return game.dispatch('/api/chat',{**self.auth,'challenge':self.p['active']['id'],'requestId':rid or str(uuid.uuid4()),'kind':kind,'text':text})
    def mc_player(self,fmt):
        q=lambda i:{'prompt':'Which is right %d?'%i,'answer':'Because B is right.','hint':'think','choices':['A one','B two','C three','D four'],'correct':1}
        pack={'title':'MC','format':fmt,'topics':[{'name':'T%d'%i,'icon':'🧲','questions':[q(i)]} for i in range(2)]}
        c=game.dispatch('/api/create',{'mode':'coop','pack':pack,'teacherKey':'teacher-test'})
        auth={'code':c['code']};j=game.dispatch('/api/join',{**auth,'name':'Mo'});auth['token']=j['token']
        p=game.ROOMS[c['code']]['players'][j['player']['id']];p['x'],p['y']=game.POSITIONS[0]
        a=game.dispatch('/api/start',{**auth,'topic':0})['player']['active']
        return auth,p,a
    def mc_chat(self,auth,p,choice=None,text=''):
        d={**auth,'challenge':p['active']['id'],'requestId':str(uuid.uuid4()),'kind':'answer','text':text}
        if choice is not None:d['choice']=choice
        return game.dispatch('/api/chat',d)
    def test_pack_format_defaults_and_choice_cleaning(self):
        self.assertEqual(game.clean_format(None),{'mc':False,'free':True});self.assertEqual(game.clean_format({'mc':False,'free':False}),{'mc':False,'free':True});self.assertEqual(game.clean_format({'mc':True,'free':False}),{'mc':True,'free':False})
        base=lambda fmt:{'title':'x','format':fmt,'topics':[{'name':'t','questions':[{'prompt':'p','answer':'a','hint':'h','choices':['a','b','c'],'correct':1},{'prompt':'p','answer':'a','hint':'h','choices':['a'],'correct':5}]}]}
        free=game.validate_pack(base(None));self.assertNotIn('choices',free['topics'][0]['questions'][0])
        mc=game.validate_pack(base({'mc':True,'free':False}));qs=mc['topics'][0]['questions'];self.assertEqual(qs[0]['choices'],['a','b','c']);self.assertNotIn('choices',qs[1])
    def test_generator_prompt_asks_for_choices_only_when_mc(self):
        self.assertIn('"choices":[string]',game.topic_prompt('9th grade',True));self.assertNotIn('"choices"',game.topic_prompt('9th grade',False));self.assertIn('9th grade',game.topic_prompt('9th grade',False))
    def test_mc_only_is_graded_instantly_without_the_tutor(self):
        auth,p,a=self.mc_player({'mc':True,'free':False});self.assertEqual(a['mode'],'mc');self.assertEqual(len(a['choices']),4);self.assertNotIn('correct',a)
        self.ai_patch.stop();calls=[];self.ai_patch=patch.object(game,'ai',side_effect=lambda *x,**k:calls.append(1));self.ai_patch.start()
        with self.assertRaises(game.GameError):self.mc_chat(auth,p)
        r=self.mc_chat(auth,p,1)['player']['active'];self.assertTrue(r['done']);self.assertEqual(p['score'],1);self.assertEqual(calls,[])
    def test_mc_only_miss_explains_ends_the_question_and_never_repeats(self):
        auth,p,a=self.mc_player({'mc':True,'free':False});cells=p['cells']
        r=self.mc_chat(auth,p,0)['player']['active'];self.assertTrue(r['done']);self.assertEqual(p['score'],0);self.assertEqual(p['cells'],cells)
        txt=r['messages'][-1]['text'];self.assertIn('B) B two',txt);self.assertIn('Because B is right.',txt);self.assertEqual(p['completed'],['0:0'])
        game.dispatch('/api/leave',auth);p['x'],p['y']=game.POSITIONS[0]
        again=game.dispatch('/api/start',{**auth,'topic':0})['player']['active'];self.assertTrue(again['messages'][0]['text']!='' )
        self.assertEqual(game.ROOMS[auth['code']]['players'][p['id']]['completed'],['0:0'])
    def test_both_needs_choice_and_reasoning_and_wrong_choice_cannot_pass(self):
        auth,p,a=self.mc_player({'mc':True,'free':True});self.assertEqual(a['mode'],'both')
        seen=[];self.ai_patch.stop();self.ai_patch=patch.object(game,'ai',side_effect=lambda s,d,*x,**k:seen.append(d) or {'status':'correct','feedback':'Great!'});self.ai_patch.start()
        with self.assertRaises(game.GameError):self.mc_chat(auth,p,text='because magnets pull things')
        with self.assertRaises(game.GameError):self.mc_chat(auth,p,1,'   ')
        r=self.mc_chat(auth,p,0,'I think magnets pull on iron so this one')['player']['active']
        self.assertFalse(r['done']);self.assertNotIn('Great',r['messages'][-1]['text']);self.assertEqual(seen[-1]['student_choice'],0);self.assertIn('My choice: A) A one',seen[-1]['student'])
        r=self.mc_chat(auth,p,1,'poles repel')['player']['active'];self.assertTrue(r['done']);self.assertIn('My reasoning: poles repel',seen[-1]['student'])
    def test_free_response_pack_ignores_choices(self):
        auth,p,a=self.mc_player({'mc':False,'free':True});self.assertEqual(a['mode'],'free');self.assertEqual(a['choices'],[])
    def test_generate_makes_exactly_the_requested_number_of_stations(self):
        seen=[]
        def fake(system,data,max_tokens=650,wait=None):
            if 'topic' not in data:
                seen.append(system);return {'title':'T','topics':[{'name':'N%d'%i,'icon':'x','focus':'f'} for i in range(7)]}
            return {'questions':[{'prompt':'Q?','answer':'a','hint':'h'}]}
        with patch.object(game,'ai',side_effect=fake):
            r=game.dispatch('/api/generate',{'text':'magnets','count':3,'teacherKey':'teacher-test'})
            self.assertEqual(len(r['pack']['topics']),3);self.assertIn('exactly 3 topic stations',seen[-1])
            r=game.dispatch('/api/generate',{'text':'magnets','count':'junk','teacherKey':'teacher-test'});self.assertEqual(len(r['pack']['topics']),5)
    def test_public_state_hides_keys_and_answers(self):
        r=game.dispatch('/api/state',self.auth); text=json.dumps(r['room']);self.assertNotIn(self.auth['token'],text);self.assertNotIn(self.created['host'],text);self.assertNotIn('terms',text);self.assertNotIn('questions',text)
    def ans(self):
        a=self.p['active'];return game.BUILTIN['topics'][a['topic']]['questions'][a['index']]['answer']
    def test_hint_costs_a_cell_but_no_attempt(self):
        self.start();self.p['cells']=1;self.chat(kind='hint');self.assertEqual(self.p['active']['attempts'],0);self.assertEqual(self.p['cells'],0)
        with self.assertRaises(game.GameError):game.dispatch('/api/chat',{**self.auth,'challenge':self.p['active']['id'],'requestId':'x2','kind':'hint','text':''})
    def test_short_answer_prompts_reasoning_free(self):
        self.start();self.chat('yes');self.assertEqual(self.p['active']['attempts'],0)
    def test_success_and_duplicate_request(self):
        self.start();answer=self.ans();self.chat(answer,rid='same');self.chat(answer,rid='same');self.assertEqual(self.p['score'],1);self.assertEqual(self.p['completed'],['0:%d'%self.p['active']['index']])
    def test_wrong_attempts_then_supported_revision(self):
        self.start()
        for _ in range(3):self.chat('The invisible unicorn sends purple glitter around the entire spaceship every day.')
        self.assertTrue(self.p['active']['repair']);self.chat(self.ans());self.assertEqual(self.p['score'],0);self.assertTrue(self.p['active']['done'])
    def test_solution_zero_points(self):
        self.start();self.chat(kind='solution');self.chat(self.ans());self.assertEqual(self.p['score'],0)
    def test_second_attempt_half_point(self):
        self.start();self.chat('The invisible unicorn sends purple glitter around the entire spaceship every day.');self.chat(self.ans());self.assertEqual(self.p['score'],.5)
    def test_leave_and_resume_without_losing_progress(self):
        original=self.start();self.chat(kind='hint');original_id=original['id']
        game.dispatch('/api/leave',self.auth);self.assertIsNone(self.p['active'])
        self.start(1);game.dispatch('/api/leave',self.auth)
        restored=self.start(0);self.assertEqual(restored['id'],original_id);self.assertEqual(len(restored['messages']),3)
        self.assertEqual(restored['attempts'],0)
    def test_cannot_start_remote(self):
        with self.assertRaises(game.GameError):game.dispatch('/api/start',{**self.auth,'topic':0})
    def test_repair_requires_own_understanding(self):
        self.p['x'],self.p['y']=game.POSITIONS[0];self.p['cells']=3
        with self.assertRaises(game.GameError):game.dispatch('/api/repair',{**self.auth,'topic':0})
    def test_tokens_pay_for_hints_and_time(self):
        self.start();self.p['cells']=0;self.p['hints']=1;self.p['times']=0
        self.chat(kind='hint');self.assertEqual(self.p['hints'],0);self.p['cells']=0
        with self.assertRaises(game.GameError):game.dispatch('/api/moretime',{**self.auth,'challenge':self.p['active']['id']})
        self.p['times']=1;game.dispatch('/api/moretime',{**self.auth,'challenge':self.p['active']['id']});self.assertEqual(self.p['times'],0)
        self.p['cells']=1;game.dispatch('/api/moretime',{**self.auth,'challenge':self.p['active']['id']});self.assertEqual(self.p['cells'],0)  # spare cell works as a joker
    def test_cells_not_duplicated(self):
        game.cell_pool(game.ROOMS[self.auth['code']]);cell=game.ROOMS[self.auth['code']]['cellPool']['active'][0];self.p['x'],self.p['y']=game.cell_positions()[cell]
        game.dispatch('/api/cell',{**self.auth,'cell':cell});game.dispatch('/api/cell',{**self.auth,'cell':cell});self.assertEqual(self.p.get('hints',0)+self.p.get('times',0),1)  # one token, not two
        self.assertEqual(self.p['hints' if cell%2==0 else 'times'],1)
        self.assertNotIn(cell,game.ROOMS[self.auth['code']]['cellPool']['active'])  # taken until it respawns
    def test_cells_scale_with_players_and_hints_cost_one(self):
        r=game.ROOMS[self.auth['code']];self.assertEqual(len(game.cell_pool(r)),3)
        for n in range(11):r['players'][f'p{n}']={**self.p,'id':f'p{n}'}
        self.assertEqual(len(game.cell_pool(r)),9)  # 12 players: 9 cells, about 3 per 4 players
    def test_repair_rewards_teammate_once(self):
        j=game.dispatch('/api/join',{'code':self.auth['code'],'name':'Grace'});other=game.ROOMS[self.auth['code']]['players'][j['player']['id']];other['cells']=0
        self.p['completed']=['0:0','0:1'];self.p['cells']=2;self.p['x'],self.p['y']=game.POSITIONS[0]
        game.dispatch('/api/repair',{**self.auth,'topic':0});game.dispatch('/api/repair',{**self.auth,'topic':0});self.assertEqual(other['cells'],1);self.assertEqual(self.p['cells'],0)
    def test_teacher_pause(self):
        game.dispatch('/api/host',{**self.created,'action':'pause'})
        with self.assertRaises(game.GameError):game.dispatch('/api/move',{**self.auth,'x':810,'y':460})
    def test_restart_recovery(self):
        self.start();self.chat(kind='hint');game.ROOMS.clear();game.load();r,p=game.get(self.auth);self.assertEqual(len(p['active']['messages']),3)
    def test_missing_api_key_blocks_play_instead_of_demo(self):
        game.KEY=''
        pack=copy.deepcopy(game.BUILTIN);pack['topics'][0]['name']='Biology'
        with self.assertRaises(game.GameError):game.dispatch('/api/create',{'mode':'solo','pack':pack})
    def test_failure_does_not_consume_attempt(self):
        self.start();game.ROOMS[self.auth['code']]['ai']=True
        with patch.object(game,'ai',side_effect=game.GameError('Unavailable')):
            with self.assertRaises(game.GameError):self.chat('A sufficiently long answer explaining moving charges and their magnetic field.')
        self.assertEqual(self.p['active']['attempts'],0);self.assertFalse(self.p['active']['busy']);self.assertEqual(len(self.p['active']['messages']),1)
    def test_sonnet_55_request_settings(self):
        game.KEY='dummy-test-key'
        captured={}
        def request(req,timeout):
            captured.update(json.loads(req.data))
            return io.BytesIO(json.dumps({'content':[{'type':'text','text':'{"status":"help","feedback":"Try a prediction."}'}]}).encode())
        with patch.object(game,'MODEL','claude-sonnet-5-5'),patch.object(game,'urlopen',side_effect=request):
            response=self.real_ai('Tutor',{'student':'hello'},650)
        self.assertEqual(captured['model'],'claude-sonnet-5-5')
        self.assertEqual(captured['thinking'],{'type':'between_tools'})
        self.assertEqual(captured['output_config'],{'effort':'medium'})
        self.assertEqual(response['status'],'help')
    def test_live_evaluation_and_validation(self):
        self.start();game.ROOMS[self.auth['code']]['ai']=True
        with patch.object(game,'ai',return_value={'status':'correct','feedback':'Correct reasoning.'}):self.chat('Natural language explanation without demo keywords.')
        self.assertEqual(self.p['score'],1)
    def test_study_code_clones_approved_pack(self):
        result=game.dispatch('/api/create',{'mode':'solo','source':self.auth['code']})
        self.assertEqual(game.ROOMS[result['code']]['pack']['title'],game.BUILTIN['title'])
    def test_disabled_study_code_rejected(self):
        game.ROOMS[self.auth['code']]['allowStudy']=False
        with self.assertRaises(game.GameError):game.dispatch('/api/create',{'mode':'solo','source':self.auth['code']})
    def test_teams_balance(self):
        r=game.dispatch('/api/create',{'mode':'race','teacherKey':'teacher-test'});teams=[]
        for i in range(5):teams.append(game.dispatch('/api/join',{'code':r['code'],'name':str(i)})['player']['team'])
        self.assertEqual(teams.count('violet'),3);self.assertEqual(teams.count('mint'),2)
    def test_full_playthrough_and_optional_practice(self):
        for topic,t in enumerate(game.BUILTIN['topics']):
            self.start(topic);self.chat(self.ans());self.assertTrue(self.p['active']['done']);game.dispatch('/api/leave',self.auth)
            self.p['cells']=2;game.dispatch('/api/repair',{**self.auth,'topic':topic})
        self.assertEqual(self.p['score'],7);self.assertEqual(len(self.p['repairs']),7)
        self.start(0);self.chat(self.ans());self.assertEqual(self.p['score'],7)

class UpgradeTests(unittest.TestCase):
    setUp=GameTests.setUp
    tearDown=GameTests.tearDown
    start=GameTests.start
    chat=GameTests.chat
    fake_ai=staticmethod(GameTests.fake_ai)
    def test_grade_level_is_validated_and_reaches_the_tutor(self):
        r=game.dispatch('/api/create',{'mode':'coop','pack':copy.deepcopy(game.BUILTIN),'teacherKey':'teacher-test','grade':'7th grade'});self.assertEqual(game.ROOMS[r['code']]['grade'],'7th grade')
        r=game.dispatch('/api/create',{'mode':'coop','pack':copy.deepcopy(game.BUILTIN),'teacherKey':'teacher-test','grade':'<script>'});self.assertEqual(game.ROOMS[r['code']]['grade'],'9th grade')
        pk=copy.deepcopy(game.BUILTIN);pk['grade']='11th grade';r=game.dispatch('/api/create',{'mode':'coop','pack':pk,'teacherKey':'teacher-test'});self.assertEqual(game.ROOMS[r['code']]['grade'],'11th grade')  # a saved pack carries its grade
        self.auth={'code':r['code']};j=game.dispatch('/api/join',{**self.auth,'name':'Ada'});self.auth['token']=j['token'];self.p=game.ROOMS[r['code']]['players'][j['player']['id']];self.p['x'],self.p['y']=game.POSITIONS[0]
        game.dispatch('/api/start',{**self.auth,'topic':0});self.p['cells']=1;self.chat(kind='hint')
        system,data=game.ai.call_args[0][0],game.ai.call_args[0][1]
        self.assertIn('11th grade',system);self.assertNotIn('{GRADE}',system);self.assertEqual(data['grade_level'],'11th grade')
    def test_characters_have_unique_colors_and_validated_looks(self):
        r=game.dispatch('/api/create',{'mode':'coop','pack':copy.deepcopy(game.BUILTIN),'teacherKey':'teacher-test'});code=r['code'];room=game.ROOMS[code]
        a=game.dispatch('/api/join',{'code':code,'name':'A','look':{'color':'Blue','shape':'cat','face':'wink','hat':'crown'}})
        b=game.dispatch('/api/join',{'code':code,'name':'B','look':{'color':'Blue','shape':'<x>','face':'nope','hat':'none'}})
        self.assertEqual(a['player']['look'],{'color':'Blue','shape':'cat','face':'wink','hat':'crown'})
        self.assertNotEqual(b['player']['look']['color'],'Blue');self.assertEqual((b['player']['look']['shape'],b['player']['look']['face']),('blob','happy'))  # taken color bumps to a free one; junk is cleaned
        with self.assertRaises(game.GameError):game.dispatch('/api/look',{'code':code,'token':b['token'],'look':{'color':'Blue'}})  # cannot steal a taken color
        ok=game.dispatch('/api/look',{'code':code,'token':b['token'],'look':{'color':'Pink','shape':'bunny','face':'sleepy','hat':'cap'}});self.assertEqual(ok['player']['look']['color'],'Pink')
        pub={p['name']:p['look']['color'] for p in ok['room']['players']};self.assertEqual(pub,{'A':'Blue','B':'Pink'})  # everyone sees everyone's look
        for n in range(14):game.dispatch('/api/join',{'code':code,'name':f'P{n}','look':{'color':'Blue'}})
        self.assertEqual(len({p['look']['color'] for p in room['players'].values()}),16)  # 16 players, 16 distinct colors
    def test_solo_cannot_turn_off_claude(self):
        r=game.dispatch('/api/create',{'mode':'solo','live':False})
        self.assertTrue(game.ROOMS[r['code']]['ai'])
        self.assertEqual(game.ROOMS[r['code']]['followup'],30)
    def test_legacy_session_always_calls_claude_for_short_answers(self):
        game.ROOMS[self.auth['code']]['ai']=False;self.start(2)
        with patch.object(game,'ai',return_value={'status':'correct','feedback':'Yes, stronger! ⚡'}) as call:
            self.chat('The field gets stronger.')
        call.assert_called_once();self.assertEqual(self.p['score'],1);self.assertEqual(self.p['cells'],1)
    def test_api_failure_never_falls_back(self):
        self.start(2)
        with patch.object(game,'ai',side_effect=game.GameError('Claude unavailable')):
            with self.assertRaises(game.GameError):self.chat('The field gets stronger.')
        self.assertFalse(self.p['active']['done']);self.assertEqual(self.p['cells'],0)
    def test_auto_names_override_submitted_names_and_stay_unique(self):
        r=game.ROOMS[self.auth['code']];r['autoNames']=True
        names=[game.dispatch('/api/join',{'code':r['code'],'name':'inappropriate-input'})['player']['name'] for _ in range(20)]
        self.assertEqual(len(set(names)),20);self.assertTrue(all('inappropriate-input' not in n for n in names))
        game.ROOMS.clear();game.load();self.assertTrue(game.ROOMS[r['code']]['autoNames'])
    def test_leave_during_api_call_keeps_result_on_original_conversation(self):
        self.start(0);first_id=self.p['active']['id'];first_idx=self.p['active']['index'];started=threading.Event();finish=threading.Event();errors=[]
        def response(*args):
            started.set();finish.wait(3);return {'status':'correct','feedback':'⚡ Correct.'}
        def send():
            try:self.chat('Moving charges produce a field.')
            except Exception as exc:errors.append(exc)
        with patch.object(game,'ai',side_effect=response):
            worker=threading.Thread(target=send);worker.start();self.assertTrue(started.wait(2))
            game.dispatch('/api/leave',self.auth);other=self.start(1);finish.set();worker.join(4)
        self.assertFalse(errors);self.assertEqual(self.p['active']['id'],other['id']);self.assertNotEqual(other['id'],first_id)
        self.assertTrue(self.p['conversations']['0']['done']);self.assertEqual(self.p['completed'],['0:%d'%first_idx]);self.assertEqual(self.p['cells'],1)
    def test_suspended_chat_survives_restart(self):
        a=self.start();self.chat(kind='hint');game.dispatch('/api/leave',self.auth);game.ROOMS.clear();game.load()
        r,self.p=game.get(self.auth);self.assertEqual(self.start()['id'],a['id']);self.assertEqual(len(self.p['active']['messages']),3)
    def test_can_leave_while_teacher_paused(self):
        self.start();game.ROOMS[self.auth['code']]['paused']=True;game.dispatch('/api/leave',self.auth);self.assertIsNone(self.p['active'])
    def test_relay_location_order_and_one_reward_per_route(self):
        game.dispatch('/api/relay',{**self.auth,'action':'start','route':0})
        with self.assertRaises(game.GameError):game.dispatch('/api/relay',{**self.auth,'checkpoint':0})
        for lap in range(2):
            if lap:game.dispatch('/api/relay',{**self.auth,'action':'start','route':0})
            for i,(x,y) in enumerate(game.RELAY_ROUTES[0]['points']):
                self.p['x'],self.p['y']=x,y;game.dispatch('/api/relay',{**self.auth,'checkpoint':i})
            self.assertIsNone(self.p['relay']);self.assertEqual(self.p['cells'],2)
        self.assertEqual(self.p['score'],0);self.assertIn('0',self.p['relayRecords'])
    def test_existing_room_migration_and_private_transcript(self):
        r=game.ROOMS[self.auth['code']];r['ai']=False;r['followup']=60;self.start();self.chat(kind='hint');game.dispatch('/api/leave',self.auth);game.save()
        game.ROOMS.clear();game.load();r,p=game.get(self.auth)
        self.assertTrue(r['ai']);self.assertEqual(r['followup'],30);self.assertNotIn('conversations',json.dumps(game.room_public(r)))

    def test_game_types_listed_and_default_is_station(self):
        types={t['id']:t for t in game.dispatch('/api/config',{})['gameTypes']}
        self.assertTrue(types['station']['available']);self.assertFalse(types['climb']['available'])
        self.assertEqual(game.room_public(game.ROOMS[self.auth['code']])['gameType'],'station')
    def test_unavailable_or_unknown_game_type_is_rejected(self):
        for bad in ('climb','nonsense'):
            with self.assertRaises(game.GameError):game.dispatch('/api/create',{'mode':'coop','gameType':bad,'pack':copy.deepcopy(game.BUILTIN),'teacherKey':'teacher-test'})
    def test_old_rooms_load_as_station_and_study_rooms_inherit_type(self):
        r=game.ROOMS[self.auth['code']];r.pop('gameType');game.save();game.ROOMS.clear();game.load()
        self.assertEqual(game.ROOMS[self.auth['code']]['gameType'],'station')
        solo=game.dispatch('/api/create',{'mode':'solo','source':self.auth['code']})
        self.assertEqual(game.ROOMS[solo['code']]['gameType'],'station')

class ThinkTimeTests(unittest.TestCase):
    def test_thirty_seconds_for_multiple_choice_and_a_minute_otherwise(self):
        q={'prompt':'Why do magnets attract iron?'}
        self.assertEqual(game.think_seconds(q,'mc'),30);self.assertEqual(game.think_seconds(q,'both'),60);self.assertEqual(game.think_seconds(q),60)
        self.assertEqual(game.think_seconds({'prompt':'word '*80},'free'),60)
    def test_a_question_can_override_its_time_within_bounds(self):
        self.assertEqual(game.think_seconds({'prompt':'x','seconds':500}),150);self.assertEqual(game.think_seconds({'prompt':'x','seconds':5}),30)
        self.assertEqual(game.think_seconds({'prompt':'x','seconds':'bad'},'mc'),30)
    def test_generator_prompt_demands_short_single_part_questions(self):
        for mc in (False,True):
            p=game.topic_prompt('9th grade',mc);self.assertIn('ONE or TWO short sentences',p);self.assertIn('no multi-part',p)

if __name__=='__main__':unittest.main()


class MediaPackTests(unittest.TestCase):
    def test_safe_url(self):
        self.assertEqual(game.safe_url('https://phet.colorado.edu/x'),'https://phet.colorado.edu/x')
        for bad in ('http://x.com/a','javascript:alert(1)','https://a b.com',''):
            self.assertEqual(game.safe_url(bad),'')
    def test_pack_keeps_only_https_media(self):
        p=game.validate_pack({'title':'T','topics':[{'name':'A','sim':{'url':'http://bad.com/x'},'questions':[{'prompt':'Why?','answer':'Because reasons here.','hint':'Think.','image':'javascript:1'}]},{'name':'B','sim':{'url':'https://ok.org/s','title':'S'},'questions':[{'prompt':'Why2?','answer':'Because reasons here.','hint':'Think.','image':'https://ok.org/i.png'}]}]})
        self.assertNotIn('sim',p['topics'][0]);self.assertNotIn('image',p['topics'][0]['questions'][0])
        self.assertEqual(p['topics'][1]['sim']['url'],'https://ok.org/s');self.assertEqual(p['topics'][1]['questions'][0]['image'],'https://ok.org/i.png')


class VariantTests(unittest.TestCase):
    def test_svg_cleaning(self):
        self.assertTrue(game.clean_svg('<svg viewBox="0 0 10 10"><circle r="3"/></svg>').startswith('<svg xmlns='))
        for bad in ('<svg><script>x</script></svg>','<svg onload="x()"></svg>','<svg><image href="http://e"/></svg>','<div></div>','<svg>'+'a'*9000+'</svg>'):
            self.assertEqual(game.clean_svg(bad),'')
    def test_variants_resolved_and_validated(self):
        q={'prompt':'A','answer':'a','hint':'h','variants':[{'prompt':'B','answer':'b','hint':'h2'}]}
        self.assertEqual(game.resolve_question(q,0)['prompt'],'A')
        self.assertEqual(game.resolve_question(q,1)['prompt'],'B')
        self.assertNotIn('variants',game.resolve_question(q,1))
        p=game.validate_pack({'title':'T','topics':[{'name':'A','questions':[dict(q,variants=q['variants']+[{'prompt':'x'}],diagram='<svg><script/></svg>')]}]})
        self.assertEqual(len(p['topics'][0]['questions'][0]['variants']),1);self.assertNotIn('diagram',p['topics'][0]['questions'][0])


class VariantEncounterTests(unittest.TestCase):
    def test_student_gets_variant_and_diagram(self):
        with tempfile.TemporaryDirectory() as tmp:
            game.DB=tmp+'/t.sqlite';game.ROOMS.clear()
            old=(game.KEY,game.TEACHER_KEY);game.KEY='k';game.TEACHER_KEY='tk'
            try:
                svg='<svg viewBox="0 0 10 10"><circle r="3"/></svg>'
                base={'prompt':'Base 6 V?','answer':'a','hint':'h','variants':[{'prompt':'Var 9 V?','answer':'b','hint':'h','diagram':svg}]}
                pack={'title':'T','topics':[{'name':'Circuits','questions':[base]}]}
                c=game.dispatch('/api/create',{'mode':'coop','pack':pack,'teacherKey':'tk'})
                seen=set()
                for _ in range(40):
                    j=game.dispatch('/api/join',{'code':c['code'],'name':'S%d'%_})
                    p=game.ROOMS[c['code']]['players'][j['player']['id']];p['x'],p['y']=game.POSITIONS[0]
                    a=game.dispatch('/api/start',{'code':c['code'],'token':j['token'],'topic':0})['player']['active']
                    seen.add(a['prompt'])
                    if a['prompt'].startswith('Var'): self.assertEqual(a['image'], '')
                self.assertEqual(seen,{'Base 6 V?','Var 9 V?'})
            finally: game.KEY,game.TEACHER_KEY=old



class GenerateTests(unittest.TestCase):
    def test_generate_builds_topics_in_parallel_and_survives_a_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            game.DB=tmp+'/t.sqlite';game.ROOMS.clear();old=(game.KEY,game.TEACHER_KEY,game.ai);game.KEY='k';game.TEACHER_KEY='tk'
            def fake(system,data,max_tokens=650,wait=None):
                if 'topic' not in data: return {'title':'Circuits','topics':[{'name':'Ohm','icon':'⚡','focus':'f'},{'name':'Bad','icon':'x','focus':'f'}]}
                if data['topic']=='Bad': raise game.GameError('boom')
                return {'questions':[{'prompt':'Why?','answer':'Because.','hint':'h','level':'easy'}]}
            game.ai=fake
            try:
                r=game.dispatch('/api/generate',{'text':'ohms law','teacherKey':'tk'})
                self.assertEqual([t['name'] for t in r['pack']['topics']],['Ohm']);self.assertTrue(r['partial'])
                self.assertEqual(r['pack']['topics'][0]['questions'][0]['level'],'easy')
            finally: game.KEY,game.TEACHER_KEY,game.ai=old


class MoreTimeTests(unittest.TestCase):
    def test_more_time_costs_a_cell(self):
        with tempfile.TemporaryDirectory() as tmp:
            game.DB=tmp+'/t.sqlite';game.ROOMS.clear();old=(game.KEY,game.TEACHER_KEY);game.KEY='k';game.TEACHER_KEY='tk'
            try:
                pack={'title':'T','topics':[{'name':'A','questions':[{'prompt':'Why?','answer':'a','hint':'h'}]}]}
                c=game.dispatch('/api/create',{'mode':'coop','pack':pack,'teacherKey':'tk'})
                j=game.dispatch('/api/join',{'code':c['code'],'name':'Ada'});auth={'code':c['code'],'token':j['token']}
                p=game.ROOMS[c['code']]['players'][j['player']['id']];p['x'],p['y']=game.POSITIONS[0];p['cells']=0
                a=game.dispatch('/api/start',{**auth,'topic':0})['player']['active']
                with self.assertRaises(game.GameError): game.dispatch('/api/moretime',{**auth,'challenge':a['id']})
                p['cells']=2
                self.assertEqual(game.dispatch('/api/moretime',{**auth,'challenge':a['id']})['player']['cells'],1)
            finally: game.KEY,game.TEACHER_KEY=old
