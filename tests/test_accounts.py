import copy, os, sys, tempfile, time, unittest, uuid
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
        self.old = (game.DB, game.KEY, game.TEACHER_KEY, accounts.MODE, accounts.GOOGLE_CLIENT_ID, accounts.TEACHER_EMAILS, accounts.SYNC_EMAIL, accounts.PUBLIC_URL)
        game.DB = self.temp.name + '/t.sqlite3'; game.KEY = 'k'; game.TEACHER_KEY = ''; game.ROOMS.clear()
        accounts.MODE = 'classes'; accounts.GOOGLE_CLIENT_ID = 'cid'; accounts.SYNC_EMAIL = True; accounts.PUBLIC_URL = 'https://game.test'
        accounts.TEACHER_EMAILS = {'teach@wccusd.net', 'other@wccusd.net'}
        self.patches = [patch.object(accounts, 'verify_google', side_effect=fake_verify),
                        patch.object(game, 'ai', side_effect=lambda system, data, max_tokens=650: {'status': 'help', 'feedback': 'Tell me more. ⚡'})]
        for p in self.patches: p.start()
        for key in ('SMTP_HOST', 'SMTP_USER', 'SMTP_PASSWORD', 'ALERT_FROM'): os.environ.pop(key, None)
        self.teacher = self.sign('teach@wccusd.net', 'Ms Teach')
        self.cls = self.api('/api/class/create', self.teacher, name='Period 3', domains='wccschools.org')
        self.invite = self.api('/api/class/invite', self.teacher, classId=self.cls['id'])
        self.alex = self.sign('alexander.smith@wccschools.org', 'ALEXANDER SMITH')
        self.api('/api/class/join', self.alex, code=self.invite['code'])

    def tearDown(self):
        for p in self.patches: p.stop()
        (game.DB, game.KEY, game.TEACHER_KEY, accounts.MODE, accounts.GOOGLE_CLIENT_ID, accounts.TEACHER_EMAILS, accounts.SYNC_EMAIL, accounts.PUBLIC_URL) = self.old
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
        self.chat_with_tutor(info, 'I want to die')
        other = self.sign('other@wccusd.net', 'Other Teacher')
        with self.assertRaises(accounts.AuthError): self.api('/api/class/delete', other, classId=self.cls['id'])
        with self.assertRaises(accounts.AuthError): self.api('/api/class/delete', self.alex, classId=self.cls['id'])
        self.api('/api/class/delete', self.teacher, classId=self.cls['id'])
        self.assertEqual(self.api('/api/class/list', self.teacher)['classes'], [])
        self.assertEqual(self.api('/api/class/list', self.alex)['classes'], [])
        self.assertEqual(self.api('/api/class/alerts', self.teacher)['alerts'], [])
        with self.assertRaises(accounts.AuthError): self.api('/api/class/join', self.sign('mia@wccschools.org', 'Mia'), code=self.invite['code'])
        with self.assertRaises(game.GameError): game.dispatch('/api/state', {'code': info['code'], 'token': info['token']})

    # --- private question library
    LIB_AI = {'title': 'E&M Practice Test', 'questions': [
        {'subject': 'Magnetism', 'prompt': 'Why does a magnet attract a nail?', 'answer': 'Domains align.', 'hint': 'Think about tiny magnets.'},
        {'subject': 'Magnetism', 'prompt': 'What happens to a compass near a wire with current?', 'answer': 'It deflects.', 'hint': 'Current makes a field.'},
        {'subject': 'Electricity', 'prompt': 'Why do bulbs in a series circuit dim?', 'answer': 'Shared voltage.', 'hint': 'Count the paths.'},
        {'subject': 'Forces', 'prompt': '', 'answer': 'x', 'hint': 'x'}]}

    def test_library_is_private_and_builds_a_subject_only_pack(self):
        seen = {}
        def fake_ai(system, data, max_tokens=650): seen['system'] = system; return self.LIB_AI
        with patch.object(game, 'ai', side_effect=fake_ai):
            lib = game.dispatch('/api/library/import', {'userToken': self.teacher, 'text': 'MC test text'})
        self.assertEqual((lib['title'], lib['count'], lib['subjects']), ('E&M Practice Test', 3, {'Magnetism': 2, 'Electricity': 1}))  # blank question dropped
        self.assertIn('multiple-choice', seen['system'])
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
        seen = {}
        def fake_ai(system, data, max_tokens=650): seen.update(data); return {'suggestions': [{'id': 0, 'nickname': 'Alex'}]}
        with patch.object(game, 'ai', side_effect=fake_ai):
            result = self.api('/api/class/nicknames/suggest', self.teacher, classId=self.cls['id'])
        self.assertEqual((result['source'], result['suggestions'][0]['suggested']), ('ai', 'Alex'))
        self.assertNotIn('@', str(seen))  # no email addresses go to the model
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

    def test_ai_failure_falls_back_to_name_guesses(self):
        with patch.object(game, 'ai', side_effect=game.GameError('down')):
            result = self.api('/api/class/nicknames/suggest', self.teacher, classId=self.cls['id'])
        self.assertEqual((result['source'], result['suggestions'][0]['suggested']), ('guess', 'Alexander'))

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
        with self.assertRaises(accounts.AuthError): game.dispatch('/api/generate', {'text': 'magnets'})
        with self.assertRaises(accounts.AuthError): game.dispatch('/api/generate', {'userToken': self.alex, 'text': 'magnets'})

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

    def test_teacher_ai_helper_is_teacher_only_and_needs_a_message(self):
        with patch.object(game, 'ai', side_effect=lambda s, d, m=650: {'reply': 'Which topics?'}) as fake:
            r = game.dispatch('/api/assist', {'userToken': self.teacher, 'messages': [{'role': 'user', 'text': 'magnetism'}]})
            self.assertEqual(r['reply'], 'Which topics?')
            self.assertEqual(fake.call_args[0][1]['conversation'][0]['role'], 'teacher')
            with self.assertRaises(accounts.AuthError): game.dispatch('/api/assist', {'userToken': self.alex, 'messages': [{'role': 'user', 'text': 'hi'}]})
            with self.assertRaises(game.GameError): game.dispatch('/api/assist', {'userToken': self.teacher, 'messages': []})

    def test_classes_are_off_unless_enabled(self):
        accounts.MODE = 'off'
        with self.assertRaises(game.GameError): game.dispatch('/api/class/list', {})

    # --- transcripts and safety
    def chat_with_tutor(self, token_info, text, ai=None):
        p = game.ROOMS[token_info['code']]['players'][token_info['player']]
        p['x'], p['y'] = game.POSITIONS[0]
        auth = {'code': token_info['code'], 'token': token_info['token']}
        a = game.dispatch('/api/start', {**auth, 'topic': 0})['player']['active']
        call = lambda: game.dispatch('/api/chat', {**auth, 'challenge': a['id'], 'requestId': str(uuid.uuid4()), 'kind': 'answer', 'text': text})
        if ai:
            with patch.object(game, 'ai', side_effect=ai): return call()
        return call()

    def student_in_room(self):
        room = self.make_room(autoNames=False); j = self.join(self.alex, room['code'])
        return {'code': room['code'], 'token': j['token'], 'player': j['player']['id']}

    def test_chats_are_logged_for_the_teacher_even_when_the_tutor_fails(self):
        info = self.student_in_room()
        self.chat_with_tutor(info, 'Magnets attract because of domains')
        def broken(system, data, max_tokens=650): raise game.GameError('The AI could not respond.')
        with self.assertRaises(game.GameError): self.chat_with_tutor(info, 'my second try', ai=broken)
        convo = self.api('/api/class/transcript', self.teacher, classId=self.cls['id'], email='alexander.smith@wccschools.org')['conversations']
        roles = [(m['role'], m['text']) for c in convo for m in c['messages']]
        self.assertEqual(roles[0], ('student', 'Magnets attract because of domains')); self.assertEqual(roles[1][0], 'tutor')
        self.assertIn(('student', 'my second try'), roles)
        members = self.api('/api/class/members', self.teacher, classId=self.cls['id'])['members']
        self.assertEqual(members[0]['messages'], 2)

    def test_concerning_message_creates_alert_with_honest_delivery_status(self):
        info = self.student_in_room()
        self.chat_with_tutor(info, 'honestly I want to kill myself')
        alert = self.api('/api/class/alerts', self.teacher)['alerts'][0]
        self.assertEqual((alert['category'], alert['status']), ('self_harm', 'not_configured'))  # no SMTP: says so, never "sent"
        self.chat_with_tutor(info, 'I want to kill myself again')
        self.assertEqual(len(self.api('/api/class/alerts', self.teacher)['alerts']), 1)  # same student and category are grouped
        detail = self.api('/api/class/alert', self.teacher, alertId=alert['id'])
        self.assertEqual(detail['messages'][0]['flag'], 'self_harm')
        other = self.sign('other@wccusd.net', 'Other')
        with self.assertRaises(accounts.AuthError): self.api('/api/class/alert', other, alertId=alert['id'])
        self.api('/api/class/alert/review', self.teacher, alertId=alert['id'])
        self.assertEqual(self.api('/api/class/alerts', self.teacher)['alerts'][0]['reviewed'], 1)

    def test_science_talk_is_not_flagged_but_ai_classification_is(self):
        info = self.student_in_room()
        self.chat_with_tutor(info, 'you can kill the current by opening the switch')
        self.assertEqual(self.api('/api/class/alerts', self.teacher)['alerts'], [])
        self.chat_with_tutor(info, 'something the keyword list misses', ai=lambda s, d, m=650: {'status': 'help', 'feedback': 'Let us talk to your teacher.', 'safety': 'harm_to_others'})
        self.assertEqual(self.api('/api/class/alerts', self.teacher)['alerts'][0]['category'], 'harm_to_others')

    def test_alert_email_links_to_dashboard_without_message_text(self):
        sent = []
        class FakeSMTP:
            def __init__(self, host, port, timeout=0): sent.append(('connect', host, port))
            def starttls(self, context=None): pass
            def login(self, user, password): sent.append(('login', user))
            def send_message(self, msg): sent.append(('mail', msg))
            def __enter__(self): return self
            def __exit__(self, *a): return False
        os.environ.update(SMTP_HOST='smtp.test', SMTP_USER='alerts@school.test', SMTP_PASSWORD='s3cret', ALERT_FROM='alerts@school.test')
        info = self.student_in_room()
        with patch('accounts.smtplib.SMTP', FakeSMTP):
            self.chat_with_tutor(info, 'I wanna die and also my secret detail')
        msg = next(x[1] for x in sent if x[0] == 'mail')
        body = msg.get_content(); alert = self.api('/api/class/alerts', self.teacher)['alerts'][0]
        self.assertEqual(msg['To'], 'teach@wccusd.net'); self.assertIn(f'https://game.test/?alert={alert["id"]}', body)
        self.assertNotIn('secret detail', body); self.assertEqual(alert['status'], 'sent')

    def test_failed_email_is_reported_without_leaking_credentials(self):
        class Broken:
            def __init__(self, *a, **k): raise OSError('connection refused for s3cret')
        os.environ.update(SMTP_HOST='smtp.test', SMTP_USER='u', SMTP_PASSWORD='s3cret')
        info = self.student_in_room()
        with patch('accounts.smtplib.SMTP', Broken):
            self.chat_with_tutor(info, 'I want to die')
        alert = self.api('/api/class/alerts', self.teacher)['alerts'][0]
        self.assertEqual(alert['status'], 'failed'); self.assertNotIn('s3cret', alert['detail'])
        with patch.object(accounts, 'send_alert') as retry:
            self.api('/api/class/alert/retry', self.teacher, alertId=alert['id']); retry.assert_called_once()


    def test_saved_packs_are_reusable_and_assignable(self):
        pack = {'title': 'Circuits', 'topics': [{'name': 'Ohm', 'questions': [{'prompt': 'Why?', 'answer': 'a', 'hint': 'h'}]}]}
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


if __name__ == '__main__': unittest.main()
