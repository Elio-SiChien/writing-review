"""Optional browser acceptance test: pip install playwright && playwright install chromium."""
import json, os, tempfile, threading, unittest
from pathlib import Path
from writing_review.server import Store, make_server
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright=None

@unittest.skipIf(sync_playwright is None,'Install playwright for browser checks')
class BrowserTests(unittest.TestCase):
    def test_highlight_edit_import_recovery_and_offline(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'data');server=make_server(store,0)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                with sync_playwright() as p:
                    executable=os.environ.get('WR_BROWSER')
                    browser=p.chromium.launch(headless=True,**({'executable_path':executable} if executable else {}))
                    page=browser.new_page(accept_downloads=True);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    page.goto('http://'+server.address);page.wait_for_selector('#e-P1')
                    page.evaluate('''() => {const n=document.querySelector('#e-P1').firstChild;let r=document.createRange();r.setStart(n,0);r.setEnd(n,9);getSelection().removeAllRanges();getSelection().addRange(r);}''')
                    page.locator('#p-P1 button').click();page.locator('#comment-text').fill('观点先行。');page.locator('#save-comment').click()
                    page.wait_for_timeout(800)
                    self.assertEqual(page.locator('.comment').count(),1)
                    self.assertEqual(page.evaluate("CSS.highlights.get('review-comments').size"),1)
                    page.reload();page.wait_for_selector('.comment');self.assertEqual(page.locator('.comment').count(),1)
                    # Overlapping comments never wrap or replace editable DOM nodes.
                    page.evaluate('''async()=>{const d=WritingReview.getReview();d.comments.push({...d.comments[0],id:'C-overlap',text:'Short and direct.'});await WritingReview.importData(d);}''')
                    self.assertEqual(page.evaluate("CSS.highlights.get('review-comments').size"),2)
                    page.locator('#e-P1').click();page.keyboard.press('Control+End');page.evaluate("document.execCommand('insertText',false,' Extra sentence.')")
                    page.wait_for_timeout(700);self.assertIn('Extra sentence.',page.locator('#e-P1').inner_text())
                    page.keyboard.press('Control+z');page.wait_for_timeout(700);self.assertNotIn('Extra sentence',page.locator('#e-P1').inner_text())
                    # Chinese IME events are handled without rewriting editor nodes.
                    page.locator('#e-P1').evaluate("e=>{e.dispatchEvent(new CompositionEvent('compositionstart'));e.dispatchEvent(new CompositionEvent('compositionend',{data:'测试'}));}")
                    self.assertEqual(page.locator('#e-P1 mark').count(),0)
                    self.assertIsNone(page.evaluate("WritingReview.locate({quote:'same'},'same same')"))
                    self.assertEqual(page.evaluate("WritingReview.locate({quote:'same',context:{before:'first '}},'first same second same').start"),6)
                    # Re-import has no duplicates and malformed JSON cannot overwrite.
                    page.evaluate('async()=>WritingReview.importData(WritingReview.getReview())')
                    self.assertEqual(page.locator('.comment').count(),2)
                    result=page.evaluate("async()=>{try{await WritingReview.importData({paragraphs:[{id:'P1'}]});}catch(e){return e.message;}}")
                    self.assertIn('损坏',result);self.assertEqual(page.locator('.comment').count(),2)
                    # A stale browser recovery copy must survive a newer server version.
                    latest=store.get('synthetic-demo');latest['paragraphs'][0]['current']+=' Other tab edit.'
                    store.save(latest,latest['version'])
                    page.locator('#e-P1').fill('Unsent text from stale tab')
                    page.reload();page.wait_for_selector('#recovery:not([hidden])')
                    with page.expect_download() as recovery:page.locator('#recovery').click()
                    recovered=Path(tmp)/'recovery.json';recovery.value.save_as(recovered)
                    self.assertEqual(json.loads(recovered.read_text(encoding='utf-8'))['paragraphs'][0]['current'],'Unsent text from stale tab')
                    self.assertIn('Other tab edit.',page.locator('#e-P1').inner_text())
                    with page.expect_download() as d:page.locator('#offline').click()
                    offline=Path(tmp)/'offline.html';d.value.save_as(offline)
                    other=browser.new_context();tab=other.new_page();tab.goto(offline.as_uri());tab.wait_for_selector('.comment')
                    self.assertEqual(tab.locator('.comment').count(),2)
                    self.assertEqual(tab.evaluate("CSS.highlights.get('review-comments').size"),2)
                    self.assertFalse(errors)
                    if os.environ.get('WR_SCREENSHOT'):
                        page.screenshot(path=os.environ['WR_SCREENSHOT'],full_page=True)
                    other.close();browser.close()
            finally:
                server.shutdown();server.server_close();thread.join();store.db.close()

if __name__=='__main__':unittest.main()
