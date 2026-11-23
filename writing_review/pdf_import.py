"""Convert a text PDF into review paragraphs with page labels.

PyMuPDF (``pip install pymupdf``) is an optional dependency: only this feature needs it.
Steps: read text blocks per page, order them for one or two columns, drop running
headers, footers and page numbers, then merge lines into paragraphs, joining words
hyphenated at a line break. Scanned PDFs without a text layer are rejected.
"""
from collections import Counter
import math, re

MISSING = '未安装 PyMuPDF，暂时不能转换 PDF。请在命令行运行 pip install pymupdf，然后重启写作复利。也可以先把稿件另存为 TXT 或 Markdown 再打开。'
SCANNED = '不支持扫描件：这个 PDF 没有可提取的文字层（可能是扫描图片）。请先用 OCR 软件转成可选中文字的 PDF，或导出为 TXT / Markdown 后再打开。'
ENCRYPTED = '这个 PDF 设置了打开密码，无法读取。请先另存为无密码的 PDF。'
EMPTY = '没有从 PDF 中识别出正文段落。'

PAGE_NUMBER = re.compile(r'^(?:page\s*|p\.\s*|第\s*)?[-\u2013\u2014]?\s*\d{1,4}\s*[-\u2013\u2014]?\s*(?:页)?(?:\s*(?:/|of)\s*\d{1,4})?$', re.I)
CJK = re.compile(r'[぀-ヿ㐀-鿿豈-﫿]')
ENDING = tuple('.?!。！？')
CLOSERS = '"\'”’)）]】」』'
HYPHENS = ('-', '\u2010', '\u00ad')
MARGIN = 0.09       # top and bottom share of the page treated as header/footer zone
REPEAT_SHARE = 0.4  # a margin line on at least this share of pages is a running header/footer

def _fitz():
    try:
        import fitz
    except ImportError:
        try:
            import pymupdf as fitz
        except ImportError:
            raise ValueError(MISSING) from None
    return fitz

def _norm(text):
    return re.sub(r'\s+', ' ', re.sub(r'\d+', '#', text)).strip().lower()

def _page_blocks(page):
    """Horizontal text blocks of a page: [{'bbox', 'lines': [{'text', 'x0', 'y0', 'x1', 'y1', 'size'}]}]."""
    data = page.get_text('dict')
    blocks = []
    for block in data.get('blocks', []):
        if block.get('type', 0) != 0:
            continue
        lines = []
        for line in block.get('lines', []):
            dx, dy = line.get('dir', (1, 0))
            if abs(dy) > 0.2 or dx <= 0:
                continue  # rotated text, typically axis labels inside figures
            spans = [s for s in line.get('spans', []) if s.get('text')]
            text = ''.join(s['text'] for s in spans)
            if not text.strip():
                continue
            x0, y0, x1, y1 = line['bbox']
            size = max((s.get('size', 0) for s in spans if s['text'].strip()), default=0)
            lines.append({'text': re.sub(r'\s+', ' ', text).strip(), 'x0': x0, 'y0': y0, 'x1': x1, 'y1': y1, 'size': size})
        if lines:
            x0 = min(l['x0'] for l in lines); x1 = max(l['x1'] for l in lines)
            y0 = min(l['y0'] for l in lines); y1 = max(l['y1'] for l in lines)
            blocks.append({'bbox': (x0, y0, x1, y1), 'lines': lines})
    return blocks

def order_blocks(blocks, width):
    """Reading order for one or two columns.

    Blocks spanning the page (titles, wide figures, single-column text) cut the page into
    bands; inside a band the left column is read top to bottom, then the right column.
    Each returned block gets 'column' (0 full width, 1 left, 2 right).
    """
    mid = width / 2
    def full(b):
        x0, _, x1, _ = b['bbox']
        return (x1 - x0) > 0.55 * width or (x0 < mid - 0.04 * width and x1 > mid + 0.04 * width)
    out, left, right = [], [], []
    def flush():
        out.extend(sorted(left, key=lambda b: b['bbox'][1])); out.extend(sorted(right, key=lambda b: b['bbox'][1]))
        left.clear(); right.clear()
    for b in sorted(blocks, key=lambda b: (b['bbox'][1], b['bbox'][0])):
        if full(b):
            flush(); b['column'] = 0; out.append(b)
        elif (b['bbox'][0] + b['bbox'][2]) / 2 < mid:
            b['column'] = 1; left.append(b)
        else:
            b['column'] = 2; right.append(b)
    flush()
    return out

