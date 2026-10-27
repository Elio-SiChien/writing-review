"""Optional real-browser checks using synthetic text only."""
import json,os,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
from writing_review.server import Store,make_server
try:from playwright.sync_api import sync_playwright
except ImportError:sync_playwright=None

TEXT='Forecasts help teams prepare for changing conditions. Lower error alone does not establish timely decisions.\n\nThis synthetic manuscript compares two approaches under a common task.'

@unittest.skipIf(sync_playwright is None,'Install playwright for browser checks')
class BrowserTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.folder=Path(self.tmp.name);self.vault=self.folder/'vault';self.vault.mkdir()
        self.store=Store(self.folder/'data',self.vault);self.server=make_server(self.store,0)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.p=sync_playwright().start();executable=os.environ.get('WR_BROWSER')
        self.browser=self.p.chromium.launch(headless=True,**({'executable_path':executable} if executable else {}))
        self.context=self.browser.new_context(accept_downloads=True);self.context.grant_permissions(['clipboard-read','clipboard-write'])
        self.page=self.context.new_page();self.errors=[];self.page.on('pageerror',lambda e:self.errors.append(str(e)))
        self.page.goto('http://'+self.server.address)
        self.assertEqual(self.page.locator('#scope option').all_text_contents(),['学术写作','基金写作','通用'])
        self.assertEqual(self.page.locator('#scope').input_value(),'general')
        self.page.locator('#import').set_input_files({'name':'Synthetic introduction.md','mimeType':'text/markdown','buffer':TEXT.encode()})
        self.page.wait_for_selector('#e-P1')
    def tearDown(self):
        self.browser.close();self.p.stop();self.server.shutdown();self.server.server_close();self.thread.join();self.store.db.close();self.tmp.cleanup()
    def select(self,end=9):
        self.page.evaluate('''end=>{const n=document.querySelector('#e-P1').firstChild,r=document.createRange();r.setStart(n,0);r.setEnd(n,end);getSelection().removeAllRanges();getSelection().addRange(r);}''',end)
    def comment(self,text='观点先行。',end=9):
        self.select(end);self.page.locator('#p-P1 .add-comment').click();self.page.locator('#comment-text').fill(text);self.page.locator('#save-comment').click()
        self.page.wait_for_function("()=>!document.querySelector('#compose').open")
    def data(self):return self.page.evaluate('WritingReview.getReview()')
    def next_request(self,data):
        return {'parentReviewId':data['id'],'expectedVersion':data['version'],'approvalNote':'User approved in the current chat.',
                'review':{'title':'Synthetic revised introduction','paragraphs':[{'id':'P1','original':'Forecasts should support decisions before conditions deteriorate.','current':'Forecasts should support decisions before conditions deteriorate.'}],'comments':[]},
                'responses':[{'commentId':c['id'],'status':'addressed','action':'Revised the sentence.'} for c in data['comments']]}
    def test_simple_ui_immediate_save_newest_first_edit_and_backup(self):
        p=self.page
        self.assertEqual(p.locator('nav button').all_text_contents(),['打开文稿','请AI出修改方案'])
        self.assertEqual(p.locator('#project').count(),0);self.assertEqual(p.locator('#demo').count(),0)
        legacy={'id':'legacy-section','title':'Legacy introduction','scope':'introduction','paragraphs':[{'id':'P1','original':'Legacy academic paragraph.','current':'Legacy academic paragraph.'}],'comments':[]}
        p.evaluate('d=>WritingReview.importData(d)',legacy)
        self.assertEqual(p.locator('#scope').input_value(),'academic')
        p.locator('#import').set_input_files({'name':'Another manuscript.md','mimeType':'text/markdown','buffer':TEXT.encode()})
        p.wait_for_function("()=>document.querySelector('#scope').value==='general'")
        self.assertEqual(self.data()['scope'],'general')
        self.comment();first=self.data()['comments'][0];rid=self.data()['id']
        exported=json.loads((self.store.review_dir/rid/'latest.json').read_text(encoding='utf-8'))
        self.assertEqual(exported['comments'][0]['text'],'观点先行。')
        self.comment('说明为什么需要提前准备。',17)
        newest=self.data()['comments'][-1]
        self.assertEqual(p.locator('.comment').first.get_attribute('data-id'),newest['id'])
        p.locator('#c-'+first['id']+' button').click();p.locator('#comment-text').fill('观点明确，表达通俗。');p.locator('#save-comment').click();p.wait_for_function("()=>!document.querySelector('#compose').open")
        self.assertEqual(self.data()['comments'][0]['createdAt'],first['createdAt'])
        self.assertEqual(p.locator('.comment').first.get_attribute('data-id'),newest['id'])
        self.assertIn('已编辑',p.locator('#c-'+first['id']).inner_text())
        self.assertEqual(p.evaluate("CSS.highlights.get('review-comments').size"),2)
        p.locator('#plan').click();p.wait_for_function("()=>document.querySelector('#status').textContent.includes('已复制')")
        copied=p.evaluate('navigator.clipboard.readText()');self.assertIn('未经我在当前聊天明确批准',copied);self.assertIn('先提出逐条修改方案',copied)
        p.reload();p.wait_for_selector('.comment');self.assertEqual(p.locator('.comment').count(),2)
        p.locator('#e-P1').click();p.keyboard.press('Control+End');p.evaluate("document.execCommand('insertText',false,' Extra sentence.')");p.evaluate('WritingReview.save()')
        p.keyboard.press('Control+z');p.evaluate('WritingReview.save()');self.assertNotIn('Extra sentence',p.locator('#e-P1').inner_text())
        p.locator('#e-P1').evaluate("e=>{e.dispatchEvent(new CompositionEvent('compositionstart'));e.dispatchEvent(new CompositionEvent('compositionend',{data:'测试'}));}")
        self.assertEqual(p.locator('#e-P1 mark').count(),0)
        self.assertIsNone(p.evaluate("WritingReview.locate({quote:'same'},'same same')"))
        p.evaluate('d=>WritingReview.importData(d)',self.data());self.assertEqual(p.locator('.comment').count(),2)
        result=p.evaluate("async()=>{try{await WritingReview.importData({paragraphs:[{id:'P1'}]});}catch(e){return e.message;}}")
        self.assertIn('损坏',result)
        p.locator('summary').click()
        with p.expect_download() as item:p.locator('#backup').click()
        file=self.folder/'backup.json';item.value.save_as(file);self.assertEqual(len(json.loads(file.read_text(encoding='utf-8'))['comments']),2)
        with p.expect_download() as item:p.evaluate('WritingReview.exportOffline()')
        offline=self.folder/'offline.html';item.value.save_as(offline)
        other=self.browser.new_context();tab=other.new_page();tab.goto(offline.as_uri());tab.wait_for_selector('.comment');self.assertEqual(tab.locator('.comment').count(),2);other.close()
        p.set_viewport_size({'width':390,'height':800})
        self.assertTrue(p.evaluate('document.documentElement.scrollWidth <= innerWidth'))
        p.set_viewport_size({'width':1280,'height':900})
        self.assertFalse(self.errors)
        if os.environ.get('WR_SCREENSHOT'):
            p.locator('#handoff-path').evaluate("e=>e.textContent='/demo/review-inbox （合成示例目录）'")
            p.locator('summary').click();p.screenshot(path=os.environ['WR_SCREENSHOT'],full_page=True)
    def test_new_round_auto_opens_and_history_is_read_only(self):
        self.comment();data=self.data();child=self.store.create_round(self.next_request(data))
        self.page.evaluate('WritingReview.checkLatest()')
        self.assertEqual(self.data()['id'],child['id']);self.assertEqual(self.data()['comments'],[])
        self.assertIn('第2轮',self.page.locator('#round-note').inner_text())
        self.page.locator('#documents').select_option(data['id']);self.page.wait_for_function("()=>document.querySelector('#e-P1').contentEditable==='false'")
        self.assertTrue(self.page.locator('#plan').is_disabled());self.assertEqual(self.page.locator('.comment button').count(),0)
        more=self.next_request(child);more['review']['paragraphs'][0]['original']='A third reviewed draft.';more['review']['paragraphs'][0]['current']='A third reviewed draft.'
        third=self.store.create_round(more)
        self.page.reload();self.page.wait_for_function("()=>document.querySelector('#round-note').textContent.includes('第3轮')")
        self.assertEqual(self.data()['id'],third['id'])
    def test_stale_recovery_survives_new_round(self):
        self.comment();data=self.data()
        self.page.locator('#e-P1').fill('Unsent text from the stale review')
        child=self.store.create_round(self.next_request(data))
        self.page.reload();self.page.wait_for_selector('#recovery:not([hidden])')
        with self.page.expect_download() as item:self.page.locator('#recovery').click()
        file=self.folder/'recovery.json';item.value.save_as(file)
        self.assertEqual(json.loads(file.read_text(encoding='utf-8'))['paragraphs'][0]['current'],'Unsent text from the stale review')
        self.assertEqual(self.data()['id'],child['id'])
    def test_file_write_failure_never_claims_obsidian_saved(self):
        with patch('writing_review.handoff.write_review',side_effect=PermissionError('Folder unavailable')):
            self.select();self.page.locator('#p-P1 .add-comment').click();self.page.locator('#comment-text').fill('Preserve this feedback.');self.page.locator('#save-comment').click()
            self.page.wait_for_function("()=>document.querySelector('#status').textContent.includes('重试')")
            self.assertNotIn('已保存到Obsidian',self.page.locator('#status').inner_text())
            self.assertEqual(len(self.store.get(self.data()['id'])['comments']),1)
        self.page.locator('#save-comment').click();self.page.wait_for_function("()=>!document.querySelector('#compose').open")
        self.assertEqual(len(self.data()['comments']),1)

if __name__=='__main__':unittest.main()
