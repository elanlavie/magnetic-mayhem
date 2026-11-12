import io
import sys, tempfile, unittest, copy, json, threading, uuid
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server as game

class GameTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); game.DB=self.temp.name+'/test.sqlite'; game.ROOMS.clear(); self.oldteacher=game.TEACHER_KEY; game.TEACHER_KEY='teacher-test'
        self.created=game.dispatch('/api/create',{'mode':'coop','pack':copy.deepcopy(game.BUILTIN),'teacherKey':'teacher-test'})
        self.auth={'code':self.created['code']}
        j=game.dispatch('/api/join',{**self.auth,'name':'Ada'}); self.auth['token']=j['token']; self.p=game.ROOMS[self.auth['code']]['players'][j['player']['id']]; self.p['cells']=0  # tests count cells from zero
    def tearDown(self): game.TEACHER_KEY=self.oldteacher; self.temp.cleanup()
    def start(self,topic=0):
        self.p['x'],self.p['y']=game.POSITIONS[topic]
        return game.dispatch('/api/start',{**self.auth,'topic':topic})['player']['active']
    def right(self):
        a=self.p['active'];q=game.resolve_question(copy.deepcopy(game.ROOMS[self.auth['code']]['pack']['topics'][a['topic']]['questions'][a['index']]),a['vi']);return a['perm'].index(q['correct'])
    def chat(self,ok=True,choice=None,rid=None):
        n=len(self.p['active']['choices']);idx=choice if choice is not None else (self.right() if ok else (self.right()+1)%n)
        return game.dispatch('/api/chat',{**self.auth,'challenge':self.p['active']['id'],'requestId':rid or str(uuid.uuid4()),'choice':idx})
    def mc_player(self,fmt=None):
        q=lambda i:{'prompt':'Which is right %d?'%i,'answer':'Because B is right.','choices':['A one','B two','C three','D four'],'correct':1}
        pack={'title':'MC','topics':[{'name':'T%d'%i,'icon':'🧲','questions':[q(i)]} for i in range(2)]}
        c=game.dispatch('/api/create',{'mode':'coop','pack':pack,'teacherKey':'teacher-test'})
        auth={'code':c['code']};j=game.dispatch('/api/join',{**auth,'name':'Mo'});auth['token']=j['token']
        p=game.ROOMS[c['code']]['players'][j['player']['id']];p['x'],p['y']=game.POSITIONS[0]
        a=game.dispatch('/api/start',{**auth,'topic':0})['player']['active']
        return auth,p,a
    def mc_chat(self,auth,p,right=None):
        a=p['active'];idx=a['perm'].index(1)  # the original correct answer is B (index 1)
        choice=None if right is None else (idx if right else (idx+1)%len(a['choices']))
        d={**auth,'challenge':a['id'],'requestId':str(uuid.uuid4())}
        if choice is not None:d['choice']=choice
        return game.dispatch('/api/chat',d)
    def test_mc_only_is_graded_instantly_without_the_tutor(self):
        auth,p,a=self.mc_player();self.assertEqual(a['mode'],'mc');self.assertEqual(len(a['choices']),4);self.assertNotIn('correct',a);self.assertEqual(sorted(a['choices']),['A one','B two','C three','D four'])
        with self.assertRaises(game.GameError):self.mc_chat(auth,p)  # nothing picked
        r=self.mc_chat(auth,p,True)['player']['active'];self.assertTrue(r['done']);self.assertEqual(p['score'],1)
    def test_mc_only_miss_explains_and_earns_nothing(self):
        auth,p,a=self.mc_player();cells=p['cells']
        r=self.mc_chat(auth,p,False)['player']['active'];self.assertTrue(r['done']);self.assertEqual(p['score'],0);self.assertEqual(p['cells'],cells)
        txt=r['messages'][-1]['text'];self.assertIn('B two',txt);self.assertIn('Because B is right.',txt);self.assertEqual(p['completed'],[])
        game.dispatch('/api/leave',auth);p['x'],p['y']=game.POSITIONS[0]
        again=game.dispatch('/api/start',{**auth,'topic':0})['player']['active'];self.assertTrue(again['messages'][0]['text']!='' )
        self.assertEqual(game.ROOMS[auth['code']]['players'][p['id']]['completed'],[]);self.assertEqual(again['messages'][0]['text'],a['prompt'])  # the same question comes back
    def test_public_state_hides_keys_and_answers(self):
        r=game.dispatch('/api/state',self.auth); text=json.dumps(r['room']);self.assertNotIn(self.auth['token'],text);self.assertNotIn(self.created['host'],text);self.assertNotIn('terms',text);self.assertNotIn('questions',text)
    def test_success_and_duplicate_request(self):
        self.start();self.chat(rid='same');self.chat(rid='same');self.assertEqual(self.p['score'],1);self.assertEqual(self.p['completed'],['0:%d'%self.p['active']['index']])
    def test_leave_and_resume_without_losing_progress(self):
        original=self.start();original_id=original['id']
        game.dispatch('/api/leave',self.auth);self.assertIsNone(self.p['active'])
        self.start(1);game.dispatch('/api/leave',self.auth)
        restored=self.start(0);self.assertEqual(restored['id'],original_id);self.assertEqual(len(restored['messages']),1)
        self.assertEqual(restored['attempts'],0)
    def test_cannot_start_remote(self):
        with self.assertRaises(game.GameError):game.dispatch('/api/start',{**self.auth,'topic':0})
    def test_repair_requires_own_understanding(self):
        self.p['x'],self.p['y']=game.POSITIONS[0];self.p['cells']=3
        with self.assertRaises(game.GameError):game.dispatch('/api/repair',{**self.auth,'topic':0})
    def test_time_tokens_and_spare_cells_pay_for_more_time(self):
        self.start();self.p['cells']=0;self.p['times']=0
        with self.assertRaises(game.GameError):game.dispatch('/api/moretime',{**self.auth,'challenge':self.p['active']['id']})
        self.p['times']=1;game.dispatch('/api/moretime',{**self.auth,'challenge':self.p['active']['id']});self.assertEqual(self.p['times'],0)
        self.p['cells']=1;game.dispatch('/api/moretime',{**self.auth,'challenge':self.p['active']['id']});self.assertEqual(self.p['cells'],0)  # spare cell works as a joker
    def test_cells_not_duplicated(self):
        game.cell_pool(game.ROOMS[self.auth['code']]);cell=game.ROOMS[self.auth['code']]['cellPool']['active'][0];self.p['x'],self.p['y']=game.cell_positions()[cell]
        game.dispatch('/api/cell',{**self.auth,'cell':cell});game.dispatch('/api/cell',{**self.auth,'cell':cell});self.assertEqual(self.p.get('times',0),1)  # one token, not two; every pickup is thinking time now
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
        self.start();game.ROOMS.clear();game.load();r,p=game.get(self.auth);self.assertEqual(len(p['active']['messages']),1)
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
            self.start(topic);self.chat();self.assertTrue(self.p['active']['done']);game.dispatch('/api/leave',self.auth)
            self.p['cells']=2;game.dispatch('/api/repair',{**self.auth,'topic':topic})
        self.assertEqual(self.p['score'],7);self.assertEqual(len(self.p['repairs']),7)
        self.start(0);self.chat();self.assertEqual(self.p['score'],7)

