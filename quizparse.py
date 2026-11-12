"""Turn a teacher's plain-text question list into game questions. No AI: a fixed, forgiving format.

    Topic: Magnets            (optional; starts a new room)
    1. Which poles attract?
    A) North and north
    B) North and south
    C) South and south
    Answer: B
    Explanation: Opposite poles attract.   (optional)

A question is a line of text, then lettered choices (A. / A) / (A) / a:), then the correct answer.
The correct answer can be an `Answer: B` line or a * or ✓ next to one choice.
"""
import re

CHOICE = re.compile(r'^\s*\(?([A-Ea-e])[\)\.\:]\s+(.*\S)\s*$')
ANSWER = re.compile(r'^\s*(?:correct\s+)?(?:answer|ans|correct)\s*[:=\-]\s*\(?([A-Ea-e])?\)?\.?\s*(.*)$', re.I)
EXPLAIN = re.compile(r'^\s*(?:explanation|explain|why|reason|rationale)\s*[:\-]\s*(.*)$', re.I)
TOPIC = re.compile(r'^\s*(?:topic|room|unit|section)\s*[:\-]\s*(.+?)\s*$|^\s*#{1,3}\s+(.+?)\s*$', re.I)
NUMBER = re.compile(r'^\s*(?:q(?:uestion)?\s*)?\d{1,3}\s*[\)\.\:\-]\s*|^\s*q(?:uestion)?\s*[:\-]\s*', re.I)
MARK = re.compile(r'(?:\s*[\*✓✔]+\s*|\s*\((?:correct|answer)\)\s*)$|^\s*[\*✓✔]+\s*', re.I)
ICONS = ['🧲', '⚡', '🔭', '🧪', '📐', '🌍', '🧠']


def _clean(s):
    return re.sub(r'[<>]', '', str(s or '').strip())


def parse_questions(text, title=''):
    """Returns {'title', 'topics': [{'name','icon','questions':[...]}], 'problems': [str]}."""
    text = str(text or '').replace('\r', '')[:60000]
    topics, problems = [], []
    cur_topic = None
    block = []

    def flush():
        nonlocal block
        if not any(l.strip() for l in block):
            block = []
            return
        lines = [l for l in block]
        block = []
        prompt_lines, choices, marked, ans_letter, ans_text, expl = [], [], None, None, '', []
        seen_choice = False
        for line in lines:
            if not line.strip():
                continue
            m = EXPLAIN.match(line)
            if m:
                expl.append(m.group(1).strip())
                continue
            m = ANSWER.match(line)
            if m and (m.group(1) or m.group(2)) and (choices or m.group(1)):
                ans_letter = (m.group(1) or '').upper() or None
                ans_text = m.group(2).strip()
                continue
            m = CHOICE.match(line)
            if m:
                seen_choice = True
                body = m.group(2)
                if MARK.search(body) or re.match(r'^\s*\([A-Ea-e]\)\s*[\*✓✔]', line):
                    marked = len(choices)
                    body = MARK.sub('', body).strip()
                choices.append(_clean(body))
                continue
            if expl:
                expl.append(line.strip())
            elif seen_choice and not choices:
                prompt_lines.append(line.strip())
            elif seen_choice:
                choices[-1] = (choices[-1] + ' ' + line.strip()).strip()  # a wrapped choice
            else:
                prompt_lines.append(line.strip())
        prompt = _clean(NUMBER.sub('', ' '.join(prompt_lines), count=1))
        label = prompt[:50] or 'A question'
        if not prompt:
            problems.append('Found choices with no question above them.')
            return
        if not 2 <= len(choices) <= 5:
            problems.append(f'“{label}”: needs 2 to 5 lettered choices (A. B. C. D.).')
            return
        correct = marked
        if ans_letter and 'ABCDE'.index(ans_letter) < len(choices):
            correct = 'ABCDE'.index(ans_letter)
        elif ans_text and correct is None:
            for i, c in enumerate(choices):
                if c.lower().strip(' .') == ans_text.lower().strip(' .'):
                    correct = i
        if correct is None:
            problems.append(f'“{label}”: no correct answer marked. Add a line like Answer: B.')
            return
        why = _clean(' '.join(expl))
        if not why:
            why = f'The correct answer is {"ABCDE"[correct]}) {choices[correct]}.'
        q = {'prompt': prompt[:3000], 'choices': choices, 'correct': correct, 'answer': why[:3000]}
        nonlocal cur_topic
        if cur_topic is None:
            cur_topic = {'name': '', 'questions': []}
            topics.append(cur_topic)
        cur_topic['questions'].append(q)

    for line in text.split('\n'):
        t = TOPIC.match(line)
        if t and not CHOICE.match(line):
            flush()
            name = _clean(t.group(1) or t.group(2))[:60]
            cur_topic = {'name': name, 'questions': []}
            topics.append(cur_topic)
            continue
        if not line.strip():
            # a blank line ends a question once it has its answer or enough choices
            if any(ANSWER.match(l) or MARK.search(l) for l in block) or sum(1 for l in block if CHOICE.match(l)) >= 2 and any(ANSWER.match(l) for l in block):
                flush()
            else:
                block.append(line)
            continue
        # a new numbered question line after a finished block starts the next question
        if block and NUMBER.match(line) and not CHOICE.match(line) and any(CHOICE.match(l) for l in block):
            flush()
        block.append(line)
    flush()
    topics = [t for t in topics if t['questions']]
    # no topic headers: group questions into rooms of three
    if topics and all(not t['name'] for t in topics):
        qs = [q for t in topics for q in t['questions']]
        topics = [{'name': '', 'questions': qs[i:i + 3]} for i in range(0, len(qs), 3)]
    for i, t in enumerate(topics[:7]):
        t['name'] = t['name'] or f'Room {i + 1}'
        t['icon'] = ICONS[i % len(ICONS)]
        t['questions'] = t['questions'][:6]
    if len(topics) > 7:
        problems.append('Only the first 7 rooms were used. A game has at most 7 topics.')
    return {'title': _clean(title)[:100], 'topics': topics[:7], 'problems': problems}
