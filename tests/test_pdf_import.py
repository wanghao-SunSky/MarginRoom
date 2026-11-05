import asyncio
import io
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject,NameObject,DecodedStreamObject
from backend import ingest,store as s,agent
from backend.pdf_import import paragraphs
from test_reading import env,make_run


def sample_pdf():
    writer=PdfWriter()
    for _ in range(5):writer.add_blank_page(width=500,height=700)
    # Real blank pages often have transforms/colors but no drawing operations.
    empty=DecodedStreamObject();empty.set_data(b'q 1 0 0 1 72 700 cm 0 G 0 g Q')
    writer.pages[0][NameObject('/Contents')]=writer._add_object(empty)
    font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
    for i in (1,2,3):
        page=writer.pages[i]
        page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
        stream=DecodedStreamObject();stream.set_data(f'BT /F1 14 Tf 50 600 Td (Chapter {i}) Tj 0 -50 Td (First paragraph.) Tj 0 -50 Td (Second paragraph.) Tj ET'.encode())
        page[NameObject('/Contents')]=writer._add_object(stream)
    stream=DecodedStreamObject();stream.set_data(b'0 0 100 100 re f')
    writer.pages[4][NameObject('/Contents')]=writer._add_object(stream)
    part=writer.add_outline_item('Part I',0)
    chapter=writer.add_outline_item('Foundations',1,parent=part)
    writer.add_outline_item('First idea',1,parent=chapter)
    writer.add_outline_item('Practice',3,parent=part)
    buf=io.BytesIO();writer.write(buf);return buf.getvalue()


def test_import_preserves_bookmarks_paragraphs_and_chapter_scope(env):
    client,*_=env
    response=client.post('/api/import',files={'file':('book.pdf',sample_pdf())})
    assert response.status_code==200,response.text
    bid=response.json()['id'];book=client.get('/api/books/'+bid).json()
    assert [x['title'] for x in book['outline']]==['Part I','Foundations','First idea','Practice']
    assert [x['depth'] for x in book['outline']]==[0,1,2,1]
    assert book['blank_pages']==[1] and book['image_pages']==[5] and book['missing_pages']==1
    second=client.get('/api/sections/'+book['sections'][1]['id']).json()
    assert 'First paragraph.\n\nSecond paragraph.' in second['content']
    assert second['chapter']=='Foundations'
    run=make_run(bid,second['id'])
    chapter=asyncio.run(agent.execute_tool(run,'read_chapter',{'section_id':second['id']}))
    assert chapter['total']==2 and chapter['covered']==2 and not chapter['truncated']
    outline=asyncio.run(agent.execute_tool(run,'get_outline',{}))
    assert outline['bookmarks_total']==4
    assert all(x['section_id'] in {row['id'] for row in book['sections']} for x in outline['bookmarks'])


def test_reimport_repairs_legacy_pdf_without_losing_ids_or_notes(env):
    client,*_=env;raw=sample_pdf()
    bid=ingest.import_file('book.pdf',raw)[0]
    rows=s.all_rows('SELECT * FROM sections WHERE book_id=? ORDER BY ordinal',(bid,))
    sid=rows[1]['id'];run=make_run(bid,sid)
    note=s.save_artifact(bid,'note','My note','Keep my words',sid,run['id'])
    with s.db() as c:
        c.execute("UPDATE runs SET status='complete' WHERE id=?",(run['id'],))
        c.execute('INSERT INTO positions VALUES(?,?,?)',(bid,sid,s.now()))
        c.execute('INSERT INTO marks VALUES(?,?)',(sid,s.now()))
        c.execute('DELETE FROM pdf_documents WHERE book_id=?',(bid,))
        c.execute("UPDATE sections SET chapter='book',title='Page',content='old extraction' WHERE book_id=?",(bid,))
    assert ingest.import_file('renamed.pdf',raw)==(bid,False)
    after=s.all_rows('SELECT * FROM sections WHERE book_id=? ORDER BY ordinal',(bid,))
    assert [r['id'] for r in after]==[r['id'] for r in rows]
    assert after[1]['chapter']=='Foundations'
    assert s.one('SELECT * FROM artifacts WHERE id=?',(note['id'],))['content']=='Keep my words'
    assert s.one('SELECT section_id FROM positions WHERE book_id=?',(bid,))['section_id']==sid
    assert s.one('SELECT * FROM marks WHERE section_id=?',(sid,))


def test_paragraphs_preserve_cjk_wrapping_headings_and_table_rows():
    text='  第一章 阅读\n\n第一行内容\n接着上一行。\n\n另一个段落。\n\n名称    数量\n苹果    3\n\n  17'
    result=paragraphs(text,[{'title':'阅读'}])
    assert result.startswith('## 第一章 阅读\n\n')
    assert '第一行内容接着上一行。\n\n另一个段落。' in result
    assert '```text\n名称    数量\n苹果    3\n```' in result
    assert not result.endswith('17')
