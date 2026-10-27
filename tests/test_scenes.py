import hashlib,json,sqlite3,tempfile,unittest
from pathlib import Path
from writing_review import scenes,memory
from writing_review.server import Store

class SceneTests(unittest.TestCase):
    def test_only_three_scenes_and_legacy_mapping(self):
        self.assertEqual(list(scenes.SCENES.values()),['学术写作','基金写作','通用'])
        for old,expected in [('introduction','academic'),('abstract','academic'),('grant','grant'),('report','general'),('general','general'),(None,'general')]:
            with self.subTest(old=old):self.assertEqual(scenes.scene(old),expected)
    def test_preferences_do_not_spill_between_scenes_or_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault=Path(tmp);folder=vault/'写作复利/偏好条目';folder.mkdir(parents=True)
            for scope in ['general','academic','introduction','abstract','grant','report']:
                item={'id':scope,'scope':scope,'status':'active','principle':scope}
                (folder/(scope+'.md')).write_text('<!-- writing-review:'+json.dumps(item)+' -->\nRULE_'+scope,encoding='utf-8')
            academic=memory.profile(vault,{'academic'})
            self.assertIn('RULE_academic',academic);self.assertIn('RULE_general',academic)
            self.assertNotIn('RULE_introduction',academic);self.assertNotIn('RULE_abstract',academic);self.assertNotIn('RULE_grant',academic)
            grant=memory.profile(vault,scenes.applicable({'scope':'grant'}))
            self.assertIn('RULE_grant',grant);self.assertNotIn('RULE_academic',grant)
            intro=memory.profile(vault,scenes.applicable({'scope':'academic','preferenceContext':['introduction']}))
            self.assertIn('RULE_introduction',intro);self.assertNotIn('RULE_abstract',intro)
            self.assertEqual(scenes.constraints({'scope':'grant','preferenceContext':['introduction']}),[])
    def test_new_manuscript_defaults_to_general(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(tmp)
            try:
                saved=store.save({'id':'new','paragraphs':[{'id':'P1','original':'Plain text.','current':'Plain text.'}],'comments':[]},0)
                self.assertEqual(saved['scope'],'general')
            finally:store.db.close()
    def test_old_snapshot_is_unchanged_and_next_round_inherits_scene_and_condition(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            old={'id':'legacy','title':'Old review','scope':'introduction','schemaVersion':2,'roundId':'old',
                 'sourceSha256':hashlib.sha256(b'Old text.').hexdigest(),
                 'paragraphs':[{'id':'P1','original':'Old text.','current':'Old text.'}],'comments':[]}
            encoded=json.dumps(old,ensure_ascii=False,sort_keys=True)
            db=sqlite3.connect(folder/'reviews.sqlite3');db.execute('CREATE TABLE reviews(id TEXT PRIMARY KEY,version INTEGER,body TEXT)')
            db.execute('INSERT INTO reviews VALUES(?,?,?)',('legacy',7,encoded));db.commit();db.close()
            store=Store(folder)
            try:
                store.export('legacy');before=(store.review_dir/'legacy/history/v000007.json').read_bytes()
                self.assertEqual(store.get('legacy')['scope'],'introduction')
                child=store.create_round({'parentReviewId':'legacy','expectedVersion':7,'approvalNote':'User approved in chat.',
                    'review':{'paragraphs':[{'id':'P1','original':'Revised.','current':'Revised.'}],'comments':[]},'responses':[]})
                self.assertEqual(child['scope'],'academic');self.assertEqual(child['preferenceContext'],['introduction'])
                self.assertEqual(store.db.execute('SELECT body FROM reviews WHERE id=?',('legacy',)).fetchone()[0],encoded)
                self.assertEqual((store.review_dir/'legacy/history/v000007.json').read_bytes(),before)
            finally:store.db.close()

if __name__=='__main__':unittest.main()
