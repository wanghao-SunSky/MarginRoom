import io
import json
import sqlite3
import zipfile
import pytest
from test_reading import env
from backend import learning, store as s


def test_anchor_roundtrip_keeps_identity_and_rejects_wrong_section(env):
    client,bid,other,sections=env;sid=sections[0]['id']
    note=s.save_artifact(bid,'note','test','quote',sid)
    body={'artifact_id':note['id'],'section_id':sid,'quote':'工具调用','prefix':'','suffix':'','start':0,'version':'4:123'}
    assert client.put(f'/api/books/{bid}/learning/anchors',json=body).status_code==200
    assert client.get(f'/api/books/{bid}/learning/anchors').json()[0]['artifact_id']==note['id']
    body['section_id']=sections[-1]['id']
    assert client.put(f'/api/books/{bid}/learning/anchors',json=body).status_code==422
    assert client.get(f'/api/books/{other}/learning/anchors').json()==[]
    with s.db() as c:c.execute('UPDATE books SET content_hash=? WHERE id=?',('new-material-version',bid))
    assert client.get(f'/api/books/{bid}/learning/anchors').json()==[]


def test_feedback_grounding_and_confirmed_card_idempotency(env,monkeypatch):
    client,bid,_,sections=env;sid=sections[0]['id'];source=sections[0]['content']
    async def fake(*_):return {'understood':['You identified the topic.'],'issues':[{'quote':source,'feedback':'You omitted the constraint.'}],'hint':'Try explaining the constraint.','cards':[{'front':'Which constraint?','back':'The original constraint.'}]}
    monkeypatch.setattr(learning,'model_json',fake)
    result=client.post(f'/api/books/{bid}/learning/feedback',json={'section_id':sid,'explanation':'My explanation','language':'en'})
    assert result.status_code==200
    assert not s.all_rows("SELECT * FROM artifacts WHERE kind='cards'")
    data=result.json();body={'feedback_id':data['id'],'cards':data['cards']}
    first=client.post(f'/api/books/{bid}/learning/cards',json=body).json()
    second=client.post(f'/api/books/{bid}/learning/cards',json=body).json()
    assert first==second and len(s.all_rows("SELECT * FROM artifacts WHERE kind='cards'"))==1
    with pytest.raises(ValueError):learning.validate_feedback({**data,'issues':[{'quote':'nonexistent quote','feedback':'bad'}]},source)
    assert learning.validate_feedback({'understood':['Correct'],'issues':[],'cards':[],'hint':''},source)['issues']==[]


def test_starters_are_content_language_and_version_bound(env):
    client,bid,_,sections=env;sid=sections[0]['id'];url=f'/api/books/{bid}/learning/starters?section_id={sid}'
    en=client.get(url+'&language=en').json();zh=client.get(url+'&language=zh').json()
    assert en['questions']!=zh['questions'] and sections[0]['title'] in en['questions'][0]
    assert client.get(url+'&language=en').json()==en
    with s.db() as c:c.execute('UPDATE books SET content_hash=? WHERE id=?',('updated',bid))
    assert client.get(url).json()['version']=='updated'


def unpack(data,tmp_path,name):
    archive=zipfile.ZipFile(io.BytesIO(data));assert set(archive.namelist())=={'collection.anki2','media'}
    path=tmp_path/name;path.write_bytes(archive.read('collection.anki2'));return sqlite3.connect(path)


def test_apkg_templates_source_and_stable_guids(tmp_path):
    cards=[{'id':'stable','front':'<question>','back':'Answer','section_id':'sec'}]
    a=unpack(learning.package_bytes('book','Title',cards,'http://localhost:9999'),tmp_path,'a.db')
    cards[0]['front']='Edited question'
    b=unpack(learning.package_bytes('book','Title',cards,'http://localhost:9999'),tmp_path,'b.db')
    assert a.execute('SELECT guid FROM notes').fetchone()==b.execute('SELECT guid FROM notes').fetchone()
    fields=a.execute('SELECT flds FROM notes').fetchone()[0]
    assert '&lt;question&gt;' in fields and 'book=book&amp;section=sec' in fields
    models=json.loads(a.execute('SELECT models FROM col').fetchone()[0]);model=next(iter(models.values()))
    assert len(model['flds'])==4 and '{{Question}}' in model['tmpls'][0]['qfmt'] and '{{Source}}' in model['tmpls'][0]['afmt']
    assert a.execute('SELECT count(*) FROM cards').fetchone()[0]==1
    a.close();b.close()


def test_local_feedback_attempt_limit_stops_model_work(env,monkeypatch):
    client,bid,_,sections=env
    with s.db() as c:
        learning.init_tables(c)
        c.execute('CREATE TABLE IF NOT EXISTS learning_attempts(created_at REAL NOT NULL)')
        c.executemany('INSERT INTO learning_attempts VALUES(?)',[(s.now(),)]*10)
    called=[]
    async def model(*args):called.append(True);return {}
    monkeypatch.setattr(learning,'model_json',model)
    response=client.post(f'/api/books/{bid}/learning/feedback',json={'section_id':sections[0]['id'],'explanation':'Test explanation','language':'en'})
    assert response.status_code==429 and not called
