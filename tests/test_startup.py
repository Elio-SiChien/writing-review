"""Regression: the launcher must not silently reuse a different dataset."""
import contextlib,io,json,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
from writing_review.server import Store,make_server,main

class StartupTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.vault=self.root/'vault';self.vault.mkdir()
        self.store=Store(self.root/'data',self.vault)
        self.store.save({'id':'synthetic','title':'Synthetic manuscript','paragraphs':[{'id':'P1','current':'A synthetic paragraph.'}],'comments':[]},0)
        self.server=make_server(self.store,0)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.store.db.close();self.tmp.cleanup()
    def run_launcher(self,folder):
        args=['writing-review','--data-dir',str(folder),'--vault',str(self.vault),'--port',str(self.server.server_port),'--no-browser']
        with patch('sys.argv',args),patch('writing_review.server.Store',side_effect=AssertionError('Must not open another Store')):
            main()
    def test_same_settings_reuse_with_visible_directory(self):
        out=io.StringIO()
        with contextlib.redirect_stdout(out):self.run_launcher(self.root/'data')
        self.assertIn(str(self.store.review_dir),out.getvalue())
        self.assertEqual(len(self.store.list()),1)
    def test_different_data_directory_is_rejected_without_overwriting(self):
        errors=io.StringIO()
        with contextlib.redirect_stderr(errors),self.assertRaises(SystemExit) as caught:
            self.run_launcher(self.root/'other-data')
        self.assertEqual(caught.exception.code,2)
        self.assertIn('配置不一致',errors.getvalue())
        self.assertEqual(self.store.get('synthetic')['paragraphs'][0]['current'],'A synthetic paragraph.')

if __name__=='__main__':unittest.main()
