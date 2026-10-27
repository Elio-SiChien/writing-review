import json, tempfile, threading, unittest, urllib.request, urllib.error, hashlib
from pathlib import Path
from writing_review.server import Store, make_server, normalize, main
from unittest.mock import patch
from writing_review import memory

def example():
    return {'id':'demo','title':'Synthetic study','roundId':'round-one','scope':'introduction',
            'paragraphs':[{'id':'P1','original':'A small error alone is insufficient.','current':'A small error alone is insufficient.'}],
            'comments':[{'id':'C1','paragraphId':'P1','quote':'small error','text':'Start with the central argument.'}]}

def suggestion():
    return {'principle':'Start each paragraph with its main point.','scope':'academic','kind':'explicit','source_ids':['C1'],'evidence':'User explicitly asks for the central argument first.','before':'Background first.','after':'The central argument comes first.'}

class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name)
        self.vault=self.base/'vault';self.vault.mkdir();self.store=Store(self.base/'data',self.vault)
    def tearDown(self):
        self.store.db.close();self.tmp.cleanup()
    def test_cas_prevents_lost_update(self):
        first=self.store.save(example(),0)
        changed=example();changed['paragraphs'][0]['current']='Edited.'
        self.store.save(changed,first['version'])
        with self.assertRaises(RuntimeError):self.store.save(example(),first['version'])
        self.assertEqual(self.store.get('demo')['paragraphs'][0]['current'],'Edited.')
    def test_identical_import_is_idempotent(self):
        first=self.store.save(example(),0)
        self.assertEqual(self.store.save(example(),first['version'])['version'],1)
    def test_mismatch_does_not_overwrite(self):
        self.store.save(example(),0);other=example();other['paragraphs'][0]['original']='Different source'
        with self.assertRaises(ValueError):self.store.save(other,1)
        self.assertEqual(self.store.get('demo')['paragraphs'][0]['original'],example()['paragraphs'][0]['original'])
    def test_duplicate_and_invalid_targets_rejected(self):
        data=example();data['comments']*=2
        with self.assertRaises(ValueError):normalize(data)
        data=example();data['comments'][0]['paragraphId']='missing'
        with self.assertRaises(ValueError):normalize(data)
    def test_no_path_traversal_id(self):
        data=example();data['id']='../../secret'
        with self.assertRaises(ValueError):normalize(data)
    def test_failure_saved_and_retry_survives_restart(self):
        self.store.auto_extract=True
        self.store.save(example(),0)
        def fail(*args):raise RuntimeError('Model is unavailable')
        self.store.learn_once(force=True,extractor=fail)
        self.assertEqual(self.store.get('demo')['learning']['status'],'retry')
        second=Store(self.base/'data',self.vault)
        self.assertEqual(second.get('demo')['comments'][0]['id'],'C1');second.db.close()
    def test_preference_deduplication_scope_and_manual_preservation(self):
        review=normalize(example());state={}
        memory.apply_suggestions(self.vault,[suggestion()],review,state)
        memory.apply_suggestions(self.vault,[suggestion()],review,state)
        rules=memory.records(self.vault);self.assertEqual(len(rules),1)
        self.assertEqual(rules[0]['rounds'],['round-one'])
        path=Path(rules[0]['_file']);path.write_text(path.read_text()+'\nHuman edit\n',encoding='utf-8')
        memory.apply_suggestions(self.vault,[suggestion()],review,state)
        self.assertIn('Human edit',path.read_text())
        self.assertEqual(len(list((self.vault/'写作复利/候选与冲突').glob('*.md'))),1)
    def test_candidates_and_project_rules_not_global(self):
        a=suggestion();a['kind']='inferred';b=suggestion();b['scope']='project:demo';b['principle']='Use this project term.'
        memory.apply_suggestions(self.vault,[a,b],normalize(example()),{})
        self.assertEqual(memory.profile(self.vault,{'academic'}),'')
        self.assertIn('project:demo',memory.profile(self.vault,{'project:demo'}))
    def test_unknown_source_rejected(self):
        a=suggestion();a['source_ids']=['invented']
        with self.assertRaises(ValueError):memory.apply_suggestions(self.vault,[a],normalize(example()),{})
    def test_adopted_human_note_survives_later_provenance(self):
        review=normalize(example());state={}
        memory.apply_suggestions(self.vault,[suggestion()],review,state)
        rule=memory.records(self.vault)[0];file=Path(rule['_file'])
        file.write_text(file.read_text(encoding='utf-8')+'\n## Human examples\nKeep my organization and wording.\n',encoding='utf-8')
        # A fresh service first adopts this pre-existing human note.
        adopted={};memory.apply_suggestions(self.vault,[suggestion()],review,adopted)
        newer=normalize(example());newer['roundId']='round-two'
        newer['comments'].append({'id':'C2','paragraphId':'P1','text':'The same preference in a new round.'})
        more=suggestion();more['source_ids']=['C1','C2']
        memory.apply_suggestions(self.vault,[more],newer,adopted)
        updated=memory.records(self.vault)[0]
        self.assertIn('## Human examples\nKeep my organization and wording.',updated['_text'])
        self.assertEqual(updated['rounds'],['round-one','round-two'])
        self.assertEqual(updated['sources'],['C1','C2'])
    def test_opt_in_inference_only_proposes_until_user_approval(self):
        self.store.auto_extract=True
        self.store.save(example(),0)
        self.store.learn_once(force=True,extractor=lambda *args:[suggestion()])
        self.assertEqual(self.store.get('demo')['learning']['status'],'proposal')
        self.assertEqual(memory.profile(self.vault,{'academic'}),'')
        proposal=json.loads((self.store.folder/'proposals/demo-v1.json').read_text(encoding='utf-8'))
        self.assertEqual(proposal['status'],'needs_user_approval')
    def test_loopback_origin_and_token(self):
        server=make_server(self.store,0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base='http://'+server.address
        try:
            with urllib.request.urlopen(base) as r:self.assertEqual(r.status,200)
            for headers in [{},{'X-Review-Token':server.token,'Origin':'https://other.example'},{'X-Review-Token':server.token,'Host':'attacker.example'}]:
                with self.assertRaises(urllib.error.HTTPError) as err:urllib.request.urlopen(urllib.request.Request(base+'/api/reviews',headers=headers))
                self.assertEqual(err.exception.code,403)
            with urllib.request.urlopen(urllib.request.Request(base+'/api/reviews',headers={'X-Review-Token':server.token})) as r:self.assertEqual(json.load(r),[])
        finally:server.shutdown();server.server_close();thread.join()
    def test_repeated_launcher_does_not_reset_running_job(self):
        self.store.auto_extract=True
        self.store.save(example(),0)
        self.store.db.execute("UPDATE jobs SET status='running'");self.store.db.commit()
        server=make_server(self.store,0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with patch('sys.argv',['writing-review','--data-dir',str(self.base/'data'),'--port',str(server.server_port),'--no-browser']):main()
            self.assertEqual(self.store.get('demo')['learning']['status'],'running')
        finally:server.shutdown();server.server_close();thread.join()
    def test_default_saves_plain_files_without_model_calls(self):
        with patch('writing_review.memory.extract') as model:
            saved=self.store.save(example(),0)
            self.assertFalse(self.store.learn_once())
            model.assert_not_called()
        self.assertEqual(saved['learning']['status'],'manual')
        self.assertEqual(saved['storage']['status'],'exported')
        folder=self.store.review_dir/'demo'
        self.assertEqual(json.loads((folder/'latest.json').read_text(encoding='utf-8'))['comments'][0]['id'],'C1')
        self.assertIn('Start with the central argument.',(folder/'latest.md').read_text(encoding='utf-8'))
        self.assertTrue((self.store.review_dir/'AI读取说明.md').exists())
    def test_versioned_handoff_pointer_and_duplicate_save(self):
        a=self.store.save(example(),0);changed=example();changed['paragraphs'][0]['current']='A clearer sentence.'
        self.store.save(changed,a['version']);self.store.save(changed,2)
        folder=self.store.review_dir/'demo'
        pointer=json.loads((folder/'CURRENT.json').read_text(encoding='utf-8'))
        self.assertEqual(pointer['version'],2)
        for kind,path in pointer['files'].items():
            self.assertEqual(hashlib.sha256((folder/path).read_bytes()).hexdigest(),pointer['sha256'][kind])
        self.assertEqual(len(list((folder/'history').glob('*.json'))),2)
        self.assertEqual(json.loads((folder/'history/v000001.json').read_text(encoding='utf-8'))['paragraphs'][0]['current'],example()['paragraphs'][0]['current'])
    def test_export_failure_preserves_database_and_retry(self):
        self.store.save(example(),0)
        changed=example();changed['paragraphs'][0]['current']='Updated.'
        real=memory.atomic
        def fail_pointer(path,text):
            if Path(path).name=='CURRENT.json':raise PermissionError('Vault unavailable')
            real(path,text)
        with patch('writing_review.handoff.atomic',side_effect=fail_pointer):
            saved=self.store.save(changed,1)
        self.assertEqual(saved['version'],2);self.assertEqual(saved['storage']['status'],'retry')
        folder=self.store.review_dir/'demo'
        self.assertEqual(json.loads((folder/'CURRENT.json').read_text(encoding='utf-8'))['version'],1)
        self.assertEqual(self.store.export('demo')['storage']['status'],'exported')
        self.assertEqual(json.loads((folder/'CURRENT.json').read_text(encoding='utf-8'))['version'],2)
    def test_existing_database_can_backfill_to_configured_folder(self):
        self.store.save(example(),0)
        other=Store(self.base/'data',self.vault,review_dir=self.base/'fixed-inbox')
        try:
            self.assertEqual(other.export_all()[0]['status'],'exported')
            self.assertTrue((self.base/'fixed-inbox/demo/latest.md').exists())
        finally:other.db.close()

if __name__=='__main__':unittest.main()
