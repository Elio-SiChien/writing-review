"""v0.5 steps 4 and 5: PDF drag-in conversion, no snapshot per comment, readable export folders.
Synthetic data only; PDFs are generated with PyMuPDF inside the test."""
import builtins, json, tempfile, threading, unittest, urllib.request, urllib.error, urllib.parse
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from writing_review.server import Store, make_server
from writing_review import handoff, pdf_import

try:
    import fitz
except ImportError:
    fitz = None

HEADER = 'Journal of Synthetic Tests 2026'
LEFT = [['Forecast systems help river', 'managers prepare for floods', 'when the hydro-', 'logical response is fast.'],
        ['A second left paragraph starts', 'here and ends here.']]
RIGHT = [['The right column is read only', 'after the whole left column.']]

def two_column_pdf(pages=3):
    doc = fitz.open()
    for n in range(1, pages+1):
        page = doc.new_page(width=595, height=842)
        page.insert_text((150, 40), HEADER, fontsize=9)
        page.insert_text((290, 815), str(n), fontsize=9)
        page.insert_text((60, 90), 'Title of page '+str(n)+' spanning the full width of the synthetic page layout', fontsize=12)
        y = 140
        for para in LEFT:
            for line in para:
                page.insert_text((60, y), line, fontsize=10); y += 13
            y += 20
        y = 140
        for para in RIGHT:
            for line in para:
                page.insert_text((320, y), line, fontsize=10); y += 13
    raw = doc.tobytes(); doc.close(); return raw

def scanned_pdf():
    doc = fitz.open(); page = doc.new_page(width=200, height=200)
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 40, 40), False); pix.clear_with(200)
    page.insert_image(fitz.Rect(10, 10, 190, 190), pixmap=pix)
    raw = doc.tobytes(); doc.close(); return raw

def review(rid='demo', title='论文2_讨论_第1轮'):
    return {'id': rid, 'title': title, 'paragraphs': [{'id': 'P1', 'original': 'Some text.', 'current': 'Some text.'}], 'comments': []}

@unittest.skipIf(fitz is None, 'PyMuPDF not installed')
class PdfConversionTests(unittest.TestCase):
    def test_two_columns_headers_page_numbers_and_hyphens(self):
        items = pdf_import.convert(two_column_pdf())
        texts = [i['text'] for i in items]
        self.assertFalse(any(HEADER in t for t in texts), texts)
        self.assertFalse(any(t.strip().isdigit() for t in texts), texts)
        page1 = [i['text'] for i in items if i['page'] == 1]
        self.assertEqual(page1[0], 'Title of page 1 spanning the full width of the synthetic page layout')
        self.assertEqual(page1[1], 'Forecast systems help river managers prepare for floods when the hydrological response is fast.')
        self.assertEqual(page1[2], 'A second left paragraph starts here and ends here.')
        self.assertEqual(page1[3], 'The right column is read only after the whole left column.')
        self.assertEqual(len(items), 12)
        self.assertEqual(items[4]['label'], 'p.2')

    def test_scanned_pdf_is_rejected_with_clear_message(self):
        with self.assertRaises(ValueError) as ctx:
            pdf_import.convert(scanned_pdf())
        self.assertIn('不支持扫描件', str(ctx.exception))

    def test_missing_pymupdf_gives_chinese_message(self):
        real = builtins.__import__
        def fake(name, *args, **kwargs):
            if name in ('fitz', 'pymupdf'):
                raise ImportError(name)
            return real(name, *args, **kwargs)
        with patch('builtins.__import__', side_effect=fake):
            with self.assertRaises(ValueError) as ctx:
                pdf_import.convert(b'%PDF-1.7')
        self.assertIn('pip install pymupdf', str(ctx.exception))

    def test_upload_endpoint_creates_listed_document_with_pdf_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp)/'data', review_dir=Path(tmp)/'reviews')
            server = make_server(store, 0); thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            try:
                raw = two_column_pdf(2)
                def post(body, name='合成 稿件.pdf'):
                    request = urllib.request.Request('http://'+server.address+'/api/pdf', data=body, method='POST',
                        headers={'X-Review-Token': server.token, 'Content-Type': 'application/pdf', 'X-File-Name': urllib.parse.quote(name)})
                    with urllib.request.urlopen(request) as r:
                        return json.load(r)
                data = post(raw)
                self.assertEqual(data['title'], '合成 稿件')
                self.assertEqual(data['paragraphs'][0]['label'], 'p.1')
                self.assertTrue((store.folder/'assets'/data['id']/'original.pdf').read_bytes() == raw)
                self.assertIn(data['id'], [d['id'] for d in store.list()])
                self.assertEqual(post(raw)['id'], data['id'])  # same file again reopens it
                self.assertEqual(len(store.list()), 1)
                with self.assertRaises(urllib.error.HTTPError) as ctx:
                    post(scanned_pdf(), 'scan.pdf')
                self.assertEqual(ctx.exception.code, 400)
                self.assertIn('不支持扫描件', json.load(ctx.exception)['error'])
                with self.assertRaises(urllib.error.HTTPError) as ctx:
                    post(b'not a pdf', 'x.pdf')
                self.assertEqual(ctx.exception.code, 400)
            finally:
                server.shutdown(); server.server_close(); thread.join(); store.db.close()

class ExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.base = Path(self.tmp.name)
        self.store = Store(self.base/'data', review_dir=self.base/'reviews')
    def tearDown(self):
        self.store.db.close(); self.tmp.cleanup()
    def history(self, rid):
        return [v for (v,) in self.store.db.execute('SELECT version FROM history WHERE id=? ORDER BY version', (rid,))]

    def test_comment_does_not_store_snapshot_but_text_change_does(self):
        first = self.store.save(review(), 0)
        data = review(); data['comments'] = [{'id': 'C1', 'paragraphId': 'P1', 'quote': '', 'text': 'Clarify.'}]
        second = self.store.save(data, first['version'])
        data['comments'][0]['text'] = 'Clarify the claim.'
        third = self.store.save(data, second['version'])
        self.assertEqual(third['version'], 3)
        self.assertEqual(self.history('demo'), [1])
        data['paragraphs'][0]['current'] = 'Edited text.'
        self.store.save(data, third['version'])
        self.assertEqual(self.history('demo'), [1, 4])
        folder = Path(self.store.get('demo')['storage']['directory'])
        self.assertEqual(sorted(p.name for p in folder.iterdir()), ['CURRENT.json', 'ROUND.json', 'latest.md'])
        pointer = json.loads((folder/'CURRENT.json').read_text(encoding='utf-8'))
        self.assertEqual(pointer['version'], 4)
        self.assertEqual(pointer['review']['comments'][0]['text'], 'Clarify the claim.')

    def test_new_round_stores_a_version(self):
        parent = self.store.save(review(), 0)
        child = self.store.create_round({'parentReviewId': 'demo', 'expectedVersion': parent['version'], 'approvalNote': 'Approved in chat.',
            'review': {'title': 'Next', 'paragraphs': [{'id': 'P1', 'original': 'New.', 'current': 'New.'}], 'comments': []}, 'responses': []})
        self.assertEqual(self.history(child['id']), [1])
        self.assertTrue(Path(child['storage']['directory']).name.endswith('_Next_第2轮'))

    def test_readable_folder_name_and_uniqueness(self):
        today = datetime.now().strftime('%Y%m%d')
        a = self.store.save(review('a1'), 0); b = self.store.save(review('b2'), 0)
        self.assertEqual(Path(a['storage']['directory']).name, today+'_论文2_讨论_第1轮')
        self.assertEqual(Path(b['storage']['directory']).name, today+'_论文2_讨论_第1轮_2')
        self.assertEqual(handoff.readable_name({'title': 'A: b/c?  d'}, 2, datetime(2026, 11, 19)), '20261119_A_b_c_d_第2轮')
        # The name is remembered: a later export on another day keeps the same folder.
        with patch('writing_review.handoff.readable_name', side_effect=AssertionError('must not rename')):
            again = self.store.save(dict(review('a1'), comments=[{'id': 'C1', 'paragraphId': 'P1', 'text': 'x'}]), 1)
        self.assertEqual(again['storage']['directory'], a['storage']['directory'])

    def test_existing_id_folder_keeps_its_name(self):
        legacy = self.store.review_dir/'old-doc'/'history'; legacy.mkdir(parents=True)
        (legacy/'v000001.json').write_text('{}', encoding='utf-8')
        saved = self.store.save(review('old-doc'), 0)
        self.assertEqual(Path(saved['storage']['directory']).name, 'old-doc')
        self.assertEqual((legacy/'v000001.json').read_text(encoding='utf-8'), '{}')

    def test_overwrite_protection(self):
        saved = self.store.save(review(), 0); folder = Path(saved['storage']['directory'])
        newer = self.store.get('demo'); newer['version'] = 1; newer['title'] = 'Changed under the same version'
        with self.assertRaises(ValueError):
            handoff.write_review(self.store.review_dir, newer, folder.name)
        older = self.store.get('demo'); older['version'] = 1
        pointer = json.loads((folder/'CURRENT.json').read_text(encoding='utf-8')); pointer['version'] = 5
        (folder/'CURRENT.json').write_text(json.dumps(pointer), encoding='utf-8')
        with self.assertRaises(ValueError):
            handoff.write_review(self.store.review_dir, older, folder.name)
        other = self.store.get('demo'); other['id'] = 'someone-else'
        with self.assertRaises(ValueError):
            handoff.write_review(self.store.review_dir, other, folder.name)

if __name__ == '__main__':
    unittest.main()
