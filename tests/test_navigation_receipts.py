"""A reconnect may replay one navigation; only its first receipt is authoritative."""
from concurrent.futures import ThreadPoolExecutor
import json
import pytest
from fastapi import HTTPException
from backend import app as web,store as s
from test_reading import env,make_run


def command(env,cid='navigation',expires=None,action='navigate'):
    _,bid,_,sections=env;run=make_run(bid,sections[0]['id'])
    with s.db() as c:
        c.execute('INSERT INTO commands(id,run_id,client_id,action,section_id,expected_revision,expires_at) VALUES(?,?,?,?,?,?,?)',(cid,run['id'],'client-test',action,sections[1]['id'] if action=='navigate' else None,3,expires if expires is not None else s.now()+60))
    return sections[1]['id']


def receipt(sid,status='applied',**overrides):
    return web.Ack(**{'client_id':'client-test','status':status,'section_id':sid if status=='applied' else None,'view_revision':4,**overrides})


@pytest.mark.parametrize('action',['navigate','return_to'])
def test_concurrent_different_receipts_settle_once(env,action):
    sid=command(env,action=action)
    def ack(i):return web.ack('navigation',receipt(sid,'applied' if i%2 else 'stale'))
    with ThreadPoolExecutor(max_workers=12) as pool:results=list(pool.map(ack,range(24)))
    stored=json.loads(s.one('SELECT result FROM commands WHERE id=?',('navigation',))['result'])
    assert all(r==stored for r in results)
    assert stored['status'] in ('applied','stale')
    assert web.ack('navigation',receipt(sid,'expired'))==stored


@pytest.mark.parametrize('bad,code',[({'client_id':'another-window'},403),({'view_revision':3},422),({'section_id':'missing'},422)])
def test_invalid_ack_does_not_consume_the_pending_command(env,bad,code):
    sid=command(env)
    with pytest.raises(HTTPException) as caught:web.ack('navigation',receipt(sid,**bad))
    assert caught.value.status_code==code
    assert s.one('SELECT status FROM commands WHERE id=?',('navigation',))['status']=='pending'
    assert web.ack('navigation',receipt(sid))['status']=='applied'


def test_expired_command_remains_expired_on_later_replay(env):
    sid=command(env,expires=s.now()-1)
    first=web.ack('navigation',receipt(sid))
    assert first['status']=='expired'
    assert web.ack('navigation',receipt(sid,'stale'))==first
