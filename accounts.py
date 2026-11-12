"""Teacher/student accounts, classes, invitations, chat transcripts and safety alerts.

Standard library only. Everything here is off unless AUTH_MODE=classes, so one
codebase can serve both a classroom deployment (students must sign in with a school
Google account and belong to a class) and an open demo deployment.

Privacy rules this module enforces:
- A teacher can only see classes, students, transcripts and alerts of classes they own.
- Students join only through a teacher's invite link, and only with an allowed email domain.
- Alert emails never contain student message text; they link back to the signed-in dashboard.
"""
import json
import os
import re
import secrets
import smtplib
import sqlite3
import ssl
import threading
import time
from contextlib import contextmanager
from email.message import EmailMessage
from urllib.parse import quote
from urllib.error import HTTPError
from urllib.request import Request, urlopen


class AuthError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _names(var):
    return {x.strip().lower().lstrip('@') for x in os.environ.get(var, '').split(',') if x.strip()}


MODE = os.environ.get('AUTH_MODE', 'off')  # 'classes' turns on sign-in and classes
GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', '')
TEACHER_EMAILS = _names('TEACHER_EMAILS')  # exact addresses allowed to be teachers
TEACHER_DOMAINS = _names('TEACHER_DOMAINS')  # whole domains allowed to be teachers
OPEN_TEACHER_SIGNUP = os.environ.get('OPEN_TEACHER_SIGNUP') == '1'  # any Google Workspace account may teach
DEFAULT_STUDENT_DOMAINS = sorted(_names('DEFAULT_STUDENT_DOMAINS'))
PUBLIC_URL = os.environ.get('PUBLIC_URL', '').rstrip('/')
SESSION_SECONDS = 12 * 3600
ALERT_DEDUPE_SECONDS = 600
SYNC_EMAIL = False  # tests set this so alert email is sent before the call returns

LOCK = threading.RLock()
CATEGORIES = {'self_harm': 'Possible self-harm concern', 'harm_to_others': 'Possible threat to others',
              'inappropriate': 'Inappropriate language'}

SCHEMA = '''
create table if not exists users (email text primary key, name text, role text, created real);
create table if not exists sessions (token text primary key, email text, expires real);
create table if not exists classes (id text primary key, teacher text, name text, domains text, created real, archived integer default 0);
create table if not exists members (class_id text, email text, name text, joined real, removed integer default 0, nickname text, nick_confirmed integer default 0, primary key (class_id, email));
create table if not exists invites (code text primary key, class_id text, expires real, uses integer default 0, max_uses integer default 0, revoked integer default 0);
create table if not exists messages (id integer primary key autoincrement, class_id text, room text, email text, name text, qid text, topic text, role text, text text, ts real, flag text);
create table if not exists packs (id text primary key, teacher text, title text, created real, data text, classes text default '[]');
create table if not exists folders (id text primary key, teacher text, name text, parent text default '', created real);
create table if not exists rounds (id integer primary key autoincrement, at real, code text, winner text, how text, players integer, impostors integer, seconds integer, tags integer, meetings integer, ejected integer, done integer, total integer, target integer, practice integer, meeting_seconds integer, round_seconds integer);
create table if not exists library (id text primary key, teacher text, title text, created real, questions text);
create table if not exists alerts (id text primary key, class_id text, teacher text, student_email text, student_name text, category text, message_id integer, created real, status text, detail text, reviewed integer default 0);
create table if not exists assignments (id text primary key, class_id text, teacher text, pack_id text, title text, open_at real, due real, created real, deleted integer default 0);
create table if not exists hw_credit (assignment_id text, email text, qid text, at real, primary key (assignment_id, email, qid));
create table if not exists hw_adjust (assignment_id text, email text, delta integer default 0, note text default '', primary key (assignment_id, email));
create index if not exists messages_student on messages (class_id, email, id);
'''


def enabled():
    return MODE == 'classes'


def public_config():
    return {'authMode': MODE, 'googleClientId': GOOGLE_CLIENT_ID if enabled() else '',
            'defaultStudentDomains': DEFAULT_STUDENT_DOMAINS}


