"""tools/cleanup_redundancy.py on temporary data only: dry run changes nothing, execute archives first."""
import importlib.util, json, sys, tempfile, unittest, zipfile
from pathlib import Path
from unittest.mock import patch
from writing_review.server import Store

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('cleanup_redundancy', ROOT/'tools'/'cleanup_redundancy.py')
cleanup = importlib.util.module_from_spec(spec); spec.loader.exec_module(cleanup)

def snapshot(rid, version, text):
    return json.dumps({'id': rid, 'version': version, 'title': 'T', 'paragraphs': [{'id': 'P1', 'original': text, 'current': text}], 'comments': []},
                      ensure_ascii=False, indent=2) + '\n'

class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.base = Path(self.tmp.name)
        self.inbox = self.base/'vault'/'写作复利'/'批注收件箱'
        # A legacy folder (named by ID) with three old snapshots, two of them identical.
        history = self.inbox/'doc'/'history'; history.mkdir(parents=True)
        (history/'v000001.json').write_text(snapshot('doc', 1, 'Same text.'), encoding='utf-8')
        (history/'v000002.json').write_text(snapshot('doc', 2, 'Same text.'), encoding='utf-8')
        (history/'v000003.json').write_text(snapshot('doc', 3, 'Other text.'), encoding='utf-8')
        (self.inbox/'doc'/'latest.json').write_text('{}', encoding='utf-8')
        orphan = self.inbox/'old-test'; orphan.mkdir()
        (orphan/'latest.md').write_text('# old', encoding='utf-8')
        self.store = Store(self.base/'data', vault=self.base/'vault')
        self.store.save({'id': 'doc', 'title': 'Doc', 'paragraphs': [{'id': 'P1', 'original': 'Now.', 'current': 'Now.'}], 'comments': []}, 0)
        self.store.db.close()
        self.files = sorted(p.relative_to(self.inbox).as_posix() for p in self.inbox.rglob('*') if p.is_file())

    def tearDown(self):
        self.tmp.cleanup()

    def run_tool(self, *extra):
        report = self.base/'report.md'
        argv = ['cleanup', '--data-dir', str(self.base/'data'), '--review-dir', str(self.inbox), '--report', str(report),
                '--backup-root', str(self.base/'backups'), *extra]
        with patch.object(sys, 'argv', argv), patch.object(cleanup, 'server_running', return_value=False):
            cleanup.main()
        return report.read_text(encoding='utf-8')

    def test_dry_run_reports_and_changes_nothing(self):
        text = self.run_tool()
        self.assertEqual(sorted(p.relative_to(self.inbox).as_posix() for p in self.inbox.rglob('*') if p.is_file()), self.files)
        self.assertIn('doc/history/v000001.json', text)
        self.assertIn('与 v000002 内容相同', text)
        self.assertIn('old-test/', text)
        self.assertIn('doc/latest.json', text)
        self.assertNotIn('doc/CURRENT.json', text.split('## 逐项清单')[1])

    def test_execute_archives_before_removing(self):
        self.run_tool('--execute', '--archive', str(self.base/'archive.zip'))
        remaining = sorted(p.relative_to(self.inbox).as_posix() for p in self.inbox.rglob('*') if p.is_file())
        self.assertEqual(remaining, ['AI读取说明.md', 'doc/CURRENT.json', 'doc/ROUND.json', 'doc/latest.md'])
        with zipfile.ZipFile(self.base/'archive.zip') as z:
            self.assertEqual(sorted(z.namelist()), ['doc/history/v000001.json', 'doc/history/v000002.json', 'doc/history/v000003.json',
                                                    'doc/latest.json', 'old-test/latest.md'])
        backup = next((self.base/'backups').glob('*_before_cleanup'))/'批注收件箱'
        self.assertEqual(sorted(p.relative_to(backup).as_posix() for p in backup.rglob('*') if p.is_file()), self.files)

if __name__ == '__main__':
    unittest.main()

class LegacyFolderTests(CleanupTests):
    """A folder from an older data directory, cited by revision notes, keeps its final version."""
    def setUp(self):
        super().setUp()
        legacy = self.inbox/'legacy-doc'; (legacy/'history').mkdir(parents=True)
        for v, t in ((1, 'Draft.'), (2, 'Final.')):
            (legacy/'history'/('v%06d.json' % v)).write_text(snapshot('legacy-doc', v, t), encoding='utf-8')
            (legacy/'history'/('v%06d.md' % v)).write_text('# ' + t, encoding='utf-8')
        (legacy/'latest.json').write_text(snapshot('legacy-doc', 2, 'Final.'), encoding='utf-8')
        (legacy/'latest.md').write_text('# Final.', encoding='utf-8')
        (legacy/'CURRENT.json').write_text(json.dumps({'documentId': 'legacy-doc', 'version': 2,
            'files': {'json': 'history/v000002.json', 'markdown': 'history/v000002.md'}}), encoding='utf-8')
        self.files = sorted(p.relative_to(self.inbox).as_posix() for p in self.inbox.rglob('*') if p.is_file())

    def test_execute_archives_before_removing(self):
        self.run_tool('--execute', '--archive', str(self.base/'archive.zip'))
        remaining = sorted(p.relative_to(self.inbox).as_posix() for p in self.inbox.rglob('*') if p.is_file() and p.parts[-3:][0] != 'doc')
        kept = [p for p in remaining if p.startswith('legacy-doc/')]
        self.assertEqual(kept, ['legacy-doc/CURRENT.json', 'legacy-doc/history/v000002.json', 'legacy-doc/history/v000002.md', 'legacy-doc/latest.md'])
        with zipfile.ZipFile(self.base/'archive.zip') as z:
            names = z.namelist()
        self.assertIn('legacy-doc/history/v000001.json', names)
        self.assertIn('legacy-doc/latest.json', names)
