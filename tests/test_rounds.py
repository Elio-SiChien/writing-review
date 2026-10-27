import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from writing_review.server import Store

def source():
    return {'id':'first','title':'Synthetic introduction','scope':'introduction',
            'paragraphs':[{'id':'P1','original':'A useful forecast supports action.','current':'A useful forecast supports action.'}],
            'comments':[{'id':'C1','paragraphId':'P1','quote':'useful forecast','text':'Make the main point explicit.','createdAt':'2026-01-01T10:00:00Z'}]}

def request(version=1,status='addressed'):
    return {'parentReviewId':'first','expectedVersion':version,'approvalNote':'User explicitly approved the proposal in the current chat.',
            'review':{'title':'Synthetic introduction','paragraphs':[{'id':'P1','original':'Forecasts should support timely decisions.','current':'Forecasts should support timely decisions.'}],'comments':[]},
            'responses':[{'commentId':'C1','status':status,'action':'Clarify the opening or carry the unresolved request.'}]}

class RoundTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'data')
        self.parent=self.store.save(source(),0)
    def tearDown(self):self.store.db.close();self.tmp.cleanup()
    def test_unapproved_request_does_not_change_source_or_preferences(self):
        data=request();data['approvalNote']=''
        with patch('writing_review.memory.apply_suggestions') as learning:
            with self.assertRaises(ValueError):self.store.create_round(data)
            learning.assert_not_called()
        self.assertEqual(len(self.store.list()),1)
        self.assertEqual(self.store.get('first')['paragraphs'],source()['paragraphs'])
    def test_new_round_stable_identity_project_and_immutable_parent(self):
        folder=self.store.review_dir/'first'
        before=(folder/'history/v000001.json').read_bytes()
        child=self.store.create_round(request())
        self.assertEqual(child['project'],self.parent['project'])
        self.assertEqual(child['lineage']['manuscriptId'],self.parent['lineage']['manuscriptId'])
        self.assertEqual(child['lineage']['roundNumber'],2)
        self.assertEqual(child['version'],1)
        self.assertEqual(child['comments'],[])
        self.assertTrue(self.store.get('first')['lineage']['readOnly'])
        with self.assertRaises(RuntimeError):self.store.save(source(),1)
        self.store.export('first')
        self.assertEqual((folder/'history/v000001.json').read_bytes(),before)
    def test_source_version_changes_require_updated_proposal(self):
        changed=source();changed['comments'][0]['text']='A new request after the proposal.'
        self.store.save(changed,1)
        with self.assertRaises(RuntimeError):self.store.create_round(request())
        self.assertEqual(len(self.store.list()),1)
    def test_every_comment_needs_response(self):
        data=request();data['responses']=[]
        with self.assertRaises(ValueError):self.store.create_round(data)
        self.assertEqual(len(self.store.list()),1)
    def test_retry_creation_is_idempotent(self):
        first=self.store.create_round(request());again=self.store.create_round(request())
        self.assertEqual(first['id'],again['id']);self.assertEqual(len(self.store.list()),2)
    def test_unresolved_anchor_is_carried_without_fabricated_location(self):
        child=self.store.create_round(request(status='carried'))
        self.assertEqual(child['comments'][0]['id'],'C1')
        self.assertEqual(child['comments'][0]['quote'],'useful forecast')
        self.assertEqual(child['comments'][0]['carriedFrom'],'first')
    def test_legacy_lineage_link_does_not_rewrite_old_saved_versions(self):
        second=source();second['id']='second';second['paragraphs'][0]['original']='Different text';second['paragraphs'][0]['current']='Different text'
        self.store.save(second,0)
        old=(self.store.review_dir/'second/history/v000001.json').read_bytes()
        self.store.link_legacy_rounds('first','second')
        self.store.export('second')
        self.assertEqual(self.store.get('second')['lineage']['roundNumber'],2)
        self.assertEqual((self.store.review_dir/'second/history/v000001.json').read_bytes(),old)

if __name__=='__main__':unittest.main()