def _drop_line_numbers(blocks):
    """Remove review line numbers: number-only lines stacked at one x position (5+ on a page)."""
    numeric = lambda l: re.fullmatch(r'\d{1,5}', l['text'])
    xs = Counter(round(l['x0'] / 4) for b in blocks for l in b['lines'] if numeric(l))
    column = {x for x, n in xs.items() if n >= 5}
    if not column:
        return blocks, False
    out = []
    for b in blocks:
        lines = [l for l in b['lines'] if not (numeric(l) and round(l['x0'] / 4) in column)]
        if lines:
            out.append({'bbox': _bbox(lines), 'lines': lines})
    return out, True

def _bbox(lines):
    return (min(l['x0'] for l in lines), min(l['y0'] for l in lines), max(l['x1'] for l in lines), max(l['y1'] for l in lines))

def _line_gap(blocks, share=0.5):
    """Typical vertical gap between consecutive lines on a page (the given quantile of gaps).

    Review manuscripts with line numbers are usually double spaced and PyMuPDF returns one
    block per line; their caller passes a higher quantile so single-spaced title and
    affiliation lines do not set the pitch.
    """
    gaps = []
    flat = [(b['column'], l) for b in blocks for l in b['lines']]
    for (c1, a), (c2, b) in zip(flat, flat[1:]):
        size = a['size'] or 10
        gap = b['y0'] - a['y1']
        if c1 == c2 and -0.3 * size <= gap < 2 * size:
            gaps.append(gap)
    gaps.sort()
    return gaps[min(len(gaps) - 1, int(len(gaps) * share))] if gaps else 0.0

def _merge_adjacent(blocks, line_gap):
    """Join blocks that continue each other in the same column (one block per line in some PDFs)."""
    out = []
    for b in blocks:
        if out:
            prev = out[-1]
            size = prev['lines'][-1]['size'] or 10
            gap = b['bbox'][1] - prev['bbox'][3]
            overlap = min(prev['bbox'][2], b['bbox'][2]) - max(prev['bbox'][0], b['bbox'][0])
            if b['column'] == prev['column'] and -0.3 * size < gap < max(0.6 * size, line_gap + 0.45 * size) and overlap > 0:
                prev['lines'] = prev['lines'] + b['lines']
                prev['bbox'] = (min(prev['bbox'][0], b['bbox'][0]), prev['bbox'][1], max(prev['bbox'][2], b['bbox'][2]), b['bbox'][3])
                continue
        out.append({'bbox': b['bbox'], 'lines': list(b['lines']), 'column': b['column']})
    return out

def _in_margin(line, height):
    return line['y1'] < MARGIN * height or line['y0'] > (1 - MARGIN) * height

def join_lines(a, b):
    """Join two lines of one paragraph, undoing a hyphenated line break."""
    if not a:
        return b
    if not b:
        return a
    if a.endswith(HYPHENS) and len(a) > 1 and a[-2].isalpha() and b[:1].islower():
        return a[:-1] + b
    if a.endswith('\u00ad'):
        return a[:-1] + b
    if CJK.match(a[-1]) and CJK.match(b[0]):
        return a + b
    return a + ' ' + b

def _ends_sentence(text):
    return text.rstrip(CLOSERS + ' ').endswith(ENDING)

def _split_block(lines, line_gap=0.0):
    """Split one block's lines into paragraphs (indent, short last line, vertical gap)."""
    left = min(l['x0'] for l in lines); right = max(l['x1'] for l in lines); width = max(right - left, 1)
    groups = [[lines[0]]]
    for prev, line in zip(lines, lines[1:]):
        size = line['size'] or prev['size'] or 10
        indent = line['x0'] - left > max(6, 0.03 * width) and prev['x0'] - left < 3 and len(groups[-1]) > 1
        short = prev['x1'] < right - 0.2 * width and _ends_sentence(prev['text'])
        gap = line['y0'] - prev['y1'] > max(0.7 * size, line_gap + 0.45 * size)
        if indent or short or gap:
            groups.append([line])
        else:
            groups[-1].append(line)
    paragraphs = []
    for group in groups:
        text = ''
        for line in group:
            text = join_lines(text, line['text'])
        paragraphs.append(text)
    return paragraphs

