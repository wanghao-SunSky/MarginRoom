"""Independent source-link and idempotency checks for the bundled course."""
import re
from backend import bundled_course as course,store as s
from test_reading import env


def test_every_rewritten_course_link_stays_in_the_same_book(env):
    bid,_=course.seed_course()
    sections=s.all_rows('SELECT * FROM sections WHERE book_id=? ORDER BY ordinal',(bid,))
    assert len({x['chapter'] for x in sections if not x['chapter'].startswith(('附录','来源'))})==19
    count=0
    for section in sections:
        for ordinary,part in course.prose_parts(section['content']):
            if not ordinary:continue
            for target in re.findall(r'\]\(([^\s)]+)\)',part):
                if target.startswith('/section/'):
                    count+=1
                    assert s.one('SELECT id FROM sections WHERE id=? AND book_id=?',(target[9:],bid))
                else:assert target.startswith(('https://','http://','mailto:'))
    assert count>=32


def test_repeated_seed_preserves_reader_work(env):
    bid,_=course.seed_course();section=s.one('SELECT id FROM sections WHERE book_id=? ORDER BY ordinal',(bid,))['id']
    artifact=s.save_artifact(bid,'note','Existing note','Do not replace my work',section)
    with s.db() as c:
        c.execute('INSERT INTO positions VALUES(?,?,?)',(bid,section,s.now()))
        c.execute('INSERT INTO marks VALUES(?,?)',(section,s.now()))
    ids=[r['id'] for r in s.all_rows('SELECT id FROM sections WHERE book_id=? ORDER BY ordinal',(bid,))]
    assert course.seed_course()==(bid,False)
    assert [r['id'] for r in s.all_rows('SELECT id FROM sections WHERE book_id=? ORDER BY ordinal',(bid,))]==ids
    assert s.one('SELECT content FROM artifacts WHERE id=?',(artifact['id'],))['content']=='Do not replace my work'
    assert s.one('SELECT section_id FROM positions WHERE book_id=?',(bid,))['section_id']==section
    assert s.one('SELECT section_id FROM marks WHERE section_id=?',(section,))