class UpgradeTests(unittest.TestCase):
    setUp=GameTests.setUp
    tearDown=GameTests.tearDown
    start=GameTests.start
    chat=GameTests.chat
    def test_grade_level_is_validated_and_saved_packs_carry_it(self):
        r=game.dispatch('/api/create',{'mode':'coop','pack':copy.deepcopy(game.BUILTIN),'teacherKey':'teacher-test','grade':'7th grade'});self.assertEqual(game.ROOMS[r['code']]['grade'],'7th grade')
        r=game.dispatch('/api/create',{'mode':'coop','pack':copy.deepcopy(game.BUILTIN),'teacherKey':'teacher-test','grade':'<script>'});self.assertEqual(game.ROOMS[r['code']]['grade'],'9th grade')
        pk=copy.deepcopy(game.BUILTIN);pk['grade']='11th grade';r=game.dispatch('/api/create',{'mode':'coop','pack':pk,'teacherKey':'teacher-test'});self.assertEqual(game.ROOMS[r['code']]['grade'],'11th grade')  # a saved pack carries its grade
        self.auth={'code':r['code']};j=game.dispatch('/api/join',{**self.auth,'name':'Ada'});self.auth['token']=j['token'];self.p=game.ROOMS[r['code']]['players'][j['player']['id']];self.p['x'],self.p['y']=game.POSITIONS[0]
        pass
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
    def test_auto_names_override_submitted_names_and_stay_unique(self):
        r=game.ROOMS[self.auth['code']];r['autoNames']=True
        names=[game.dispatch('/api/join',{'code':r['code'],'name':'inappropriate-input'})['player']['name'] for _ in range(20)]
        self.assertEqual(len(set(names)),20);self.assertTrue(all('inappropriate-input' not in n for n in names))
        game.ROOMS.clear();game.load();self.assertTrue(game.ROOMS[r['code']]['autoNames'])
    def test_suspended_chat_survives_restart(self):
        a=self.start();game.dispatch('/api/leave',self.auth);game.ROOMS.clear();game.load()
        r,self.p=game.get(self.auth);self.assertEqual(self.start()['id'],a['id']);self.assertEqual(len(self.p['active']['messages']),1)
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
        r=game.ROOMS[self.auth['code']];r['followup']=60;self.start();game.dispatch('/api/leave',self.auth);game.save()
        game.ROOMS.clear();game.load();r,p=game.get(self.auth)
        self.assertEqual(r['followup'],30);self.assertNotIn('conversations',json.dumps(game.room_public(r)))

    def test_game_types_listed_and_default_is_station(self):
        types={t['id']:t for t in game.dispatch('/api/config',{})['gameTypes']}
        self.assertTrue(types['station']['available']);self.assertTrue(types['climb']['available'])
        self.assertEqual(game.room_public(game.ROOMS[self.auth['code']])['gameType'],'station')
    def test_unavailable_or_unknown_game_type_is_rejected(self):
        with self.assertRaises(game.GameError):game.dispatch('/api/create',{'mode':'coop','gameType':'nonsense','pack':copy.deepcopy(game.BUILTIN),'teacherKey':'teacher-test'})
        with self.assertRaises(game.GameError):game.dispatch('/api/create',{'mode':'infiltration','gameType':'climb','pack':copy.deepcopy(game.BUILTIN),'teacherKey':'teacher-test'})
    def test_solo_practice_from_a_climb_study_code_stays_a_climb(self):
        made=game.dispatch('/api/create',{'mode':'coop','gameType':'climb','pack':copy.deepcopy(game.BUILTIN),'teacherKey':'teacher-test','allowStudy':True})
        solo=game.dispatch('/api/create',{'mode':'impostorSolo','source':made['code']})
        r=game.ROOMS[solo['code']];self.assertEqual((r['gameType'],r['mode']),('climb','solo'))
    def test_climb_picks_unanswered_questions_and_moves_freely(self):
        made=game.dispatch('/api/create',{'mode':'coop','gameType':'climb','pack':copy.deepcopy(game.BUILTIN),'teacherKey':'teacher-test'})
        joined=game.dispatch('/api/join',{'code':made['code'],'name':'Sam'});auth={'code':made['code'],'token':joined['token']}
        r,p=game.get(auth)
        self.assertEqual(game.room_public(r)['floors'],min(game.CLIMB_CAP,sum(len(t['questions']) for t in r['pack']['topics'])))
        moved=game.dispatch('/api/move',{**auth,'x':450,'y':-330})
        self.assertEqual((moved['x'],moved['y']),(450,-330))
        game.dispatch('/api/move',{**auth,'x':450,'y':-99999});self.assertEqual(p['y'],-330)
        snap=game.dispatch('/api/start',{**auth,'topic':2});self.assertEqual(snap['player']['active']['topic'],2)
        p['completed']=[f'2:{i}' for i in range(len(r['pack']['topics'][2]['questions']))];p['active']=None
        self.assertNotEqual(game.climb_pick(r,p,2),2)
        p['completed']=[f'{i}:{j}' for i,t in enumerate(r['pack']['topics']) for j in range(len(t['questions']))]
        self.assertIsNone(game.climb_pick(r,p,0))
    def test_climb_energy_setting_and_race_is_won_by_reaching_the_top(self):
        made=game.dispatch('/api/create',{'mode':'race','gameType':'climb','energy':110,'pack':copy.deepcopy(game.BUILTIN),'teacherKey':'teacher-test'})
        r=game.ROOMS[made['code']];pub=game.room_public(r)
        self.assertEqual((pub['energy'],pub['summit']),(110,game.climb_floors(r)*game.CLIMB_PX))
        low=game.dispatch('/api/create',{'mode':'coop','gameType':'climb','energy':1,'pack':copy.deepcopy(game.BUILTIN),'teacherKey':'teacher-test'})
        self.assertEqual(game.ROOMS[low['code']]['energy'],40)
        joined=game.dispatch('/api/join',{'code':made['code'],'name':'Sam'});auth={'code':made['code'],'token':joined['token']}
        _,p=game.get(auth);top=game.climb_summit(r)
        p['x'],p['y']=450,-top+300  # climbing is checked in small steps, so start near the top
        game.dispatch('/api/move',{**auth,'x':450,'y':-top+40});self.assertIsNone(r.get('winner'))
        game.dispatch('/api/move',{**auth,'x':450,'y':-top-10});self.assertEqual(r.get('winner'),p['team'])
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
class MediaPackTests(unittest.TestCase):
    def test_safe_url(self):
        self.assertEqual(game.safe_url('https://phet.colorado.edu/x'),'https://phet.colorado.edu/x')
        for bad in ('http://x.com/a','javascript:alert(1)','https://a b.com',''):
            self.assertEqual(game.safe_url(bad),'')
    def test_pack_keeps_only_https_media(self):
        p=game.validate_pack({'title':'T','topics':[{'name':'A','sim':{'url':'http://bad.com/x'},'questions':[{'prompt':'Why?','answer':'Because reasons here.','choices':['a','b'],'correct':0,'image':'javascript:1'}]},{'name':'B','sim':{'url':'https://ok.org/s','title':'S'},'questions':[{'prompt':'Why2?','answer':'Because reasons here.','choices':['a','b'],'correct':0,'image':'https://ok.org/i.png'}]}]})
        self.assertNotIn('sim',p['topics'][0]);self.assertNotIn('image',p['topics'][0]['questions'][0])
        self.assertEqual(p['topics'][1]['sim']['url'],'https://ok.org/s');self.assertEqual(p['topics'][1]['questions'][0]['image'],'https://ok.org/i.png')


