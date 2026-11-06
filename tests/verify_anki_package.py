"""Optional official-engine check, outside normal project dependencies.
Run: uv run --with anki==26.09.4 python tests/verify_anki_package.py
Uses disposable synthetic notes only; never opens an existing Anki profile.
"""
import sys
import tempfile
import time
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urlsplit,parse_qs
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from anki.collection import Collection,ImportAnkiPackageRequest
from backend.learning import package_bytes

class Link(HTMLParser):
    href=''
    def handle_starttag(self,tag,attrs):
        if tag=='a':self.href=dict(attrs).get('href','')


def main():
    cards=[{'id':'example-one','front':'谁保留所有权？','back':'原来的变量。','section_id':'borrowing'},
           {'id':'example-two','front':'Can a reference outlive its value?','back':'No.','section_id':'lifetimes'}]
    with tempfile.TemporaryDirectory(prefix='marginroom-anki-engine-') as temp:
        root=Path(temp);path=root/'collection.anki2';package=root/'reading.apkg';newer=root/'updated.apkg'
        package.write_bytes(package_bytes('example-book','Example',cards,'https://reader.example'))
        col=Collection(str(path))
        col.import_anki_package(ImportAnkiPackageRequest(package_path=str(package)))
        ids=col.find_notes('');assert len(ids)==2 and col.card_count()==2
        initial={col.get_note(nid).fields[0]:(nid,col.get_note(nid).guid) for nid in ids}
        col.import_anki_package(ImportAnkiPackageRequest(package_path=str(package)))
        assert len(col.find_notes(''))==2 and col.card_count()==2
        time.sleep(1.2) # Anki's package modification timestamps have second resolution.
        cards[0]['back']='更新：原值所有权仍由原变量保留。'
        newer.write_bytes(package_bytes('example-book','Example',cards,'https://reader.example'))
        col.import_anki_package(ImportAnkiPackageRequest(package_path=str(newer)))
        assert len(col.find_notes(''))==2 and col.card_count()==2
        for nid in col.find_notes(''):
            note=col.get_note(nid);assert (nid,note.guid)==initial[note.fields[0]]
            expected=next(c for c in cards if c['id']==note.fields[0]);assert note.fields[1:3]==[expected['front'],expected['back']]
            link=Link();link.feed(note.fields[3]);url=urlsplit(link.href)
            assert url.scheme=='https' and url.netloc=='reader.example'
            assert parse_qs(url.query)=={'book':['example-book'],'section':[expected['section_id']]}
        col.close();col=Collection(str(path));assert len(col.find_notes(''))==2;col.close()
    print('Official Anki engine: first import, reimport, same-GUID update, Unicode/source links and reopen passed. GUI and source-link click remain untested.')

if __name__=='__main__':main()