def _continues(prev, text, boundary):
    """Whether text continues the previous paragraph across a block, column or page."""
    if not prev or _ends_sentence(prev):
        return False
    if prev.endswith(HYPHENS) and text[:1].islower():
        return True
    if text[:1].islower():
        return True
    # Chinese text has no case: only join at a column or page break, after a long paragraph.
    return boundary and bool(CJK.match(prev[-1])) and bool(CJK.match(text[:1])) and len(prev) > 30

def _meaningful(text):
    return bool(re.search(r'[A-Za-zÀ-ɏͰ-ϿЀ-ӿ]{2,}', text) or CJK.search(text)) or len(text) >= 15

def convert(raw):
    """PDF bytes -> [{'text', 'page', 'pageEnd', 'label'}] in reading order."""
    fitz = _fitz()
    try:
        doc = fitz.open(stream=raw, filetype='pdf')
    except Exception as exc:
        raise ValueError('无法读取这个 PDF：' + str(exc)[:160]) from None
    try:
        if doc.needs_pass:
            raise ValueError(ENCRYPTED)
        pages = []
        chars = 0
        for page in doc:
            blocks = _page_blocks(page)
            chars += sum(len(re.sub(r'\s', '', l['text'])) for b in blocks for l in b['lines'])
            pages.append((page.number + 1, page.rect.width, page.rect.height, blocks))
        count = len(pages)
    finally:
        doc.close()
    if count == 0 or chars < max(1, 5 * count) and chars < 40:
        raise ValueError(SCANNED)

    # Running headers and footers: margin lines that repeat (digits ignored) on many pages.
    seen = Counter()
    for _, _, height, blocks in pages:
        seen.update({_norm(l['text']) for b in blocks for l in b['lines'] if _in_margin(l, height)})
    threshold = max(2, math.ceil(REPEAT_SHARE * count))
    repeated = {t for t, n in seen.items() if count >= 2 and n >= threshold}

    paragraphs = []  # dicts: text, page, pageEnd
    last_column = None
    for number, width, height, blocks in pages:
        kept = []
        every = [l for b in blocks for l in b['lines']]
        top = min((l['y0'] for l in every), default=0); bottom = max((l['y1'] for l in every), default=0)
        for b in blocks:
            # Page numbers: in the margin zone, or the very first or last line of the page.
            lines = [l for l in b['lines'] if not (PAGE_NUMBER.match(l['text']) and (_in_margin(l, height) or l['y0'] <= top + 0.5 or l['y1'] >= bottom - 0.5))
                     and not (_in_margin(l, height) and _norm(l['text']) in repeated)]
            if lines:
                kept.append({'bbox': _bbox(lines), 'lines': lines})
        kept, numbered = _drop_line_numbers(kept)
        ordered = order_blocks(kept, width)
        line_gap = _line_gap(ordered, 0.75 if numbered else 0.5)
        first_on_page = True
        for b in _merge_adjacent(ordered, line_gap):
            boundary = first_on_page or (b['column'] != last_column and b['column'] == 2)
            first_on_page = False; last_column = b['column']
            for i, text in enumerate(_split_block(b['lines'], line_gap)):
                if i == 0 and paragraphs and _continues(paragraphs[-1]['text'], text, boundary):
                    paragraphs[-1]['text'] = join_lines(paragraphs[-1]['text'], text)
                    paragraphs[-1]['pageEnd'] = number
                else:
                    paragraphs.append({'text': text, 'page': number, 'pageEnd': number})
    result = []
    for p in paragraphs:
        text = p['text'].strip()
        if not text or not _meaningful(text):
            continue
        label = 'p.' + str(p['page']) + ('-' + str(p['pageEnd']) if p['pageEnd'] != p['page'] else '')
        result.append({'text': text, 'page': p['page'], 'pageEnd': p['pageEnd'], 'label': label})
    if not result:
        raise ValueError(EMPTY)
    return result
