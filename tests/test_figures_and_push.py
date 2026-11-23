"""v0.5: figure cards (asset route, handoff labels) and LaTeX push conversion. Synthetic data only."""
import importlib.util, json, tempfile, threading, unittest, urllib.request, urllib.error
from pathlib import Path
from writing_review.server import Store, make_server

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('push_latex', ROOT/'tools'/'push_latex.py')
push = importlib.util.module_from_spec(spec); spec.loader.exec_module(push)

PNG = bytes.fromhex('89504e470d0a1a0a0000000d4948445200000001000000010806000000'
                    '1f15c4890000000d49444154789c6300010000000500010d0a2db40000000049454e44ae426082')

def figure_review():
    return {'id':'figdemo','title':'Synthetic figures','scope':'academic','assetSet':'figdemo',
            'paragraphs':[{'id':'P1','original':'Some text.','current':'Some text.','label':'3.1 ¶1','heading':'3.1 Results'},
                          {'id':'P2','original':'Fig. 1. A caption.','current':'Fig. 1. A caption.','label':'Fig. 1',
                           'kind':'figure','image':'Fig1.png','imagePath':'C:/x/Fig1.png'}],
            'comments':[{'id':'C1','paragraphId':'P2','quote':'','wholeParagraph':True,'text':'Change the colour bar.'}]}

class FigureTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name)
        self.store=Store(self.base/'data',review_dir=self.base/'reviews')
        self.server=make_server(self.store,0);self.url='http://'+self.server.address
        threading.Thread(target=self.server.serve_forever,daemon=True).start()
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.store.db.close();self.tmp.cleanup()

    def test_figure_comment_is_saved_with_label_and_image(self):
        saved=self.store.save(figure_review(),0)
        md=(Path(saved['storage']['directory'])/'latest.md').read_text(encoding='utf-8')
        self.assertIn('## P2 · Fig. 1',md)
        self.assertIn('图片：C:/x/Fig1.png',md)
        self.assertIn('意见：Change the colour bar.',md)

    def test_asset_route_serves_only_images_inside_assets(self):
        folder=self.store.folder/'assets'/'figdemo';folder.mkdir(parents=True)
        (folder/'Fig1.png').write_bytes(PNG)
        with urllib.request.urlopen(self.url+'/asset/figdemo/Fig1.png') as r:
            self.assertEqual(r.headers['Content-Type'],'image/png');self.assertEqual(r.read(),PNG)
        for bad in ['/asset/figdemo/../reviews.sqlite3','/asset/figdemo/Fig1.txt','/asset/..%2F/Fig1.png']:
            with self.assertRaises(urllib.error.HTTPError) as ctx:urllib.request.urlopen(self.url+bad)
            self.assertEqual(ctx.exception.code,404)

class PushLatexTests(unittest.TestCase):
    def test_sections_figures_tables_numbers_and_citations(self):
        with tempfile.TemporaryDirectory() as d:
            d=Path(d);(d/'sections').mkdir()
            (d/'main.tex').write_text('\\input{numbers.tex}\n',encoding='utf-8')
            (d/'numbers.tex').write_text('\\nvdef{a.p}{0.007}\n\\nvdef{a.rho}{\\ensuremath{-}0.73}\n',encoding='utf-8')
            (d/'main.aux').write_text('\\newlabel{sec:r}{{3.2}{5}}\n\\newlabel{fig:x}{{4}{6}}\n\\newlabel{tab:t}{{1}{7}}\n'
                                      '\\bibcite{Smith}{{2}{}{{Smith et~al.}}{{}}}\n',encoding='utf-8')
            (d/'sections'/'s.tex').write_text(
                '\\subsection{Results}\\label{sec:r}\n% a comment\nThe gradient ($\\rho$~=~\\nv{a.rho}, \\pv{a}; Fig.~\\ref{fig:x}) '
                'follows \\citet{Smith}.\n\nSecond paragraph \\citep{Smith}.\n\n'
                '\\begin{figure}[!htb]\n\\figfile{Fig4_x}\n\\caption{A figure.}\n\\label{fig:x}\n\\end{figure}\n\n'
                '\\begin{table}[!htb]\n\\caption{Metrics.}\n\\label{tab:t}\n\\begin{tabular}{ll}\n\\toprule\nA & B \\\\\n\\midrule\n1 & 2 \\\\\n\\bottomrule\n\\end{tabular}\n\\end{table}\n',
                encoding='utf-8')
            labels,cites=push.read_aux(d);conv=push.Converter(push.read_numbers(d),labels,cites)
            items=push.parse([d/'sections'/'s.tex'],conv)
        self.assertEqual([i['kind'] for i in items],['text','text','figure','table'])
        self.assertEqual(items[0]['heading'],'3.2 Results');self.assertEqual(items[0]['label'],'3.2 ¶1')
        self.assertEqual(items[0]['text'],'The gradient (ρ = −0.73, p = 0.007; Fig. 4) follows Smith et al. [2].')
        self.assertEqual(items[1]['text'],'Second paragraph [2].')
        self.assertEqual(items[2]['label'],'Fig. 4');self.assertEqual(items[2]['image'],'Fig4_x')
        self.assertIn('A | B',items[3]['text']);self.assertTrue(items[3]['text'].startswith('Table 1. Metrics.'))

if __name__=='__main__':unittest.main()
