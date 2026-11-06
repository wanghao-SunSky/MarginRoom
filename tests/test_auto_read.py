from test_reading import env
from backend import store as s


def test_automatic_read_is_idempotent_and_preserves_manual_unread(env):
    client,bid,_,sections=env;sid=sections[0]['id'];url=f'/api/sections/{sid}/read'
    for _ in range(2):assert client.put(url,json={'read':True,'source':'auto'}).json()['read'] is True
    assert len(s.all_rows('SELECT * FROM marks WHERE section_id=?',(sid,)))==1
    assert client.put(url,json={'read':False}).json()['auto_blocked'] is True
    assert client.put(url,json={'read':True,'source':'auto'}).json()['read'] is False
    detail=client.get('/api/books/'+bid).json()['sections'][0]
    assert not detail['is_read'] and detail['auto_read_blocked']
    assert client.put(url,json={'read':True}).json()['auto_blocked'] is False
    assert client.get('/api/books/'+bid).json()['sections'][0]['is_read']


def test_auto_unread_is_rejected_and_progress_is_per_section(env):
    client,bid,_,sections=env;sid=sections[0]['id']
    assert client.put(f'/api/sections/{sid}/read',json={'read':False,'source':'auto'}).status_code==422
    client.put(f'/api/sections/{sid}/read',json={'read':True,'source':'auto'})
    assert sum(x['is_read'] for x in client.get('/api/books/'+bid).json()['sections'])==1