@contextmanager
def tx(db):
    with LOCK:
        conn = sqlite3.connect(db, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            conn.executescript(SCHEMA)
            if not any(r['name'] == 'folder' for r in conn.execute('pragma table_info(packs)')):
                conn.execute("alter table packs add column folder text default ''")  # saved games can live in a folder
            yield conn
            conn.commit()
        finally:
            conn.close()


# ---------------------------------------------------------------- sign-in

def verify_google(credential):
    """Validate a Google ID token with Google and return {'email','name','hd'}."""
    if not GOOGLE_CLIENT_ID:
        raise AuthError('Google sign-in is not configured on this server yet.')
    try:
        info = json.load(urlopen('https://oauth2.googleapis.com/tokeninfo?id_token=' + quote(credential), timeout=10))
    except Exception:
        raise AuthError('Google could not verify this sign-in. Please try again.', 401)
    valid = (info.get('aud') == GOOGLE_CLIENT_ID
             and info.get('iss') in ('accounts.google.com', 'https://accounts.google.com')
             and str(info.get('email_verified')).lower() == 'true'
             and float(info.get('exp', 0)) > time.time() and info.get('email'))
    if not valid:
        raise AuthError('This Google sign-in is not valid for this app.', 401)
    email = info['email'].lower()
    return {'email': email, 'name': (info.get('name') or email.split('@')[0])[:80], 'hd': (info.get('hd') or '').lower()}


def role_for(info):
    email = info['email']
    if email in TEACHER_EMAILS or email.split('@')[-1] in TEACHER_DOMAINS or (OPEN_TEACHER_SIGNUP and info.get('hd')):
        return 'teacher'
    return 'student'


def sign_in(db, credential):
    if not credential:
        raise AuthError('Sign in with your school Google account.', 401)
    info = verify_google(credential)
    role = role_for(info)
    token = secrets.token_urlsafe(32)
    now = time.time()
    with tx(db) as c:
        c.execute('insert into users (email,name,role,created) values (?,?,?,?) '
                  'on conflict(email) do update set name=excluded.name, role=excluded.role',
                  (info['email'], info['name'], role, now))
        c.execute('delete from sessions where expires<?', (now,))
        c.execute('insert into sessions values (?,?,?)', (token, info['email'], now + SESSION_SECONDS))
    user = {'email': info['email'], 'name': info['name'], 'role': role}
    return {'userToken': token, 'user': user, 'classes': class_list(db, user)}


def sign_out(db, token):
    with tx(db) as c:
        c.execute('delete from sessions where token=?', (token,))


def user_for(db, d):
    token = str(d.get('userToken', ''))
    if not token:
        raise AuthError('Please sign in with your school Google account.', 401)
    with tx(db) as c:
        row = c.execute('select u.email,u.name,u.role from sessions s join users u on u.email=s.email '
                        'where s.token=? and s.expires>?', (token, time.time())).fetchone()
    if not row:
        raise AuthError('Your sign-in expired. Please sign in again.', 401)
    return dict(row)


def need_teacher(user):
    if user['role'] != 'teacher':
        raise AuthError('Only teachers can do that.', 403)


# ---------------------------------------------------------------- classes

def _owned(c, user, class_id):
    need_teacher(user)
    row = c.execute('select * from classes where id=? and teacher=? and archived=0', (str(class_id), user['email'])).fetchone()
    if not row:  # same message whether the class is missing or belongs to someone else
        raise AuthError('Class not found.', 404)
    return row


def clean_domains(raw):
    if isinstance(raw, str):
        raw = re.split(r'[,\s]+', raw)
    domains = []
    for item in raw or []:
        item = str(item).strip().lower().lstrip('@')
        if not item:
            continue
        if not re.fullmatch(r'[a-z0-9-]+(\.[a-z0-9-]+)+', item):
            raise AuthError(f'"{item}" is not a valid email domain.')
        if item not in domains:
            domains.append(item)
    if not 1 <= len(domains) <= 5:
        raise AuthError('Choose which student email domain(s) may join, for example wccschools.org.')
    return domains


def class_create(db, user, name, domains):
    need_teacher(user)
    name = str(name or '').strip()[:80]
    if not name:
        raise AuthError('Give the class a name.')
    domains = clean_domains(domains)
    class_id = secrets.token_hex(6)
    with tx(db) as c:
        c.execute('insert into classes (id,teacher,name,domains,created) values (?,?,?,?,?)',
                  (class_id, user['email'], name, json.dumps(domains), time.time()))
    return {'id': class_id, 'name': name, 'domains': domains}


def class_list(db, user):
    with tx(db) as c:
        if user['role'] == 'teacher':
            rows = c.execute(
                'select c.id,c.name,c.domains,c.created,'
                '(select count(*) from members m where m.class_id=c.id and m.removed=0) as students,'
                '(select count(*) from alerts a where a.class_id=c.id and a.reviewed=0) as openAlerts '
                'from classes c where c.teacher=? and c.archived=0 order by c.created desc', (user['email'],)).fetchall()
            return [{**dict(r), 'domains': json.loads(r['domains'])} for r in rows]
        rows = c.execute(
            'select c.id,c.name,u.name as teacher from members m join classes c on c.id=m.class_id '
            'left join users u on u.email=c.teacher where m.email=? and m.removed=0 and c.archived=0 '
            'order by m.joined desc', (user['email'],)).fetchall()
        return [dict(r) for r in rows]


def has_access(db, email, class_id):
    """True for the class's teacher and for active student members."""
    with tx(db) as c:
        row = c.execute(
            'select 1 from classes c where c.id=? and c.archived=0 and (c.teacher=? or exists '
            '(select 1 from members m where m.class_id=c.id and m.email=? and m.removed=0))',
            (str(class_id), email, email)).fetchone()
    return bool(row)


def is_owner(db, email, class_id):
    with tx(db) as c:
        return bool(c.execute('select 1 from classes where id=? and teacher=? and archived=0', (str(class_id), email)).fetchone())


def invite_create(db, user, class_id, days=14, max_uses=0):
    days = max(1, min(60, int(days or 14)))
    max_uses = max(0, min(500, int(max_uses or 0)))
    code = secrets.token_urlsafe(9)
    expires = time.time() + days * 86400
    with tx(db) as c:
        _owned(c, user, class_id)
        c.execute('insert into invites (code,class_id,expires,max_uses) values (?,?,?,?)', (code, str(class_id), expires, max_uses))
    return {'code': code, 'url': f'{PUBLIC_URL}/?join={code}' if PUBLIC_URL else f'/?join={code}', 'expires': expires}


def class_delete(db, user, class_id):
    """Permanently delete a class and everything stored for it (students, invites, chats, alerts)."""
    with tx(db) as c:
        _owned(c, user, class_id)
        for table in ('members', 'invites', 'messages', 'alerts'):
            c.execute(f'delete from {table} where class_id=?', (str(class_id),))
        c.execute('delete from classes where id=?', (str(class_id),))
    return {'ok': True}


def invite_revoke(db, user, class_id):
    with tx(db) as c:
        _owned(c, user, class_id)
        c.execute('update invites set revoked=1 where class_id=?', (str(class_id),))
    return {'ok': True}


def join_class(db, user, code):
    if user['role'] == 'teacher':
        raise AuthError('Teachers manage classes from the class dashboard. Open this link as a student to try it.', 403)
    with tx(db) as c:
        inv = c.execute('select * from invites where code=?', (str(code),)).fetchone()
        bad = AuthError('This invite link is not valid anymore. Ask your teacher for a new one.', 404)
        if not inv or inv['revoked'] or inv['expires'] < time.time():
            raise bad
        cls = c.execute('select * from classes where id=? and archived=0', (inv['class_id'],)).fetchone()
        if not cls:
            raise bad
        domains = json.loads(cls['domains'])
        if user['email'].split('@')[-1] not in domains:
            raise AuthError(f'This class accepts {", ".join("@" + d for d in domains)} accounts. '
                            f'You are signed in as {user["email"]}.', 403)
        row = c.execute('select removed from members where class_id=? and email=?', (cls['id'], user['email'])).fetchone()
        if row and row['removed']:
            raise AuthError('Your teacher removed you from this class. Ask them to add you back.', 403)
        if not row:
            if inv['max_uses'] and inv['uses'] >= inv['max_uses']:
                raise bad
            c.execute('insert into members (class_id,email,name,joined,nickname) values (?,?,?,?,?)',
                      (cls['id'], user['email'], user['name'], time.time(), guess_nickname(user['name'])))
            c.execute('update invites set uses=uses+1 where code=?', (inv['code'],))
    return {'id': cls['id'], 'name': cls['name']}


def members(db, user, class_id):
    with tx(db) as c:
        _owned(c, user, class_id)
        rows = c.execute(
            'select m.email,m.name,m.nickname,m.nick_confirmed as nickConfirmed,m.joined,m.removed,'
            '(select count(*) from messages g where g.class_id=m.class_id and g.email=m.email and g.role=\'student\') as messages,'
            '(select count(*) from messages g where g.class_id=m.class_id and g.email=m.email and g.flag is not null) as flagged,'
            '(select max(ts) from messages g where g.class_id=m.class_id and g.email=m.email) as lastActive '
            'from members m where m.class_id=? order by m.removed, lower(m.name)', (str(class_id),)).fetchall()
    return [dict(r) for r in rows]


def set_removed(db, user, class_id, email, removed):
    with tx(db) as c:
        _owned(c, user, class_id)
        c.execute('update members set removed=? where class_id=? and email=?', (1 if removed else 0, str(class_id), str(email).lower()))
    return {'ok': True}


# ---------------------------------------------------------------- nicknames

def clean_nickname(text):
    text = re.sub(r'[\x00-\x1f<>&"`]', '', str(text or '')).strip()
    return re.sub(r'\s+', ' ', text)[:24]


def guess_nickname(full_name):
    """Fallback guess: the given name. The teacher (or the AI suggestion) can improve it."""
    first = (str(full_name or '').split() or [''])[0]
    first = clean_nickname(first)
    return first.title() if first.isupper() or first.islower() else first


def save_nicknames(db, user, class_id, nicknames):
    """Teacher-edited nicknames; saved for the class so future games use them."""
    if not isinstance(nicknames, dict):
        raise AuthError('Nothing to save.')
    with tx(db) as c:
        _owned(c, user, class_id)
        for email, nick in nicknames.items():
            email = str(email).lower()
            row = c.execute('select name from members where class_id=? and email=?', (str(class_id), email)).fetchone()
            if not row:
                continue
            nick = clean_nickname(nick)
            if nick:
                c.execute('update members set nickname=?, nick_confirmed=1 where class_id=? and email=?', (nick, str(class_id), email))
            else:  # blank resets to the automatic guess
                c.execute('update members set nickname=?, nick_confirmed=0 where class_id=? and email=?',
                          (guess_nickname(row['name']), str(class_id), email))
    return {'ok': True}


def suggest_nicknames(db, user, class_id, ask=None):
    """Propose nicknames for students the teacher has not confirmed yet. Nothing is saved.

    Plain guesses from the display name, such as the first name.
    """
    with tx(db) as c:
        _owned(c, user, class_id)
        rows = c.execute('select email,name,nickname from members where class_id=? and removed=0 and nick_confirmed=0 order by lower(name)',
                         (str(class_id),)).fetchall()
    items = [{'email': r['email'], 'name': r['name'], 'current': r['nickname'] or guess_nickname(r['name'])} for r in rows]
    suggestions = {i: guess_nickname(x['name']) for i, x in enumerate(items)}
    source = 'guess'
    return {'source': source, 'suggestions': [{**x, 'suggested': suggestions[i]} for i, x in enumerate(items)]}


def game_name(db, email, class_id, fallback='Explorer'):
    """The name a student plays under when the teacher chose class nicknames."""
    with tx(db) as c:
        row = c.execute('select name,nickname from members where class_id=? and email=?', (str(class_id), email)).fetchone()
        if not row:  # the teacher playing in their own class
            row = c.execute('select name,name as nickname from users where email=?', (email,)).fetchone()
    if not row:
        return fallback
    return clean_nickname(row['nickname']) or guess_nickname(row['name']) or fallback


# ---------------------------------------------------------------- transcripts

def log_message(db, class_id, room, email, name, qid, topic, role, text):
    with tx(db) as c:
        cur = c.execute('insert into messages (class_id,room,email,name,qid,topic,role,text,ts) values (?,?,?,?,?,?,?,?,?)',
                        (class_id, room, email, name, qid, topic, role, str(text)[:4000], time.time()))
        return cur.lastrowid


def transcript(db, user, class_id, email):
    with tx(db) as c:
        _owned(c, user, class_id)
        rows = c.execute('select id,room,qid,topic,role,text,ts,flag from messages where class_id=? and email=? order by id',
                         (str(class_id), str(email).lower())).fetchall()
    groups, index = [], {}
    for r in rows:
        key = (r['room'], r['qid'])
        if key not in index:
            index[key] = {'room': r['room'], 'qid': r['qid'], 'topic': r['topic'], 'messages': []}
            groups.append(index[key])
        index[key]['messages'].append({k: r[k] for k in ('id', 'role', 'text', 'ts', 'flag')})
    return groups


# ---------------------------------------------------------------- safety

SELF_HARM = re.compile(r"\b(kill(ing)? myself|end(ing)? my life|want to die|wanna die|suicid\w*|hurt(ing)? myself|"
                       r"cut(ting)? myself|harm(ing)? myself|(don'?t|do not) want to (live|be alive)|better off dead)\b", re.I)
HARM_OTHERS = re.compile(r"\b(kill (him|her|them|you|everyone|everybody|someone|people)|shoot (up )?(the |this )?"
                         r"(school|class|people|everyone)|bring a (gun|knife) to school|bomb (threat|the school)|"
                         r"(going|gonna) to hurt (him|her|them|you|someone))\b", re.I)
PROFANITY = re.compile(r"\b(fuck\w*|shit\w*|bitch\w*|asshole|cunt)\b", re.I)


def screen(text):
    """Cheap local backstop. The tutor model also classifies each message in context."""
    text = str(text or '')
    if SELF_HARM.search(text):
        return 'self_harm'
    if HARM_OTHERS.search(text):
        return 'harm_to_others'
    if PROFANITY.search(text):
        return 'inappropriate'
    return None


def mark_message(db, message_id, label):
    """Label a message for the teacher (for example 'pasted') without opening a safety alert."""
    with tx(db) as c:
        c.execute('update messages set flag=? where id=? and flag is null', (label, message_id))


def flag_message(db, class_id, message_id, email, name, category):
    """Mark a message and open an alert (unless the same student/category was alerted recently)."""
    if category not in CATEGORIES:
        return None
    now = time.time()
    with tx(db) as c:
        c.execute('update messages set flag=? where id=? and (flag is null or flag=\'inappropriate\')', (category, message_id))
        cls = c.execute('select teacher from classes where id=?', (class_id,)).fetchone()
        if not cls:
            return None
        recent = c.execute('select 1 from alerts where class_id=? and student_email=? and category=? and created>?',
                           (class_id, email, category, now - ALERT_DEDUPE_SECONDS)).fetchone()
        if recent:
            return None
        alert_id = secrets.token_urlsafe(8)
        c.execute('insert into alerts (id,class_id,teacher,student_email,student_name,category,message_id,created,status,detail) '
                  'values (?,?,?,?,?,?,?,?,?,?)',
                  (alert_id, class_id, cls['teacher'], email, name, category, message_id, now, 'queued', ''))
    if SYNC_EMAIL:
        send_alert(db, alert_id)
    else:
        threading.Thread(target=send_alert, args=(db, alert_id), daemon=True).start()
    return alert_id


def _set_status(db, alert_id, status, detail=''):
    with tx(db) as c:
        c.execute('update alerts set status=?, detail=? where id=?', (status, detail[:300], alert_id))


def mail_configured():
    return bool(os.environ.get('RESEND_API_KEY') or os.environ.get('SMTP_HOST'))


def send_mail(to, subject, body):
    """Send one plain-text email. Returns (ok, detail). Uses Resend over HTTPS when RESEND_API_KEY is set (works on hosts that block
    SMTP ports), otherwise SMTP. Credentials never appear in the returned detail."""
    sender = os.environ.get('ALERT_FROM') or os.environ.get('SMTP_USER', '')
    key = os.environ.get('RESEND_API_KEY', '')
    if key:
        if not sender:
            return False, 'Set ALERT_FROM to an address on your verified sending domain.'
        req = Request('https://api.resend.com/emails', method='POST',
                      data=json.dumps({'from': sender, 'to': [to], 'subject': subject, 'text': body}).encode(),
                      headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json', 'User-Agent': 'imposter-classroom/1.0'})
        try:
            with urlopen(req, timeout=20):
                pass
            return True, f'Emailed {to}'
        except HTTPError as exc:
            try:
                why = json.loads(exc.read().decode()).get('message', '')
            except Exception:
                why = ''
            return False, f'The email service refused it ({exc.code}). {why}'[:300]
        except Exception as exc:
            return False, f'{type(exc).__name__}: could not reach the email service.'
    host = os.environ.get('SMTP_HOST', '')
    if not host:
        return False, 'not_configured'
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = sender
    msg['To'] = to
    msg.set_content(body)
    try:
        port = int(os.environ.get('SMTP_PORT', '587'))
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=20, context=ssl.create_default_context())
        else:
            server = smtplib.SMTP(host, port, timeout=20)
            server.starttls(context=ssl.create_default_context())
        with server:
            if os.environ.get('SMTP_USER'):
                server.login(os.environ['SMTP_USER'], os.environ.get('SMTP_PASSWORD', ''))
            server.send_message(msg)
        return True, f'Emailed {to}'
    except Exception as exc:  # never include credentials in the stored detail
        return False, f'{type(exc).__name__}: email could not be sent. Check the mail settings (some hosts block SMTP; try RESEND_API_KEY).'


def send_alert(db, alert_id):
    """Send the alert email and record an honest delivery status."""
    with tx(db) as c:
        row = c.execute('select a.*, c.name as class_name from alerts a join classes c on c.id=a.class_id where a.id=?', (alert_id,)).fetchone()
    if not row:
        return
    if not mail_configured():
        _set_status(db, alert_id, 'not_configured', 'Email is not set up on this server. The alert is still in your dashboard.')
        return
    link = f'{PUBLIC_URL}/?alert={alert_id}' if PUBLIC_URL else None
    body = (f'{CATEGORIES[row["category"]]} in your class "{row["class_name"]}".\n\n'
            f'Student: {row["student_name"]} ({row["student_email"]})\n\n'
            + (f'Review the conversation (sign in with your teacher account):\n{link}\n' if link else
               'Sign in to the Imposter class dashboard to review the conversation.\n')
            + '\nThis automated check can be wrong. Please read the conversation before acting. '
              'The message text is not included in this email to protect student privacy.\n')
    ok, detail = send_mail(row['teacher'], f'Imposter safety alert: {row["class_name"]}', body)
    _set_status(db, alert_id, 'sent' if ok else 'failed', detail)


def mail_test(db, user):
    """Teachers can send themselves a test message to find out whether alert emails will actually arrive."""
    need_teacher(user)
    if not mail_configured():
        return {'ok': False, 'detail': 'Email is not set up on this server yet, so alerts only appear in your dashboard.'}
    ok, detail = send_mail(user['email'], 'Imposter test email',
                           'This is a test from your Imposter site. If you can read this, safety alerts will reach this address.\n')
    return {'ok': ok, 'detail': detail}


def alerts_list(db, user):
    need_teacher(user)
    with tx(db) as c:
        rows = c.execute('select a.id,a.class_id,c.name as class_name,a.student_email,a.student_name,a.category,a.created,'
                         'a.status,a.detail,a.reviewed from alerts a join classes c on c.id=a.class_id '
                         'where a.teacher=? order by a.created desc limit 100', (user['email'],)).fetchall()
    return [{**dict(r), 'label': CATEGORIES.get(r['category'], r['category'])} for r in rows]


def alert_detail(db, user, alert_id):
    need_teacher(user)
    with tx(db) as c:
        a = c.execute('select * from alerts where id=? and teacher=?', (str(alert_id), user['email'])).fetchone()
        if not a:
            raise AuthError('Alert not found.', 404)
        row = c.execute('select room,qid from messages where id=?', (a['message_id'],)).fetchone()
        context = []
        if row:
            context = [dict(r) for r in c.execute(
                'select id,role,text,ts,flag from messages where class_id=? and email=? and room=? and qid=? order by id',
                (a['class_id'], a['student_email'], row['room'], row['qid'])).fetchall()]
    return {'alert': {k: a[k] for k in ('id', 'class_id', 'student_email', 'student_name', 'category', 'created', 'status', 'detail', 'reviewed')},
            'label': CATEGORIES.get(a['category']), 'messageId': a['message_id'], 'messages': context}


def alert_review(db, user, alert_id):
    need_teacher(user)
    with tx(db) as c:
        c.execute('update alerts set reviewed=1 where id=? and teacher=?', (str(alert_id), user['email']))
    return {'ok': True}


def alert_retry(db, user, alert_id):
    need_teacher(user)
    with tx(db) as c:
        if not c.execute('select 1 from alerts where id=? and teacher=?', (str(alert_id), user['email'])).fetchone():
            raise AuthError('Alert not found.', 404)
    send_alert(db, str(alert_id))
    return {'ok': True}


# ---------------------------------------------------------------- saved game packs

def _pack_class_ids(r):
    """None means every class of the pack's teacher (the default); otherwise the explicit list ('-' = none on purpose)."""
    raw = json.loads(r['classes'] or '[]')
    return None if not raw else [i for i in raw if i != '-']


def _pack_in_class(r, class_id, class_teacher):
    ids = _pack_class_ids(r)
    return class_teacher == r['teacher'] if ids is None else str(class_id) in ids


MAX_ROOMS = 7  # a game has at most this many rooms; students answer one question in each
MC_SECONDS, FREE_SECONDS = 30, 60  # per-question answer time; keep in step with think_seconds() in server.py


def _clean_settings(s):
    """The game settings saved with a pack, so the teacher can see them in the list and reuse them. Unknown keys are dropped."""
    if not isinstance(s, dict):
        return {}

    def num(k, lo, hi):
        try:
            return max(lo, min(hi, int(s[k])))
        except (KeyError, TypeError, ValueError):
            return None
    out = {}
    if s.get('gameType') in ('station', 'climb'):
        out['gameType'] = s['gameType']
    if s.get('mode') in ('infiltration', 'coop', 'race'):
        out['mode'] = s['mode']
    for k, lo, hi in (('followup', 10, 30), ('roundSeconds', 0, 3600), ('crewTargetPct', 50, 100), ('meetingSeconds', 0, 900),
                      ('discussionSeconds', 15, 180), ('voteSeconds', 15, 300), ('briefingSeconds', 10, 120)):
        v = num(k, lo, hi)
        if v is not None:
            out[k] = v
    if s.get('tagDelay') == 'auto':
        out['tagDelay'] = 'auto'
    elif num('tagDelay', 0, 60) is not None:
        out['tagDelay'] = num('tagDelay', 0, 60)
    for k in ('interruptChats', 'writtenDiscussion', 'autoNames', 'allowStudy', 'unlimited'):
        if isinstance(s.get(k), bool):
            out[k] = s[k]
    return out


def _pack_info(data):
    """What a teacher wants to see at a glance. 'required' is the number of rooms, which is how many questions each student
    must answer; the pack holds several questions per room (and number variants) so students do not all get the same one."""
    topics = data.get('topics', [])
    kind = 'mc'
    s = data.get('settings') or {}
    return {'required': min(MAX_ROOMS, len(topics)), 'pool': sum(len(t.get('questions', [])) for t in topics),
            'answer': kind, 'answerSeconds': 0 if s.get('unlimited') else MC_SECONDS if kind == 'mc' else FREE_SECONDS,
            'mode': s.get('mode') or '', 'roundMinutes': round(s.get('roundSeconds', 0) / 60) if s.get('roundSeconds') else 0,
            'hasSettings': bool(s)}


def _pack_summary(r, class_names=None):
    data = json.loads(r['data'])
    ids = _pack_class_ids(r)
    every = ids is None
    if every:
        ids = list((class_names or {}).keys())
    info = _pack_info(data)
    return {'allClasses': every, 'id': r['id'], 'title': r['title'], 'created': r['created'],
            'topics': len(data.get('topics', [])), 'questions': info['required'], 'info': info,
            'folder': (r['folder'] if 'folder' in r.keys() else '') or '',
            'grade': str(data.get('grade') or '')[:30],
            'classes': [{'id': i, 'name': (class_names or {}).get(i, '')} for i in ids]}


def pack_save(db, user, pack, pack_id=None, folder=None):
    need_teacher(user)
    settings = _clean_settings(pack['settings']) if isinstance(pack.get('settings'), dict) else None
    title = str(pack.get('title') or 'My game')[:100]
    pack = {k: v for k, v in pack.items() if k != 'settings'}
    with tx(db) as c:
        if folder and not c.execute('select 1 from folders where id=? and teacher=?', (str(folder), user['email'])).fetchone():
            folder = ''  # the folder is gone: save at the top level instead of failing
        if pack_id:
            r = c.execute('select id, data from packs where id=? and teacher=?', (str(pack_id), user['email'])).fetchone()
            if not r:
                raise AuthError('Saved game not found.', 404)
            # a re-save that carries no settings (for example a rebuilt question set) keeps the ones already saved
            kept = json.loads(r['data']).get('settings') if settings is None else settings
            pack = {**pack, 'settings': kept or {}}
            c.execute('update packs set title=?, data=? where id=?', (title, json.dumps(pack), r['id']))
            new_id = r['id']
        else:
            if c.execute('select count(*) n from packs where teacher=?', (user['email'],)).fetchone()['n'] >= 200:
                raise AuthError('You have 200 saved games. Delete some first.')
            new_id = secrets.token_hex(6)
            pack = {**pack, 'settings': settings or {}}
            c.execute('insert into packs (id, teacher, title, created, data, classes, folder) values (?,?,?,?,?,?,?)',
                      (new_id, user['email'], title, time.time(), json.dumps(pack), '[]', str(folder or '')))
    return {'id': new_id, 'title': title}


def pack_list(db, user):
    need_teacher(user)
    with tx(db) as c:
        names = {r['id']: r['name'] for r in c.execute('select id,name from classes where teacher=? and archived=0', (user['email'],))}
        rows = c.execute('select * from packs where teacher=? order by created desc', (user['email'],)).fetchall()
    out = []
    for r in rows:
        s = _pack_summary(r, names)
        s['classes'] = [x for x in s['classes'] if x['id'] in names]
        out.append(s)
    return out


# ---------------------------------------------------------------- folders for saved games
MAX_FOLDERS, MAX_FOLDER_DEPTH = 100, 5


def folder_list(db, user):
    need_teacher(user)
    with tx(db) as c:
        rows = c.execute('select id,name,parent from folders where teacher=? order by lower(name)', (user['email'],)).fetchall()
    return [{'id': r['id'], 'name': r['name'], 'parent': r['parent'] or ''} for r in rows]


def _folder_depth(c, teacher, folder_id):
    depth, seen = 0, set()
    while folder_id and folder_id not in seen:
        seen.add(folder_id)
        r = c.execute('select parent from folders where id=? and teacher=?', (folder_id, teacher)).fetchone()
        if not r:
            raise AuthError('Folder not found.', 404)
        depth += 1
        folder_id = r['parent']
    return depth


def folder_create(db, user, name, parent=''):
    need_teacher(user)
    name = ' '.join(str(name or '').split())[:60]
    if not name:
        raise AuthError('Give the folder a name.')
    parent = str(parent or '')
    with tx(db) as c:
        if parent and _folder_depth(c, user['email'], parent) >= MAX_FOLDER_DEPTH:
            raise AuthError(f'Folders can only go {MAX_FOLDER_DEPTH} levels deep.')
        if c.execute('select count(*) n from folders where teacher=?', (user['email'],)).fetchone()['n'] >= MAX_FOLDERS:
            raise AuthError(f'You have {MAX_FOLDERS} folders. Delete some first.')
        fid = secrets.token_hex(6)
        c.execute('insert into folders values (?,?,?,?,?)', (fid, user['email'], name, parent, time.time()))
    return {'id': fid, 'name': name, 'parent': parent}


def folder_rename(db, user, folder_id, name):
    need_teacher(user)
    name = ' '.join(str(name or '').split())[:60]
    if not name:
        raise AuthError('Give the folder a name.')
    with tx(db) as c:
        if not c.execute('update folders set name=? where id=? and teacher=?', (name, str(folder_id), user['email'])).rowcount:
            raise AuthError('Folder not found.', 404)
    return {'ok': True, 'name': name}


def folder_move(db, user, folder_id, parent=''):
    """Move a folder (with everything inside it) under another folder, or to the top level when parent is empty."""
    need_teacher(user)
    folder_id, parent = str(folder_id), str(parent or '')
    with tx(db) as c:
        if not c.execute('select 1 from folders where id=? and teacher=?', (folder_id, user['email'])).fetchone():
            raise AuthError('Folder not found.', 404)
        # Refuse a move into itself or one of its own subfolders.
        walk, seen = parent, set()
        while walk and walk not in seen:
            if walk == folder_id:
                raise AuthError('A folder cannot go inside itself.')
            seen.add(walk)
            r = c.execute('select parent from folders where id=? and teacher=?', (walk, user['email'])).fetchone()
            if not r:
                raise AuthError('Folder not found.', 404)
            walk = r['parent']
        below = _subtree_height(c, user['email'], folder_id)
        if parent and _folder_depth(c, user['email'], parent) + below > MAX_FOLDER_DEPTH:
            raise AuthError(f'Folders can only go {MAX_FOLDER_DEPTH} levels deep.')
        c.execute('update folders set parent=? where id=?', (parent, folder_id))
    return {'ok': True}


def _subtree_height(c, teacher, folder_id):
    kids = [r['id'] for r in c.execute('select id from folders where parent=? and teacher=?', (folder_id, teacher))]
    return 1 + max((_subtree_height(c, teacher, k) for k in kids), default=0)


def folder_delete(db, user, folder_id):
    """Deleting a folder never deletes games: what was inside moves up to the folder's parent."""
    need_teacher(user)
    folder_id = str(folder_id)
    with tx(db) as c:
        r = c.execute('select parent from folders where id=? and teacher=?', (folder_id, user['email'])).fetchone()
        if not r:
            return {'ok': True}
        up = r['parent'] or ''
        c.execute('update packs set folder=? where folder=? and teacher=?', (up, folder_id, user['email']))
        c.execute('update folders set parent=? where parent=? and teacher=?', (up, folder_id, user['email']))
        c.execute('delete from folders where id=? and teacher=?', (folder_id, user['email']))
    return {'ok': True}


def pack_move(db, user, pack_id, folder=''):
    need_teacher(user)
    folder = str(folder or '')
    with tx(db) as c:
        if folder and not c.execute('select 1 from folders where id=? and teacher=?', (folder, user['email'])).fetchone():
            raise AuthError('Folder not found.', 404)
        if not c.execute('update packs set folder=? where id=? and teacher=?', (folder, str(pack_id), user['email'])).rowcount:
            raise AuthError('Saved game not found.', 404)
    return {'ok': True}


def pack_get(db, user, pack_id):
    need_teacher(user)
    with tx(db) as c:
        r = c.execute('select * from packs where id=? and teacher=?', (str(pack_id), user['email'])).fetchone()
    if not r:
        raise AuthError('Saved game not found.', 404)
    return {'id': r['id'], 'pack': json.loads(r['data'])}


def pack_assign(db, user, pack_id, class_ids, every=False):
    need_teacher(user)
    ids = []
    with tx(db) as c:
        r = c.execute('select id from packs where id=? and teacher=?', (str(pack_id), user['email'])).fetchone()
        if not r:
            raise AuthError('Saved game not found.', 404)
        for cid in (class_ids or [])[:50]:
            if not c.execute('select 1 from classes where id=? and teacher=? and archived=0', (str(cid), user['email'])).fetchone():
                raise AuthError('Class not found.', 404)
            ids.append(str(cid))
        c.execute('update packs set classes=? where id=?', ('[]' if every else json.dumps(sorted(set(ids)) or ['-']), r['id']))
    return {'ok': True, 'classes': sorted(set(ids)), 'all': every}


def pack_delete(db, user, pack_id):
    need_teacher(user)
    with tx(db) as c:
        c.execute('delete from packs where id=? and teacher=?', (str(pack_id), user['email']))
    return {'ok': True}


def class_packs(db, user, class_id):
    if not has_access(db, user['email'], class_id):
        raise AuthError('Join this class first.', 403)
    with tx(db) as c:
        rows = c.execute('select * from packs').fetchall()
        owner = c.execute('select teacher from classes where id=?', (str(class_id),)).fetchone()
    owner = owner['teacher'] if owner else None
    return [{'id': r['id'], 'title': r['title'], 'topics': _pack_summary(r)['topics'], 'questions': _pack_summary(r)['questions']}
            for r in rows if _pack_in_class(r, class_id, owner)]


def pack_for(db, email, pack_id, class_id):
    """A saved pack for play: its teacher always, or a class member when it is assigned to that class."""
    with tx(db) as c:
        r = c.execute('select * from packs where id=?', (str(pack_id),)).fetchone()
    if not r:
        raise AuthError('That game is no longer available.', 404)
    with tx(db) as c:
        owner = c.execute('select teacher from classes where id=?', (str(class_id),)).fetchone()
    if r['teacher'] != email and not (owner and _pack_in_class(r, class_id, owner['teacher']) and has_access(db, email, class_id)):
        raise AuthError('That game is not assigned to this class.', 403)
    return json.loads(r['data'])


# ---------------------------------------------------------------- private question library
def _clean_question(q):
    """One saved multiple-choice question: prompt, 2 to 5 choices, the index of the right one, and a short explanation."""
    if not isinstance(q, dict):
        return None
    out = {k: re.sub(r'[<>]', '', str(q.get(k, '')).strip())[:1500] for k in ('subject', 'prompt', 'answer')}
    out['subject'] = out['subject'][:40] or 'General'
    ch, ok = q.get('choices'), q.get('correct')
    if not (out['prompt'] and out['answer']):
        return None
    if not (isinstance(ch, list) and 2 <= len(ch) <= 5 and all(isinstance(c, str) and 1 <= len(c.strip()) <= 300 for c in ch)
            and isinstance(ok, int) and not isinstance(ok, bool) and 0 <= ok < len(ch)):
        return None
    out['choices'] = [re.sub(r'[<>]', '', c.strip()) for c in ch]
    out['correct'] = ok
    out['hint'] = ''
    if q.get('level') in ('easy', 'medium', 'hard'):
        out['level'] = q['level']
    dg = str(q.get('diagram') or '')
    if dg:
        out['diagram'] = dg[:8000]
    return out


def library_import(db, user, text, title, ask=None):
    need_teacher(user)
    import quizparse
    parsed = quizparse.parse_questions(text, title)
    questions = [cq for t in parsed['topics'] for q in t['questions'] for cq in [_clean_question({**q, 'subject': t['name']})] if cq][:60]
    if not questions:
        raise AuthError('No questions were found. ' + (' '.join(parsed['problems'][:2]) or 'Write each question with lettered choices and an Answer: line.'))
    title = (str(title or '').strip() or 'Question set')[:80]
    lib_id = secrets.token_hex(6)
    with tx(db) as c:
        c.execute('insert into library values (?,?,?,?,?)', (lib_id, user['email'], title, time.time(), json.dumps(questions)))
    return {**library_summary(lib_id, title, time.time(), questions), 'problems': parsed['problems']}


def library_summary(lib_id, title, created, questions):
    subjects = {}
    for q in questions:
        subjects[q['subject']] = subjects.get(q['subject'], 0) + 1
    return {'id': lib_id, 'title': title, 'created': created, 'count': len(questions), 'subjects': subjects}


def library_list(db, user):
    need_teacher(user)
    with tx(db) as c:
        rows = c.execute('select * from library where teacher=? order by created desc', (user['email'],)).fetchall()
    return [library_summary(r['id'], r['title'], r['created'], json.loads(r['questions'])) for r in rows]


def library_get(db, user, lib_id):
    need_teacher(user)
    with tx(db) as c:
        r = c.execute('select * from library where id=? and teacher=?', (str(lib_id), user['email'])).fetchone()
    if not r:
        raise AuthError('Question set not found.', 404)
    return {**library_summary(r['id'], r['title'], r['created'], json.loads(r['questions'])), 'questions': json.loads(r['questions'])}


def library_delete(db, user, lib_id):
    need_teacher(user)
    with tx(db) as c:
        c.execute('delete from library where id=? and teacher=?', (str(lib_id), user['email']))
    return {'ok': True}


def library_pack(db, user, lib_ids, subjects, title=None, per_station=4):
    """Build a game pack from chosen sets and topic tags: one station per tag, up to 7 stations of 1 to 3 questions."""
    need_teacher(user)
    wanted = {str(s).lower() for s in (subjects or [])}
    per_station = max(1, min(6, int(per_station or 4)))
    groups = {}
    with tx(db) as c:
        for lib_id in (lib_ids or []):
            r = c.execute('select questions from library where id=? and teacher=?', (str(lib_id), user['email'])).fetchone()
            if not r:
                raise AuthError('Question set not found.', 404)
            for q in json.loads(r['questions']):
                if not wanted or q['subject'].lower() in wanted:
                    groups.setdefault(q['subject'], []).append(q)
    if not groups:
        raise AuthError('No questions match those topics.')
    icons = ['⭐', '🪐', '🚀', '🛰️', '💡', '🌀', '🎯']
    topics = [{'name': name, 'icon': icons[i % len(icons)],
               'questions': [{k: q[k] for k in ('prompt', 'answer', 'choices', 'correct', 'diagram', 'level') if k in q} for q in qs[:per_station]]}
              for i, (name, qs) in enumerate(list(groups.items())[:7])]
    return {'title': (str(title or '').strip() or 'My question set')[:100], 'topics': topics}


# ---------------------------------------------------------------- routing

def record_round(db, r):
    """Store one finished round's result so the teacher balance page can show who is winning."""
    with tx(db) as c:
        c.execute('insert into rounds (at,code,winner,how,players,impostors,seconds,tags,meetings,ejected,done,total,target,practice,meeting_seconds,round_seconds) values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                  (time.time(), r.get('code',''), r.get('winner',''), r.get('how',''), r.get('players',0), r.get('impostors',0), r.get('seconds',0), r.get('tags',0), r.get('meetings',0), r.get('ejected',0), r.get('done',0), r.get('total',0), r.get('target',0), 1 if r.get('practice') else 0, r.get('meetingSeconds',0), r.get('roundSeconds',0)))


def balance(db, user):
    """Win rates and averages across finished rounds, for the teacher only. Practice rounds against computer players are left out."""
    need_teacher(user)
    with tx(db) as c:
        rows = [dict(x) for x in c.execute('select * from rounds where practice=0 order by at desc limit 500')]
    def pack(rs):
        n = len(rs)
        if not n:
            return {'rounds': 0}
        crew = sum(1 for x in rs if x['winner'] == 'crew')
        how = {}
        for x in rs:
            how[x['how']] = how.get(x['how'], 0) + 1
        avg = lambda k: round(sum(x[k] for x in rs) / n, 1)
        return {'rounds': n, 'crewWins': crew, 'impostorWins': n - crew, 'crewRate': round(100 * crew / n), 'avgSeconds': round(sum(x['seconds'] for x in rs) / n), 'avgTags': avg('tags'), 'avgMeetings': avg('meetings'), 'avgImpostors': avg('impostors'), 'ended': how}
    buckets = [('Up to 8 players', 0, 8), ('9 to 15 players', 9, 15), ('16 to 24 players', 16, 24), ('25 or more players', 25, 999)]
    return {'all': pack(rows), 'bySize': [{'label': l, **pack([x for x in rows if lo <= x['players'] <= hi])} for l, lo, hi in buckets],
            'recent': [{k: x[k] for k in ('at', 'players', 'impostors', 'winner', 'how', 'seconds', 'tags', 'meetings', 'done', 'target')} for x in rows[:15]]}


# ---------------------------------------------------------------- weekly homework
def _qids(pack_data):
    """Every question of a pack, as the 'topic:index' ids the games use."""
    return [f'{t}:{i}' for t, topic in enumerate(pack_data.get('topics') or []) for i in range(len(topic.get('questions') or []))]


def _hw_row(c, assignment_id):
    row = c.execute('select a.*, p.data as data from assignments a left join packs p on p.id=a.pack_id where a.id=? and a.deleted=0', (str(assignment_id),)).fetchone()
    if not row:
        raise AuthError('Assignment not found.', 404)
    return row


def _hw_total(row):
    return len(_qids(json.loads(row['data'] or '{}')))


def hw_create(db, user, class_id, pack_id, title, open_at, due):
    need_teacher(user)
    with tx(db) as c:
        _owned(c, user, class_id)
        pack = c.execute('select * from packs where id=? and teacher=?', (str(pack_id), user['email'])).fetchone()
        if not pack:
            raise AuthError('Pick one of your saved games for this assignment.', 404)
        if not _qids(json.loads(pack['data'])):
            raise AuthError('That game has no questions yet.')
        now = time.time()
        try:
            open_at = float(open_at) if open_at else now
            due = float(due) if due else None
        except (TypeError, ValueError):
            raise AuthError('Those dates did not look right.')
        if due and due < open_at:
            raise AuthError('The due date is before the open date.')
        aid = secrets.token_hex(6)
        c.execute('insert into assignments (id,class_id,teacher,pack_id,title,open_at,due,created) values (?,?,?,?,?,?,?,?)',
                  (aid, str(class_id), user['email'], pack['id'], (str(title or '').strip() or pack['title'])[:120], open_at, due, now))
    return {'id': aid}


def hw_delete(db, user, assignment_id):
    need_teacher(user)
    with tx(db) as c:
        row = _hw_row(c, assignment_id)
        if row['teacher'] != user['email']:
            raise AuthError('Assignment not found.', 404)
        c.execute('update assignments set deleted=1 where id=?', (row['id'],))
    return {'ok': True}


def _hw_counts(c, assignment_id):
    out = {}
    for r in c.execute('select email, count(*) n from hw_credit where assignment_id=? group by email', (assignment_id,)):
        out[r['email']] = r['n']
    adj = {r['email']: r['delta'] for r in c.execute('select email, delta from hw_adjust where assignment_id=?', (assignment_id,))}
    return out, adj


def hw_list(db, user, class_id=None):
    """Teacher: their assignments (optionally for one class) with class averages. Student: open assignments with their own progress."""
    now = time.time()
    with tx(db) as c:
        if user['role'] == 'teacher':
            q = 'select a.*, p.data as data, cl.name as class_name from assignments a left join packs p on p.id=a.pack_id join classes cl on cl.id=a.class_id where a.teacher=? and a.deleted=0 and cl.archived=0'
            args = [user['email']]
            if class_id:
                q += ' and a.class_id=?'
                args.append(str(class_id))
            rows = c.execute(q + ' order by coalesce(a.due, 9e15), a.created desc', args).fetchall()
            out = []
            for r in rows:
                total = _hw_total(r)
                counts, adj = _hw_counts(c, r['id'])
                students = [m['email'] for m in c.execute('select email from members where class_id=? and removed=0', (r['class_id'],))]
                done = [max(0, min(total, counts.get(e, 0) + adj.get(e, 0))) for e in students]
                out.append({'id': r['id'], 'classId': r['class_id'], 'className': r['class_name'], 'title': r['title'], 'total': total, 'open': r['open_at'], 'due': r['due'],
                            'students': len(students), 'finished': sum(1 for n in done if total and n >= total),
                            'avgPercent': round(100 * sum(done) / (total * len(students))) if total and students else 0})
            return {'assignments': out}
        rows = c.execute(
            'select a.*, p.data as data, cl.name as class_name from assignments a left join packs p on p.id=a.pack_id join classes cl on cl.id=a.class_id '
            'join members m on m.class_id=a.class_id and m.email=? and m.removed=0 where a.deleted=0 and cl.archived=0 and a.open_at<=? order by coalesce(a.due, 9e15), a.created desc', (user['email'], now)).fetchall()
        out = []
        for r in rows:
            total = _hw_total(r)
            counts, adj = _hw_counts(c, r['id'])
            n = max(0, min(total, counts.get(user['email'], 0) + adj.get(user['email'], 0)))
            out.append({'id': r['id'], 'classId': r['class_id'], 'className': r['class_name'], 'title': r['title'], 'total': total, 'done': n,
                        'percent': round(100 * n / total) if total else 0, 'due': r['due']})
        return {'assignments': out}


def hw_report(db, user, assignment_id):
    need_teacher(user)
    with tx(db) as c:
        row = _hw_row(c, assignment_id)
        if row['teacher'] != user['email']:
            raise AuthError('Assignment not found.', 404)
        total = _hw_total(row)
        counts, adj = _hw_counts(c, row['id'])
        notes = {r['email']: r['note'] for r in c.execute('select email, note from hw_adjust where assignment_id=?', (row['id'],))}
        last = {r['email']: r['t'] for r in c.execute('select email, max(at) t from hw_credit where assignment_id=? group by email', (row['id'],))}
        pasted = {r['email']: r['n'] for r in c.execute("select email, count(*) n from messages where class_id=? and flag='pasted' and ts>=? group by email", (row['class_id'], row['open_at'] or 0))}
        members_ = c.execute('select email,name from members where class_id=? and removed=0 order by lower(name)', (row['class_id'],)).fetchall()
    students = []
    for m in members_:
        n = max(0, min(total, counts.get(m['email'], 0) + adj.get(m['email'], 0)))
        students.append({'email': m['email'], 'name': m['name'], 'done': n, 'earned': counts.get(m['email'], 0), 'adjust': adj.get(m['email'], 0), 'note': notes.get(m['email'], ''),
                         'percent': round(100 * n / total) if total else 0, 'last': last.get(m['email']), 'pasted': pasted.get(m['email'], 0)})
    return {'id': row['id'], 'classId': row['class_id'], 'title': row['title'], 'total': total, 'due': row['due'], 'open': row['open_at'], 'students': students}


def hw_adjust(db, user, assignment_id, email, delta, note=''):
    """The teacher can add or remove credited questions for one student (for example after talking with them)."""
    need_teacher(user)
    try:
        delta = max(-100, min(100, int(delta)))
    except (TypeError, ValueError):
        raise AuthError('Enter a whole number.')
    with tx(db) as c:
        row = _hw_row(c, assignment_id)
        if row['teacher'] != user['email']:
            raise AuthError('Assignment not found.', 404)
        if not c.execute('select 1 from members where class_id=? and email=?', (row['class_id'], str(email))).fetchone():
            raise AuthError('Student not found.', 404)
        c.execute('insert into hw_adjust (assignment_id,email,delta,note) values (?,?,?,?) on conflict(assignment_id,email) do update set delta=excluded.delta, note=excluded.note',
                  (row['id'], str(email), delta, str(note or '')[:200]))
    return {'ok': True}


def hw_for_play(db, email, assignment_id):
    """What a student needs to start homework: the class, the pack, and the questions already credited. Raises if it is not theirs or not open yet."""
    with tx(db) as c:
        row = _hw_row(c, assignment_id)
        if not c.execute('select 1 from members where class_id=? and email=? and removed=0', (row['class_id'], email)).fetchone() and row['teacher'] != email:
            raise AuthError('That assignment is not for your class.', 403)
        if row['open_at'] and row['open_at'] > time.time() and row['teacher'] != email:
            raise AuthError('That assignment has not opened yet.')
    return {'id': row['id'], 'classId': row['class_id'], 'title': row['title'], 'pack': json.loads(row['data']), 'teacher': row['teacher']}


def hw_credited(db, email, assignment_id):
    with tx(db) as c:
        return {r['qid'] for r in c.execute('select qid from hw_credit where assignment_id=? and email=?', (str(assignment_id), email))}


def hw_credit(db, email, assignment_id, qid):
    with tx(db) as c:
        c.execute('insert or ignore into hw_credit (assignment_id,email,qid,at) values (?,?,?,?)', (str(assignment_id), email, str(qid), time.time()))
        return c.execute('select count(*) n from hw_credit where assignment_id=? and email=?', (str(assignment_id), email)).fetchone()['n']


def hw_export(db, user, class_id):
    """The class gradebook as CSV text: one row per student, a completed count and percent for every assignment."""
    need_teacher(user)
    with tx(db) as c:
        cl = _owned(c, user, class_id)
        rows = c.execute('select a.*, p.data as data from assignments a left join packs p on p.id=a.pack_id where a.class_id=? and a.deleted=0 order by a.open_at, a.created', (cl['id'],)).fetchall()
        students = c.execute('select email,name from members where class_id=? and removed=0 order by lower(name)', (cl['id'],)).fetchall()
        data = []
        for a in rows:
            counts, adj = _hw_counts(c, a['id'])
            data.append((a, _hw_total(a), counts, adj))

    def cell(v):
        v = str(v)
        if v[:1] in '=+-@':
            v = "'" + v
        return '"' + v.replace('"', '""') + '"'
    head = ['Student', 'Email']
    for a, total, _, _ in data:
        head += [f"{a['title']} (of {total})", f"{a['title']} %"]
    lines = [','.join(cell(h) for h in head)]
    for s in students:
        row = [s['name'], s['email']]
        for a, total, counts, adj in data:
            n = max(0, min(total, counts.get(s['email'], 0) + adj.get(s['email'], 0)))
            row += [n, round(100 * n / total) if total else 0]
        lines.append(','.join(cell(v) for v in row))
    return {'csv': '\n'.join(lines) + '\n', 'filename': re.sub(r'[^A-Za-z0-9]+', '-', cl['name']).strip('-') + '-homework.csv'}


def dispatch(db, path, d, ask=None):
    if path == '/api/auth/google':
        return sign_in(db, str(d.get('credential', '')))
    if path == '/api/auth/logout':
        sign_out(db, str(d.get('userToken', '')))
        return {'ok': True}
    user = user_for(db, d)
    if path == '/api/auth/me':
        return {'user': user, 'classes': class_list(db, user)}
    if path == '/api/balance':
        return balance(db, user)
    if path == '/api/hw/create':
        return hw_create(db, user, d.get('classId'), d.get('packId'), d.get('title'), d.get('openAt'), d.get('due'))
    if path == '/api/hw/delete':
        return hw_delete(db, user, d.get('id'))
    if path == '/api/hw/list':
        return hw_list(db, user, d.get('classId'))
    if path == '/api/hw/report':
        return hw_report(db, user, d.get('id'))
    if path == '/api/hw/adjust':
        return hw_adjust(db, user, d.get('id'), d.get('email'), d.get('delta'), d.get('note'))
    if path == '/api/hw/export':
        return hw_export(db, user, d.get('classId'))
    if path == '/api/class/create':
        return class_create(db, user, d.get('name'), d.get('domains') or DEFAULT_STUDENT_DOMAINS)
    if path == '/api/class/list':
        return {'classes': class_list(db, user)}
    if path == '/api/class/delete':
        return class_delete(db, user, d.get('classId'))
    if path == '/api/class/join':
        return join_class(db, user, d.get('code'))
    if path == '/api/class/invite':
        return invite_create(db, user, d.get('classId'), d.get('days', 14), d.get('maxUses', 0))
    if path == '/api/class/invite/revoke':
        return invite_revoke(db, user, d.get('classId'))
    if path == '/api/class/members':
        return {'members': members(db, user, d.get('classId'))}
    if path == '/api/class/remove':
        return set_removed(db, user, d.get('classId'), d.get('email'), True)
    if path == '/api/class/restore':
        return set_removed(db, user, d.get('classId'), d.get('email'), False)
    if path == '/api/class/nicknames/suggest':
        return suggest_nicknames(db, user, d.get('classId'), ask)
    if path == '/api/class/nicknames/save':
        return save_nicknames(db, user, d.get('classId'), d.get('nicknames'))
    if path == '/api/class/transcript':
        return {'conversations': transcript(db, user, d.get('classId'), d.get('email'))}
    if path == '/api/class/mailtest':
        return mail_test(db, user)
    if path == '/api/class/alerts':
        return {'alerts': alerts_list(db, user)}
    if path == '/api/class/alert':
        return alert_detail(db, user, d.get('alertId'))
    if path == '/api/class/alert/review':
        return alert_review(db, user, d.get('alertId'))
    if path == '/api/class/alert/retry':
        return alert_retry(db, user, d.get('alertId'))
    if path == '/api/pack/save':
        return pack_save(db, user, d.get('pack') or {}, d.get('id'), d.get('folder'))
    if path == '/api/pack/list':
        return {'packs': pack_list(db, user), 'folders': folder_list(db, user)}
    if path == '/api/pack/move':
        return pack_move(db, user, d.get('id'), d.get('folder'))
    if path == '/api/folder/create':
        return folder_create(db, user, d.get('name'), d.get('parent'))
    if path == '/api/folder/rename':
        return folder_rename(db, user, d.get('id'), d.get('name'))
    if path == '/api/folder/move':
        return folder_move(db, user, d.get('id'), d.get('parent'))
    if path == '/api/folder/delete':
        return folder_delete(db, user, d.get('id'))
    if path == '/api/pack/get':
        return pack_get(db, user, d.get('id'))
    if path == '/api/pack/assign':
        return pack_assign(db, user, d.get('id'), d.get('classIds'), bool(d.get('all')))
    if path == '/api/pack/delete':
        return pack_delete(db, user, d.get('id'))
    if path == '/api/class/packs':
        return {'packs': class_packs(db, user, d.get('classId'))}
    if path == '/api/library/import':
        return library_import(db, user, d.get('text'), d.get('title'), ask)
    if path == '/api/library/list':
        return {'sets': library_list(db, user)}
    if path == '/api/library/get':
        return library_get(db, user, d.get('id'))
    if path == '/api/library/delete':
        return library_delete(db, user, d.get('id'))
    if path == '/api/library/pack':
        return {'pack': library_pack(db, user, d.get('ids'), d.get('subjects'), d.get('title'), d.get('perStation', 4))}
    raise AuthError('Unknown action.', 404)
