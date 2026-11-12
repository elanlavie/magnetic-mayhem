import json, copy, os, sys, tempfile, time, unittest, uuid
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server as game
import accounts


def fake_verify(credential):
    email, name = credential.split('|')
    if not email:
        raise accounts.AuthError('bad token', 401)
    return {'email': email.lower(), 'name': name, 'hd': email.split('@')[-1]}


class ClassTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old = (game.DB, game.TEACHER_KEY, accounts.MODE, accounts.GOOGLE_CLIENT_ID, accounts.TEACHER_EMAILS, accounts.SYNC_EMAIL, accounts.PUBLIC_URL)
        game.DB = self.temp.name + '/t.sqlite3'; game.TEACHER_KEY = ''; game.ROOMS.clear()
        accounts.MODE = 'classes'; accounts.GOOGLE_CLIENT_ID = 'cid'; accounts.SYNC_EMAIL = True; accounts.PUBLIC_URL = 'https://game.test'
        accounts.TEACHER_EMAILS = {'teach@wccusd.net', 'other@wccusd.net'}
        self.patches = [patch.object(accounts, 'verify_google', side_effect=fake_verify)]
        for p in self.patches: p.start()
        for key in ('SMTP_HOST', 'SMTP_USER', 'SMTP_PASSWORD', 'ALERT_FROM'): os.environ.pop(key, None)
        self.teacher = self.sign('teach@wccusd.net', 'Ms Teach')
        self.cls = self.api('/api/class/create', self.teacher, name='Period 3', domains='wccschools.org')
        self.invite = self.api('/api/class/invite', self.teacher, classId=self.cls['id'])
        self.alex = self.sign('alexander.smith@wccschools.org', 'ALEXANDER SMITH')
        self.api('/api/class/join', self.alex, code=self.invite['code'])

    def tearDown(self):
        for p in self.patches: p.stop()
        (game.DB, game.TEACHER_KEY, accounts.MODE, accounts.GOOGLE_CLIENT_ID, accounts.TEACHER_EMAILS, accounts.SYNC_EMAIL, accounts.PUBLIC_URL) = self.old
        self.temp.cleanup()

    def sign(self, email, name):
        return game.dispatch('/api/auth/google', {'credential': f'{email}|{name}'})['userToken']

    def api(self, path, token, **extra):
        return game.dispatch(path, {'userToken': token, **extra})

    def make_room(self, **extra):
        r = game.dispatch('/api/create', {'userToken': self.teacher, 'classId': self.cls['id'], 'mode': 'coop', 'pack': copy.deepcopy(game.BUILTIN), **extra})
        return r

    def join(self, token, code):
        return game.dispatch('/api/join', {'userToken': token, 'code': code})

    # --- sign-in, roles, classes
    def test_roles_and_invalid_sign_in(self):
        me = game.dispatch('/api/auth/me', {'userToken': self.teacher})['user']; self.assertEqual(me['role'], 'teacher')
        self.assertEqual(game.dispatch('/api/auth/me', {'userToken': self.alex})['user']['role'], 'student')
        with self.assertRaises(accounts.AuthError): game.dispatch('/api/auth/google', {'credential': '|x'})
        with self.assertRaises(accounts.AuthError): game.dispatch('/api/auth/me', {'userToken': 'nope'})

    def test_only_teachers_make_classes_and_a_domain_is_required(self):
        with self.assertRaises(accounts.AuthError): self.api('/api/class/create', self.alex, name='x', domains='wccschools.org')
        with self.assertRaises(accounts.AuthError): self.api('/api/class/create', self.teacher, name='x', domains='')
        with self.assertRaises(accounts.AuthError): self.api('/api/class/create', self.teacher, name='x', domains='not a domain!')

    def test_invites_enforce_domain_expiry_revocation_and_removal(self):
        kid = self.sign('kid@gmail.com', 'Kid')
        with self.assertRaises(accounts.AuthError): self.api('/api/class/join', kid, code=self.invite['code'])
        with self.assertRaises(accounts.AuthError): self.api('/api/class/join', self.teacher, code=self.invite['code'])
        mia = self.sign('mia@wccschools.org', 'Mia Lee')
        old = self.api('/api/class/invite', self.teacher, classId=self.cls['id'])
        import sqlite3; sqlite3.connect(game.DB).execute('update invites set expires=? where code=?', (time.time() - 5, old['code'])).connection.commit()
        with self.assertRaises(accounts.AuthError): self.api('/api/class/join', mia, code=old['code'])
        self.api('/api/class/invite/revoke', self.teacher, classId=self.cls['id'])
        with self.assertRaises(accounts.AuthError): self.api('/api/class/join', mia, code=self.invite['code'])
        fresh = self.api('/api/class/invite', self.teacher, classId=self.cls['id'], maxUses=1)
        self.api('/api/class/join', mia, code=fresh['code']); self.api('/api/class/join', mia, code=fresh['code'])  # idempotent
        leo = self.sign('leo@wccschools.org', 'Leo')
        with self.assertRaises(accounts.AuthError): self.api('/api/class/join', leo, code=fresh['code'])  # used up
        self.api('/api/class/remove', self.teacher, classId=self.cls['id'], email='mia@wccschools.org')
        again = self.api('/api/class/invite', self.teacher, classId=self.cls['id'])
        with self.assertRaises(accounts.AuthError): self.api('/api/class/join', mia, code=again['code'])
        self.api('/api/class/restore', self.teacher, classId=self.cls['id'], email='mia@wccschools.org')
        self.assertEqual([c['name'] for c in self.api('/api/class/list', mia)['classes']], ['Period 3'])

    def test_teachers_only_see_their_own_classes(self):
        other = self.sign('other@wccusd.net', 'Other Teacher')
        self.assertEqual(self.api('/api/class/list', other)['classes'], [])
        for path, extra in (('/api/class/members', {}), ('/api/class/invite', {}), ('/api/class/transcript', {'email': 'alexander.smith@wccschools.org'})):
            with self.assertRaises(accounts.AuthError): self.api(path, other, classId=self.cls['id'], **extra)
        with self.assertRaises(accounts.AuthError): game.dispatch('/api/create', {'userToken': other, 'classId': self.cls['id'], 'mode': 'coop', 'pack': copy.deepcopy(game.BUILTIN)})
        with self.assertRaises(accounts.AuthError): self.api('/api/class/members', self.alex, classId=self.cls['id'])

    def test_teacher_can_delete_a_class_and_its_data(self):
        info = self.student_in_room()
        self.chat_with_tutor(info)
        other = self.sign('other@wccusd.net', 'Other Teacher')
        with self.assertRaises(accounts.AuthError): self.api('/api/class/delete', other, classId=self.cls['id'])
        with self.assertRaises(accounts.AuthError): self.api('/api/class/delete', self.alex, classId=self.cls['id'])
        self.api('/api/class/delete', self.teacher, classId=self.cls['id'])
        self.assertEqual(self.api('/api/class/list', self.teacher)['classes'], [])
        self.assertEqual(self.api('/api/class/list', self.alex)['classes'], [])
        with self.assertRaises(accounts.AuthError): self.api('/api/class/join', self.sign('mia@wccschools.org', 'Mia'), code=self.invite['code'])
        with self.assertRaises(game.GameError): game.dispatch('/api/state', {'code': info['code'], 'token': info['token']})

    # --- private question library
    LIB_TEXT = """Title: E&M Practice Test

Topic: Magnetism
1. Why does a magnet attract a nail?
A) It has charge
B) Its tiny domains line up
C) Gravity
Answer: B
Explanation: The nail's domains align with the magnet's field.

2. What does a compass do near a wire with current?
A) Deflects
B) Nothing
Answer: A
Explanation: Current makes a magnetic field.

Topic: Electricity
3. Why do bulbs in a series circuit dim?
A) They share the voltage
B) They are tired
Answer: A
Explanation: Voltage is split between them.

4. A question with no answer line
A) one
B) two
"""

    def test_library_is_private_and_builds_a_subject_only_pack(self):
        lib = game.dispatch('/api/library/import', {'userToken': self.teacher, 'text': self.LIB_TEXT, 'title': 'E&M Practice Test'})
        self.assertEqual((lib['title'], lib['count'], lib['subjects']), ('E&M Practice Test', 3, {'Magnetism': 2, 'Electricity': 1}))  # the one with no answer is reported, not saved
        self.assertTrue(lib['problems'])
        other = self.sign('other@wccusd.net', 'Other Teacher')
        self.assertEqual(game.dispatch('/api/library/list', {'userToken': other})['sets'], [])
        with self.assertRaises(accounts.AuthError): game.dispatch('/api/library/get', {'userToken': other, 'id': lib['id']})
        with self.assertRaises(accounts.AuthError): game.dispatch('/api/library/pack', {'userToken': other, 'ids': [lib['id']], 'subjects': ['Magnetism']})
        with self.assertRaises(accounts.AuthError): game.dispatch('/api/library/import', {'userToken': self.alex, 'text': 'x'})
        pack = game.dispatch('/api/library/pack', {'userToken': self.teacher, 'ids': [lib['id']], 'subjects': ['magnetism'], 'title': 'Magnetism only'})['pack']
        self.assertEqual([(t['name'], len(t['questions'])) for t in pack['topics']], [('Magnetism', 2)])
        room = game.dispatch('/api/create', {'userToken': self.teacher, 'classId': self.cls['id'], 'mode': 'coop', 'pack': pack})  # usable in a game
        self.assertTrue(room['code'])
        game.dispatch('/api/library/delete', {'userToken': self.teacher, 'id': lib['id']})
        self.assertEqual(game.dispatch('/api/library/list', {'userToken': self.teacher})['sets'], [])

    # --- nicknames
    def test_nicknames_are_suggested_edited_saved_and_used_in_games(self):
        member = self.api('/api/class/members', self.teacher, classId=self.cls['id'])['members'][0]
        self.assertEqual((member['nickname'], member['nickConfirmed']), ('Alexander', 0))
        result = self.api('/api/class/nicknames/suggest', self.teacher, classId=self.cls['id'])
        self.assertEqual((result['source'], result['suggestions'][0]['suggested']), ('guess', 'Alexander'))
        self.assertEqual(self.api('/api/class/members', self.teacher, classId=self.cls['id'])['members'][0]['nickname'], 'Alexander')  # suggesting saves nothing
        self.api('/api/class/nicknames/save', self.teacher, classId=self.cls['id'], nicknames={'alexander.smith@wccschools.org': '  Alex <b>'})
        member = self.api('/api/class/members', self.teacher, classId=self.cls['id'])['members'][0]
        self.assertEqual((member['nickname'], member['nickConfirmed']), ('Alex b', 1))
        self.api('/api/class/nicknames/save', self.teacher, classId=self.cls['id'], nicknames={'alexander.smith@wccschools.org': 'Alex'})
        room = self.make_room()
        self.assertEqual(self.join(self.alex, room['code'])['player']['name'], 'Alex')  # saved nickname is used in later sessions
        with self.assertRaises(accounts.AuthError): self.api('/api/class/nicknames/save', self.alex, classId=self.cls['id'], nicknames={})
        self.api('/api/class/nicknames/save', self.teacher, classId=self.cls['id'], nicknames={'alexander.smith@wccschools.org': ''})
        self.assertEqual(self.api('/api/class/members', self.teacher, classId=self.cls['id'])['members'][0]['nickConfirmed'], 0)

    def test_each_game_chooses_nicknames_or_anonymous_fun_names(self):
        self.api('/api/class/nicknames/save', self.teacher, classId=self.cls['id'], nicknames={'alexander.smith@wccschools.org': 'Alex'})
        real = self.make_room(autoNames=False); fun = self.make_room(autoNames=True)
        self.assertEqual(self.join(self.alex, real['code'])['player']['name'], 'Alex')
        fun_join = self.join(self.alex, fun['code']); fun_name = fun_join['player']['name']
        self.assertNotEqual(fun_name, 'Alex'); self.assertNotIn('Alex', fun_name)
        host = game.dispatch('/api/host', {'code': fun['code'], 'host': fun['host']})['room']
        self.assertEqual(list(host['hostIdentities'].values()), ['ALEXANDER SMITH'])  # only the teacher can map fun names to people
        self.assertNotIn('alexander', str(fun_join['room']).lower())

    # --- gating
    def test_games_require_sign_in_and_class_membership(self):
        room = self.make_room()
        with self.assertRaises(accounts.AuthError): game.dispatch('/api/join', {'code': room['code'], 'name': 'x'})
        stranger = self.sign('zed@wccschools.org', 'Zed')
        with self.assertRaises(game.GameError): self.join(stranger, room['code'])
        first = self.join(self.alex, room['code']); again = self.join(self.alex, room['code'])
        self.assertEqual(first['token'], again['token'])  # same student, same player, even from another device
        auth = {'code': room['code'], 'token': first['token']}
        game.dispatch('/api/state', auth)
        self.api('/api/class/remove', self.teacher, classId=self.cls['id'], email='alexander.smith@wccschools.org')
        with self.assertRaises(game.GameError): game.dispatch('/api/state', auth)  # removal cuts off existing games too
        with self.assertRaises(accounts.AuthError): game.dispatch('/api/create', {'userToken': self.alex, 'classId': self.cls['id'], 'mode': 'coop', 'pack': copy.deepcopy(game.BUILTIN)})

    def test_teacher_tools_need_teacher_session(self):
        with self.assertRaises(accounts.AuthError): game.dispatch('/api/parse', {'text': 'magnets'})
        with self.assertRaises(accounts.AuthError): game.dispatch('/api/parse', {'userToken': self.alex, 'text': 'magnets'})

    def test_bot_practice_bots_do_not_inherit_the_students_identity(self):
        with self.assertRaises(game.GameError): game.dispatch('/api/create', {'userToken': self.alex, 'classId': self.cls['id'], 'mode': 'impostorSolo', 'soloRole': 'crew', 'pack': copy.deepcopy(game.BUILTIN)})  # students cannot bring their own questions
        teacher_room = self.make_room()
        room = game.dispatch('/api/create', {'userToken': self.alex, 'classId': self.cls['id'], 'mode': 'impostorSolo', 'soloRole': 'crew', 'source': teacher_room['code']})
        first = self.join(self.alex, room['code']); again = self.join(self.alex, room['code'])
        self.assertEqual(first['token'], again['token'])
        self.assertEqual([p['name'] for p in game.ROOMS[room['code']]['players'].values() if p.get('email')], [first['player']['name']])

    def test_classroom_has_no_builtin_questions_and_needs_a_pack(self):
        self.assertIsNone(game.dispatch('/api/config', {})['builtin'])
        with self.assertRaises(game.GameError): game.dispatch('/api/create', {'userToken': self.teacher, 'classId': self.cls['id'], 'mode': 'coop'})
        accounts.MODE = 'off'
        self.assertTrue(game.dispatch('/api/config', {})['builtin'])  # the open demo keeps its sample

    def test_classes_are_off_unless_enabled(self):
        accounts.MODE = 'off'
        with self.assertRaises(game.GameError): game.dispatch('/api/class/list', {})

    # --- transcripts and safety
    def pick(self, auth, a, right=True):
        """Choose the right (or a wrong) button for the shuffled question on screen."""
        q = game.ROOMS[auth['code']]['pack']['topics'][a['topic']]['questions'][a['index']]
        idx = a['perm'].index(q['correct']); return idx if right else (idx + 1) % len(a['perm'])

    def answer(self, auth, right=True):
        a = game.get(auth)[1]['active']
        return game.dispatch('/api/chat', {**auth, 'challenge': a['id'], 'requestId': str(uuid.uuid4()), 'choice': self.pick(auth, a, right)})

    def chat_with_tutor(self, token_info, text=None, ai=None):
        p = game.ROOMS[token_info['code']]['players'][token_info['player']]
        p['x'], p['y'] = game.POSITIONS[0]
        auth = {'code': token_info['code'], 'token': token_info['token']}
        game.dispatch('/api/start', {**auth, 'topic': 0})
        return self.answer(auth)

    def student_in_room(self):
        room = self.make_room(autoNames=False); j = self.join(self.alex, room['code'])
        return {'code': room['code'], 'token': j['token'], 'player': j['player']['id']}

    def test_saved_game_summary_counts_rooms_not_every_question(self):
        # 3 rooms with 4 questions each: students answer 3 questions, so the list says 3, not 12
        topics = [{'name': f'Room {i}', 'questions': [{'prompt': 'Why?', 'answer': 'a', 'choices': ['x', 'y'], 'correct': 0}] * 4} for i in range(3)]
        saved = self.api('/api/pack/save', self.teacher, pack={'title': 'Magnets', 'grade': '9th grade', 'format': {'mc': True, 'free': False}, 'topics': topics,
                         'settings': {'mode': 'infiltration', 'roundSeconds': 600, 'followup': 20, 'bogus': 1}})
        p = self.api('/api/pack/list', self.teacher)['packs'][0]
        self.assertEqual((p['questions'], p['info']['required'], p['info']['pool']), (3, 3, 12))
        self.assertEqual((p['info']['answer'], p['info']['answerSeconds'], p['info']['mode'], p['info']['roundMinutes']), ('mc', 30, 'infiltration', 10))
        got = self.api('/api/pack/get', self.teacher, id=saved['id'])['pack']['settings']
        self.assertEqual(got, {'mode': 'infiltration', 'roundSeconds': 600, 'followup': 20})  # unknown keys dropped
        # re-saving without settings (a rebuilt question set) keeps the saved ones
        self.api('/api/pack/save', self.teacher, pack={'title': 'Magnets', 'topics': topics}, id=saved['id'])
        self.assertEqual(self.api('/api/pack/get', self.teacher, id=saved['id'])['pack']['settings']['mode'], 'infiltration')
        # settings never reach students in a live room
        room = self.api('/api/create', self.teacher, classId=self.cls['id'], mode='coop', pack=self.api('/api/pack/get', self.teacher, id=saved['id'])['pack'])
        self.assertNotIn('settings', game.ROOMS[room['code']]['pack'])

    def test_unlimited_time_is_saved_and_reaches_the_room(self):
        pack = {'title': 'Calm', 'topics': [{'name': 'Room', 'questions': [{'prompt': 'Why?', 'answer': 'a', 'choices': ['x', 'y'], 'correct': 0}]}], 'settings': {'unlimited': True}}
        saved = self.api('/api/pack/save', self.teacher, pack=pack)
        self.assertEqual(self.api('/api/pack/list', self.teacher)['packs'][0]['info']['answerSeconds'], 0)
        room = self.api('/api/create', self.teacher, classId=self.cls['id'], mode='coop', unlimited=True, pack=self.api('/api/pack/get', self.teacher, id=saved['id'])['pack'])
        self.assertTrue(game.ROOMS[room['code']]['unlimited'])
        normal = self.api('/api/create', self.teacher, classId=self.cls['id'], mode='coop', pack=pack)
        self.assertFalse(game.ROOMS[normal['code']]['unlimited'])

    def test_folders_nest_move_and_never_delete_games(self):
        a = self.api('/api/folder/create', self.teacher, name='  Physics  ')
        self.assertEqual(a['name'], 'Physics')
        b = self.api('/api/folder/create', self.teacher, name='Magnetism', parent=a['id'])
        pack = {'title': 'Circuits', 'topics': [{'name': 'Ohm', 'questions': [{'prompt': 'Why?', 'answer': 'a', 'choices': ['x', 'y'], 'correct': 0}]}]}
        g = self.api('/api/pack/save', self.teacher, pack=pack, folder=b['id'])  # new games land in the folder being viewed
        listed = self.api('/api/pack/list', self.teacher)
        self.assertEqual(listed['packs'][0]['folder'], b['id'])
        self.assertEqual({f['id']: f['parent'] for f in listed['folders']}, {a['id']: '', b['id']: a['id']})
        # a folder cannot go inside itself or its own subfolder
        for bad in (a['id'], b['id']):
            with self.assertRaises(accounts.AuthError): self.api('/api/folder/move', self.teacher, id=a['id'], parent=bad)
        # depth is limited
        parent = b['id']
        with self.assertRaises(accounts.AuthError):
            for i in range(10): parent = self.api('/api/folder/create', self.teacher, name=f'deep{i}', parent=parent)['id']
        # moving a game, and other teachers cannot see or use the folders
        self.api('/api/pack/move', self.teacher, id=g['id'], folder=a['id'])
        self.assertEqual(self.api('/api/pack/list', self.teacher)['packs'][0]['folder'], a['id'])
        other = self.sign('other@wccusd.net', 'Other Teacher')
        self.assertEqual(self.api('/api/pack/list', other)['folders'], [])
        with self.assertRaises(accounts.AuthError): self.api('/api/pack/move', other, id=g['id'], folder='')
        with self.assertRaises(accounts.AuthError): self.api('/api/folder/create', other, name='x', parent=a['id'])
        # deleting a folder keeps its games and subfolders, moving them up a level
        self.api('/api/pack/move', self.teacher, id=g['id'], folder=b['id'])
        self.api('/api/folder/delete', self.teacher, id=b['id'])
        after = self.api('/api/pack/list', self.teacher)
        self.assertEqual(after['packs'][0]['folder'], a['id'])
        self.api('/api/folder/delete', self.teacher, id=a['id'])
        self.assertEqual(self.api('/api/pack/list', self.teacher)['packs'][0]['folder'], '')
        self.assertNotIn(a['id'], [f['id'] for f in self.api('/api/pack/list', self.teacher)['folders']])

    def test_saved_packs_are_reusable_and_assignable(self):
        pack = {'title': 'Circuits', 'topics': [{'name': 'Ohm', 'questions': [{'prompt': 'Why?', 'answer': 'a', 'choices': ['x', 'y'], 'correct': 0}]}]}
        saved = self.api('/api/pack/save', self.teacher, pack=pack)
        listed = self.api('/api/pack/list', self.teacher)['packs']
        self.assertEqual([p['title'] for p in listed], ['Circuits']);self.assertEqual(listed[0]['questions'], 1)
        # a new pack is available to all of the teacher's classes by default, with no assigning needed
        self.assertTrue(listed[0]['allClasses'])
        self.assertEqual([p['title'] for p in self.api('/api/class/packs', self.alex, classId=self.cls['id'])['packs']], ['Circuits'])
        # the teacher can hide it on purpose: then students see nothing and cannot play it
        self.api('/api/pack/assign', self.teacher, id=saved['id'], classIds=[])
        self.assertEqual(self.api('/api/class/packs', self.alex, classId=self.cls['id'])['packs'], [])
        with self.assertRaises(accounts.AuthError): self.api('/api/create', self.alex, mode='solo', classId=self.cls['id'], packId=saved['id'])
        self.api('/api/pack/assign', self.teacher, id=saved['id'], classIds=[self.cls['id']])
        self.assertEqual([p['title'] for p in self.api('/api/class/packs', self.alex, classId=self.cls['id'])['packs']], ['Circuits'])
        room = self.api('/api/create', self.alex, mode='solo', classId=self.cls['id'], packId=saved['id'])
        self.assertTrue(room['code'])
        # another teacher cannot see, load, or assign it
        other = self.sign('other@wccusd.net', 'Other')
        self.assertEqual(self.api('/api/pack/list', other)['packs'], [])
        with self.assertRaises(accounts.AuthError): self.api('/api/pack/get', other, id=saved['id'])
        self.assertEqual(self.api('/api/pack/get', self.teacher, id=saved['id'])['pack']['title'], 'Circuits')
        self.api('/api/pack/delete', self.teacher, id=saved['id'])
        self.assertEqual(self.api('/api/pack/list', self.teacher)['packs'], [])

    # --- weekly homework
    def test_homework_credit_only_for_good_explanations_and_teacher_counts(self):
        pack = copy.deepcopy(game.BUILTIN); total = sum(len(x['questions']) for x in pack['topics'])
        pid = self.api('/api/pack/save', self.teacher, pack=pack)['id']
        hw = self.api('/api/hw/create', self.teacher, classId=self.cls['id'], packId=pid, title='Week 1', due=time.time() + 86400)
        with self.assertRaises(accounts.AuthError): self.api('/api/hw/create', self.alex, classId=self.cls['id'], packId=pid)
        mine = self.api('/api/hw/list', self.alex)['assignments']
        self.assertEqual((mine[0]['title'], mine[0]['total'], mine[0]['done']), ('Week 1', total, 0))
        # a student outside the class cannot start it
        outsider = self.sign('zed.zed@wccschools.org', 'ZED ZED')
        with self.assertRaises(accounts.AuthError): game.dispatch('/api/create', {'userToken': outsider, 'assignmentId': hw['id']})
        made = game.dispatch('/api/create', {'userToken': self.alex, 'assignmentId': hw['id']})
        joined = game.dispatch('/api/join', {'userToken': self.alex, 'code': made['code']})
        auth = {'userToken': self.alex, 'code': made['code'], 'token': joined['token']}
        self.assertEqual(game.ROOMS[made['code']]['gameType'], 'chat')
        done = lambda: game.dispatch('/api/hw/list', {'userToken': self.alex})['assignments'][0]['done']
        game.dispatch('/api/start', auth); self.answer(auth, right=False); self.assertEqual(done(), 0)  # a miss earns nothing
        game.get(auth)[1]['active'] = None
        game.dispatch('/api/start', auth); snap = self.answer(auth); self.assertEqual(done(), 1); self.assertEqual(snap['player']['hw']['done'], 1)
        game.get(auth)[1]['active'] = None
        rep = self.api('/api/hw/report', self.teacher, id=hw['id'])
        self.assertEqual((rep['students'][0]['done'], rep['total']), (1, total))
        self.api('/api/hw/adjust', self.teacher, id=hw['id'], email='alexander.smith@wccschools.org', delta=2, note='talked it through')
        self.assertEqual(self.api('/api/hw/report', self.teacher, id=hw['id'])['students'][0]['done'], 3)
        listing = self.api('/api/hw/list', self.teacher)['assignments'][0]
        self.assertEqual((listing['students'], listing['total']), (1, total))
        csv = self.api('/api/hw/export', self.teacher, classId=self.cls['id'])['csv']
        self.assertIn('Week 1', csv); self.assertIn('ALEXANDER SMITH', csv)
        with self.assertRaises(accounts.AuthError): self.api('/api/hw/report', self.alex, id=hw['id'])

    def test_homework_not_open_yet_and_deleted(self):
        pid = self.api('/api/pack/save', self.teacher, pack=copy.deepcopy(game.BUILTIN))['id']
        hw = self.api('/api/hw/create', self.teacher, classId=self.cls['id'], packId=pid, openAt=time.time() + 86400)
        self.assertEqual(self.api('/api/hw/list', self.alex)['assignments'], [])
        with self.assertRaises(accounts.AuthError): game.dispatch('/api/create', {'userToken': self.alex, 'assignmentId': hw['id']})
        self.api('/api/hw/delete', self.teacher, id=hw['id'])
        self.assertEqual(self.api('/api/hw/list', self.teacher)['assignments'], [])

    def test_homework_imposter_practice_asks_questions_without_credit(self):
        pid = self.api('/api/pack/save', self.teacher, pack=copy.deepcopy(game.BUILTIN))['id']
        hw = self.api('/api/hw/create', self.teacher, classId=self.cls['id'], packId=pid)
        for q in ('0:0', '1:1'): accounts.hw_credit(game.DB, 'alexander.smith@wccschools.org', hw['id'], q)
        made = game.dispatch('/api/create', {'userToken': self.alex, 'assignmentId': hw['id'], 'gameType': 'station'})
        r = game.ROOMS[made['code']]
        self.assertEqual((r['gameType'], r['mode'], r['assignmentId'] == hw['id'], bool(r.get('botPractice'))), ('station', 'infiltration', True, True))
        joined = game.dispatch('/api/join', {'userToken': self.alex, 'code': made['code']})
        me = game.get({'userToken': self.alex, 'code': made['code'], 'token': joined['token']})[1]
        self.assertNotIn('0:0', me['roundTasks']); self.assertNotIn('1:1', me['roundTasks'])

    def test_test_email_reports_honestly_and_resend_is_used_when_configured(self):
        r = self.api('/api/class/mailtest', self.teacher); self.assertFalse(r['ok']); self.assertIn('not set up', r['detail'])
        with self.assertRaises(accounts.AuthError): self.api('/api/class/mailtest', self.alex)
        sent = []
        class Resp:
            def __enter__(self): return self
            def __exit__(self, *a): return False
        def fake_urlopen(req, timeout=0):
            sent.append((req.full_url, req.get_header('Authorization'), json.loads(req.data)))
            return Resp()
        os.environ['RESEND_API_KEY'] = 're_test'; os.environ['ALERT_FROM'] = 'alerts@example.org'
        try:
            with patch.object(accounts, 'urlopen', fake_urlopen):
                r = self.api('/api/class/mailtest', self.teacher)
            self.assertTrue(r['ok']); self.assertEqual(sent[0][0], 'https://api.resend.com/emails')
            self.assertEqual((sent[0][1], sent[0][2]['to'], sent[0][2]['from']), ('Bearer re_test', ['teach@wccusd.net'], 'alerts@example.org'))
            self.assertNotIn('re_test', json.dumps(r))
        finally:
            os.environ.pop('RESEND_API_KEY', None); os.environ.pop('ALERT_FROM', None)


if __name__ == '__main__': unittest.main()