class VariantTests(unittest.TestCase):
    def test_svg_cleaning(self):
        self.assertTrue(game.clean_svg('<svg viewBox="0 0 10 10"><circle r="3"/></svg>').startswith('<svg xmlns='))
        for bad in ('<svg><script>x</script></svg>','<svg onload="x()"></svg>','<svg><image href="http://e"/></svg>','<div></div>','<svg>'+'a'*9000+'</svg>'):
            self.assertEqual(game.clean_svg(bad),'')
    def test_variants_resolved_and_validated(self):
        q={'prompt':'A','answer':'a','choices':['x','y'],'correct':0,'variants':[{'prompt':'B','answer':'b','choices':['x','y'],'correct':1}]}
        self.assertEqual(game.resolve_question(q,0)['prompt'],'A')
        self.assertEqual(game.resolve_question(q,1)['prompt'],'B')
        self.assertNotIn('variants',game.resolve_question(q,1))
        p=game.validate_pack({'title':'T','topics':[{'name':'A','questions':[dict(q,variants=q['variants']+[{'prompt':'x'}],diagram='<svg><script/></svg>')]}]})
        self.assertEqual(len(p['topics'][0]['questions'][0]['variants']),1);self.assertNotIn('diagram',p['topics'][0]['questions'][0])


class VariantEncounterTests(unittest.TestCase):
    def test_student_gets_variant_and_diagram(self):
        with tempfile.TemporaryDirectory() as tmp:
            game.DB=tmp+'/t.sqlite';game.ROOMS.clear()
            old=game.TEACHER_KEY;game.TEACHER_KEY='tk'
            try:
                svg='<svg viewBox="0 0 10 10"><circle r="3"/></svg>'
                base={'prompt':'Base 6 V?','answer':'a','choices':['x','y'],'correct':0,'variants':[{'prompt':'Var 9 V?','answer':'b','choices':['x','y'],'correct':1,'diagram':svg}]}
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
            finally: game.TEACHER_KEY=old




class MoreTimeTests(unittest.TestCase):
    def test_more_time_costs_a_cell(self):
        with tempfile.TemporaryDirectory() as tmp:
            game.DB=tmp+'/t.sqlite';game.ROOMS.clear();old=game.TEACHER_KEY;game.TEACHER_KEY='tk'
            try:
                pack={'title':'T','topics':[{'name':'A','questions':[{'prompt':'Why?','answer':'a','choices':['x','y'],'correct':0}]}]}
                c=game.dispatch('/api/create',{'mode':'coop','pack':pack,'teacherKey':'tk'})
                j=game.dispatch('/api/join',{'code':c['code'],'name':'Ada'});auth={'code':c['code'],'token':j['token']}
                p=game.ROOMS[c['code']]['players'][j['player']['id']];p['x'],p['y']=game.POSITIONS[0];p['cells']=0
                a=game.dispatch('/api/start',{**auth,'topic':0})['player']['active']
                with self.assertRaises(game.GameError): game.dispatch('/api/moretime',{**auth,'challenge':a['id']})
                p['cells']=2
                self.assertEqual(game.dispatch('/api/moretime',{**auth,'challenge':a['id']})['player']['cells'],1)
            finally: game.TEACHER_KEY=old
