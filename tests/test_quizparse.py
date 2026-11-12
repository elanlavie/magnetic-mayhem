import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import quizparse

SAMPLE="""Topic: Magnetism
1. Why does a magnet attract a nail?
A) It has charge
B) Its domains line up
C) Gravity
Answer: B
Explanation: The nail's domains align.

2. Pick one
A) yes
B) no
Answer: A

3. Bad one
A) x
B) y
"""

class ParseTests(unittest.TestCase):
    def test_parses_questions_and_flags_missing_answers(self):
        r=quizparse.parse_questions(SAMPLE)
        qs=[q for t in r['topics'] for q in t['questions']]
        self.assertEqual(len(qs),2);self.assertEqual(qs[0]['choices'][qs[0]['correct']],'Its domains line up')
        self.assertTrue(r['problems']);self.assertEqual(r['topics'][0]['name'],'Magnetism')
    def test_empty_text_has_no_questions(self):
        r=quizparse.parse_questions('hello');self.assertEqual([q for t in r['topics'] for q in t['questions']],[])
if __name__=='__main__':unittest.main()
