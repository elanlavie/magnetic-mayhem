import io
import sys, tempfile, unittest, copy, json, threading, uuid
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server as game

class GameTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); game.DB=self.temp.name+'/test.sqlite'; game.ROOMS.clear(); self.oldkey=game.KEY; self.oldteacher=game.TEACHER_KEY; game.KEY=''; game.TEACHER_KEY=''
        self.created=game.dispatch('/api/create',{'mode':'coop','pack':copy.deepcopy(game.BUILTIN)})
        self.auth={'code':self.created['code']}
        j=game.dispatch('/api/join',{**self.auth,'name':'Ada'}); self.auth['token']=j['token']; self.p=game.ROOMS[self.auth['code']]['players'][j['player']['id']]
    def tearDown(self): game.KEY=self.oldkey; game.TEACHER_KEY=self.oldteacher; self.temp.cleanup()
    def start(self,topic=0):
        self.p['x'],self.p['y']=game.POSITIONS[topic]
        return game.dispatch('/api/start',{**self.auth,'topic':topic})['player']['active']
    def chat(self,text='',kind='answer',rid=None):
        return game.dispatch('/api/chat',{**self.auth,'challenge':self.p['active']['id'],'requestId':rid or str(uuid.uuid4()),'kind':kind,'text':text})
    def test_public_state_hides_keys_and_answers(self):
        r=game.dispatch('/api/state',self.auth); text=json.dumps(r['room']);self.assertNotIn(self.auth['token'],text);self.assertNotIn(self.created['host'],text);self.assertNotIn('terms',text);self.assertNotIn('questions',text)
    def test_hint_is_free(self):
        self.start();self.chat(kind='hint');self.assertEqual(self.p['active']['attempts'],0)
    def test_short_answer_prompts_reasoning_free(self):
        self.start();self.chat('yes');self.assertEqual(self.p['active']['attempts'],0)
    def test_success_and_duplicate_request(self):
        self.start();answer=game.BUILTIN['topics'][0]['questions'][0]['answer'];self.chat(answer,rid='same');self.chat(answer,rid='same');self.assertEqual(self.p['score'],1);self.assertEqual(self.p['completed'],['0:0'])
    def test_wrong_attempts_then_supported_revision(self):
        self.start()
        for _ in range(3):self.chat('The invisible unicorn sends purple glitter around the entire spaceship every day.')
        self.assertTrue(self.p['active']['repair']);self.chat(game.BUILTIN['topics'][0]['questions'][0]['answer']);self.assertEqual(self.p['score'],0);self.assertTrue(self.p['active']['done'])
    def test_solution_zero_points(self):
        self.start();self.chat(kind='solution');self.chat(game.BUILTIN['topics'][0]['questions'][0]['answer']);self.assertEqual(self.p['score'],0)
    def test_second_attempt_half_point(self):
        self.start();self.chat('The invisible unicorn sends purple glitter around the entire spaceship every day.');self.chat(game.BUILTIN['topics'][0]['questions'][0]['answer']);self.assertEqual(self.p['score'],.5)
    def test_cannot_abandon_challenge(self):
        self.start()
        with self.assertRaises(game.GameError):game.dispatch('/api/leave',self.auth)
    def test_cannot_start_remote(self):
        with self.assertRaises(game.GameError):game.dispatch('/api/start',{**self.auth,'topic':0})
    def test_repair_requires_own_understanding(self):
        self.p['x'],self.p['y']=game.POSITIONS[0];self.p['cells']=3
        with self.assertRaises(game.GameError):game.dispatch('/api/repair',{**self.auth,'topic':0})
    def test_cells_not_duplicated(self):
        self.p['x'],self.p['y']=game.cell_positions()[0]
        game.dispatch('/api/cell',{**self.auth,'cell':0});game.dispatch('/api/cell',{**self.auth,'cell':0});self.assertEqual(self.p['cells'],1)
    def test_repair_rewards_teammate_once(self):
        j=game.dispatch('/api/join',{'code':self.auth['code'],'name':'Grace'});other=game.ROOMS[self.auth['code']]['players'][j['player']['id']]
        self.p['completed']=['0:0','0:1'];self.p['cells']=2;self.p['x'],self.p['y']=game.POSITIONS[0]
        game.dispatch('/api/repair',{**self.auth,'topic':0});game.dispatch('/api/repair',{**self.auth,'topic':0});self.assertEqual(other['cells'],1);self.assertEqual(self.p['cells'],0)
    def test_teacher_pause(self):
        game.dispatch('/api/host',{**self.created,'action':'pause'})
        with self.assertRaises(game.GameError):game.dispatch('/api/move',{**self.auth,'x':810,'y':460})
    def test_restart_recovery(self):
        self.start();self.chat(kind='hint');game.ROOMS.clear();game.load();r,p=game.get(self.auth);self.assertEqual(len(p['active']['messages']),3)
    def test_custom_topics_need_live_ai(self):
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
            response=game.ai('Tutor',{'student':'hello'},650)
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
        r=game.dispatch('/api/create',{'mode':'race'});teams=[]
        for i in range(5):teams.append(game.dispatch('/api/join',{'code':r['code'],'name':str(i)})['player']['team'])
        self.assertEqual(teams.count('violet'),3);self.assertEqual(teams.count('mint'),2)
    def test_full_playthrough_and_optional_practice(self):
        for topic,t in enumerate(game.BUILTIN['topics']):
            for q in t['questions']:
                self.start(topic);self.chat(q['answer']);self.assertTrue(self.p['active']['done'],q['prompt']);game.dispatch('/api/leave',self.auth)
            self.p['cells']=2;game.dispatch('/api/repair',{**self.auth,'topic':topic})
        self.assertEqual(self.p['score'],14);self.assertEqual(len(self.p['repairs']),7)
        self.start(0);self.chat(game.BUILTIN['topics'][0]['questions'][0]['answer']);self.assertEqual(self.p['score'],14)
if __name__=='__main__':unittest.main()
