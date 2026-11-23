"""Report (and, only when asked, archive) redundant files in the Writing Review vault export.

Default is a dry run: nothing in the vault or the database is changed. It writes a Markdown
report, by default to docs/清理清单_dryrun_<date>.md, listing:

- old history snapshots (history/vNNNNNN.json|md) that no CURRENT.json points to;
- duplicate snapshots whose content is identical apart from the version number;
- legacy latest.json copies when CURRENT.json already embeds the full record;
- orphan folders: export folders whose document is not in the SQLite database.

``--execute`` (run only after the user approved the dry-run report) first copies the whole
export folder to a backup and checks the file count, then writes the listed items into a
zip archive outside the vault, verifies every archived file, and only then removes the
originals from the vault. The database is never modified.

Usage:
    python -X utf8 tools/cleanup_redundancy.py                 # dry run, report only
    python -X utf8 tools/cleanup_redundancy.py --execute       # after approval
"""
from datetime import datetime
from pathlib import Path
import argparse, hashlib, json, os, re, shutil, sqlite3, sys, urllib.request, zipfile

PROJECT = Path(__file__).resolve().parents[1]
KEEP = {'CURRENT.json', 'ROUND.json', 'latest.md'}
HISTORY = re.compile(r'^v(\d{6})\.(json|md)$')

def default_data():
    return Path(os.environ.get('LOCALAPPDATA', Path.home() / '.local/share')) / 'WritingReview'

def review_dir(args):
    if args.review_dir:
        return Path(args.review_dir).resolve()
    config = Path(args.data_dir) / 'config.json'
    saved = json.loads(config.read_text(encoding='utf-8')) if config.exists() else {}
    if saved.get('review_dir'):
        return Path(saved['review_dir']).resolve()
    vault = args.vault or saved.get('vault')
    if vault:
        return (Path(vault) / '写作复利' / '批注收件箱').resolve()
    return (Path(args.data_dir) / 'reviews').resolve()

def read_db(path):
    """Review IDs, titles and stored history versions, opened read-only."""
    if not path.exists():
        raise SystemExit('Database not found: ' + str(path))
    db = sqlite3.connect('file:' + path.resolve().as_posix() + '?mode=ro', uri=True)
    try:
        reviews = {rid: json.loads(body).get('title', '') for rid, body in db.execute('SELECT id, body FROM reviews')}
        history = set(db.execute('SELECT id, version FROM history'))
        folders = {}
        try:
            for key, value in db.execute("SELECT key, value FROM state WHERE key LIKE 'exportFolder:%'"):
                folders[value] = key.split(':', 1)[1]
        except sqlite3.Error:
            pass
    finally:
        db.close()
    return reviews, history, folders

def size(path):
    return path.stat().st_size if path.is_file() else sum(f.stat().st_size for f in path.rglob('*') if f.is_file())

def human(n):
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024 or unit == 'GB':
            return (str(n) + ' B') if unit == 'B' else '%.1f %s' % (n, unit)
        n /= 1024

def load_json(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None

def content_key(path):
    """Hash of a snapshot with its version number removed, to find identical snapshots."""
    if path.suffix == '.json':
        data = load_json(path)
        if isinstance(data, dict):
            data.pop('version', None)
            return 'json:' + hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    text = path.read_text(encoding='utf-8', errors='replace').replace('\r\n', '\n')
    text = re.sub(r'^Document: `[^`]*` \| Version: \d+$', '', text, flags=re.M)
    return path.suffix + ':' + hashlib.sha256(text.encode()).hexdigest()

def scan(root, reviews, history, mapped):
    """Return (items, folders). Each item: dict(path, kind, size, folder, note)."""
    items, folders = [], []
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        if folder.name == '说明归档':
            continue  # archived reading guides, kept on purpose
        current = load_json(folder / 'CURRENT.json')
        owner = (current or {}).get('documentId') or mapped.get(folder.name) or folder.name
        info = {'name': folder.name, 'owner': owner, 'size': size(folder),
                'files': sum(1 for f in folder.rglob('*') if f.is_file()),
                'title': reviews.get(owner) or (current or {}).get('title') or ((load_json(folder / 'latest.json') or {}).get('title', '')),
                'modified': datetime.fromtimestamp(max([f.stat().st_mtime for f in folder.rglob('*')] or [folder.stat().st_mtime])).strftime('%Y-%m-%d %H:%M')}
        folders.append(info)
        legacy = owner not in reviews and isinstance((current or {}).get('files'), dict) and not folder.name.startswith('synthetic')
        if owner not in reviews and not legacy:
            note = '无 CURRENT.json' if current is None else '数据库中无文稿 ' + owner
            items.append({'path': folder, 'kind': 'orphan', 'size': info['size'], 'folder': folder.name, 'note': note, 'title': info['title']})
            info['status'] = 'orphan'
            continue
        # Legacy folders (exported from an older data directory) are cited by revision notes:
        # keep the version CURRENT.json points to and trim only the intermediate snapshots.
        info['status'] = 'legacy' if legacy else 'active'
        referenced = {(folder / p).resolve() for p in ((current or {}).get('files') or {}).values()}
        groups = {}
        for f in sorted((folder / 'history').glob('*')) if (folder / 'history').is_dir() else []:
            m = HISTORY.match(f.name)
            if f.is_file():
                groups.setdefault(content_key(f), []).append((int(m[1]) if m else 0, f))
        for group in groups.values():
            group.sort()
            # Within identical snapshots keep the one CURRENT.json points to, else the newest.
            keeper = next((x for x in group if x[1].resolve() in referenced), group[-1])
            for version, f in group:
                if f.resolve() in referenced:
                    continue
                duplicate = (version, f) != keeper
                note = ('与 v%06d 内容相同（仅版本号不同）' % keeper[0]) if duplicate else '旧版本快照'
                note += '；数据库存有该版本' if (owner, version) in history else '；数据库无该版本记录'
                items.append({'path': f, 'kind': 'duplicate' if duplicate else 'history', 'size': f.stat().st_size,
                              'folder': folder.name, 'note': note, 'version': version, 'inDb': (owner, version) in history})
        latest = folder / 'latest.json'
        pointed = folder / (((current or {}).get('files') or {}).get('json') or 'missing')
        if latest.is_file() and isinstance((current or {}).get('review'), dict):
            items.append({'path': latest, 'kind': 'latest-json', 'size': latest.stat().st_size, 'folder': folder.name,
                          'note': 'CURRENT.json 已内含完整记录'})
        elif latest.is_file() and pointed.is_file() and load_json(latest) == load_json(pointed):
            items.append({'path': latest, 'kind': 'latest-json', 'size': latest.stat().st_size, 'folder': folder.name,
                          'note': '与 CURRENT.json 指向的 ' + pointed.relative_to(folder).as_posix() + ' 内容相同'})
        for f in folder.iterdir():
            if f.is_file() and f.name not in KEEP and f.name != 'latest.json' and f.resolve() not in referenced:
                info.setdefault('other', []).append(f.name)
    return items, folders

LABELS = {'history': '旧历史快照（内容唯一）', 'duplicate': '重复快照（内容与更新的快照相同）',
          'latest-json': '旧版 latest.json 副本', 'orphan': '孤立目录（数据库中无此文稿）'}

def report(root, db_path, items, folders, reviews, out, executed=None):
    total = sum(i['size'] for i in items)
    all_size = sum(f['size'] for f in folders)
    lines = ['# 清理清单（' + ('已执行' if executed else '空跑，未改动任何文件') + '）', '',
             '- 生成时间：' + datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
             '- 交接目录：`' + str(root) + '`',
             '- 数据库（只读）：`' + str(db_path) + '`，文稿 ' + str(len(reviews)) + ' 份',
             '- 交接目录现有：' + str(len(folders)) + ' 个文稿目录，' + str(sum(f['files'] for f in folders)) + ' 个文件，' + human(all_size),
             '- **可释放：' + human(total) + '（' + str(len(items)) + ' 项）**，清理后约剩 ' + human(all_size - total), '',
             '保留不动：每个现有文稿目录的 CURRENT.json、ROUND.json、latest.md，以及 CURRENT.json 仍指向的旧版文件；目录外的 AI读取说明.md、当前审批流程.md、说明归档/。数据库不改。', '',
             '## 按类别', '', '| 类别 | 项数 | 大小 |', '|---|---:|---:|']
    for kind in ('history', 'duplicate', 'latest-json', 'orphan'):
        sel = [i for i in items if i['kind'] == kind]
        lines.append('| ' + LABELS[kind] + ' | ' + str(len(sel)) + ' | ' + human(sum(i['size'] for i in sel)) + ' |')
    snap = [i for i in items if i['kind'] in ('history', 'duplicate')]
    if snap:
        lines += ['', '旧快照中 ' + str(sum(1 for i in snap if i.get('inDb'))) + ' / ' + str(len(snap)) + ' 个文件的同版本记录仍在 SQLite 数据库 history 表中。']
    lines += ['', '## 现有文稿目录（只清理旧快照与重复副本）', '', '标“旧稿”的目录不在当前数据库中，但修订记录引用了它们的最终版本，所以保留 CURRENT.json 指向的版本，只归档中间快照。', '',
              '| 目录 | 标题 | 文件数 | 目录大小 | 可释放 |', '|---|---|---:|---:|---:|']
    for f in folders:
        if f['status'] not in ('active', 'legacy'):
            continue
        if f['status'] == 'legacy':
            f = dict(f, title='旧稿 · ' + str(f['title']))
        free = sum(i['size'] for i in items if i['folder'] == f['name'] and i['kind'] != 'orphan')
        lines.append('| `' + f['name'] + '` | ' + str(f['title']).replace('|', '/') + ' | ' + str(f['files']) + ' | ' + human(f['size']) + ' | ' + human(free) + ' |')
    orphans = [f for f in folders if f['status'] == 'orphan']
    lines += ['', '## 孤立目录（整个目录归档）', '', '这些目录不属于当前数据库中的任何文稿（多为早期测试、验收或其他数据目录导出的旧稿）。执行前请确认其中没有仍需要的批注。', '',
              '| 目录 | 标题 | 文件数 | 大小 | 最后修改 | 原因 |', '|---|---|---:|---:|---|---|']
    for f in orphans:
        reason = next(i['note'] for i in items if i['kind'] == 'orphan' and i['folder'] == f['name'])
        lines.append('| `' + f['name'] + '` | ' + str(f['title']).replace('|', '/') + ' | ' + str(f['files']) + ' | ' + human(f['size']) + ' | ' + f['modified'] + ' | ' + reason + ' |')
    others = [(f['name'], n) for f in folders for n in f.get('other', [])]
    if others:
        lines += ['', '## 未识别的文件（不处理）', ''] + ['- `' + a + '/' + b + '`' for a, b in others]
    lines += ['', '## 逐项清单', '']
    for i in items:
        rel = i['path'].relative_to(root).as_posix() + ('/' if i['path'].is_dir() else '')
        lines.append('- [' + LABELS[i['kind']].split('（')[0] + '] `' + rel + '` ' + human(i['size']) + ' · ' + i['note'])
    if executed:
        lines += ['', '## 执行记录', ''] + ['- ' + x for x in executed]
    else:
        lines += ['', '## 下一步', '', '确认清单无误后运行：', '', '```', 'python -X utf8 tools/cleanup_redundancy.py --execute', '```', '',
                  '执行时先把整个交接目录完整备份到库外并核对文件数，再把以上各项写入库外 zip 归档并逐个校验，校验通过后才从库中移走。']
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return total

def server_running(port=8765):
    try:
        with urllib.request.urlopen('http://127.0.0.1:%d/' % port, timeout=1) as r:
            return r.headers.get('X-Writing-Review') == '1'
    except Exception:
        return False

def execute(root, items, backup_root, archive):
    """Backup, archive with verification, then remove originals. Returns log lines."""
    log = []
    vault = root.parent.parent if root.parent.name == '写作复利' else root
    if archive.resolve().is_relative_to(vault) or archive.resolve().is_relative_to(root):
        raise SystemExit('The archive must be outside the vault export folder: ' + str(archive))
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup = backup_root / (stamp + '_before_cleanup') / root.name
    shutil.copytree(root, backup)
    src_files = [f for f in root.rglob('*') if f.is_file()]
    dst_files = [f for f in backup.rglob('*') if f.is_file()]
    if len(src_files) != len(dst_files) or sum(f.stat().st_size for f in src_files) != sum(f.stat().st_size for f in dst_files):
        raise SystemExit('Backup verification failed; nothing was removed: ' + str(backup))
    log.append('完整备份：`' + str(backup) + '`（' + str(len(dst_files)) + ' 个文件，已核对）')
    files = []
    for i in items:
        files += [f for f in i['path'].rglob('*') if f.is_file()] if i['path'].is_dir() else [i['path']]
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED) as z:
        for f in files:
            z.write(f, f.relative_to(root).as_posix())
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:
            raise SystemExit('Archive check failed; nothing was removed: ' + str(archive))
        for f in files:
            if z.read(f.relative_to(root).as_posix()) != f.read_bytes():
                raise SystemExit('Archive content differs for ' + str(f) + '; nothing was removed')
    log.append('归档：`' + str(archive) + '`（' + str(len(files)) + ' 个文件，逐个校验一致）')
    for f in files:
        f.unlink()
    for i in items:
        if i['path'].is_dir():
            shutil.rmtree(i['path'], ignore_errors=False)
        elif i['path'].parent.name == 'history' and i['path'].parent.is_dir() and not any(i['path'].parent.iterdir()):
            i['path'].parent.rmdir()
    log.append('已从交接目录移走 ' + str(len(files)) + ' 个文件')
    return log

def main():
    parser = argparse.ArgumentParser(description='Report redundant files in the Writing Review vault export (dry run by default).')
    parser.add_argument('--data-dir', type=Path, default=default_data())
    parser.add_argument('--vault', type=Path)
    parser.add_argument('--review-dir', type=Path)
    parser.add_argument('--report', type=Path, help='Report path (default docs/清理清单_dryrun_<date>.md)')
    parser.add_argument('--execute', action='store_true', help='Archive and remove the listed items (only after approval)')
    parser.add_argument('--backup-root', type=Path, default=PROJECT.parent / 'writing-review-backups')
    parser.add_argument('--archive', type=Path, help='Zip archive path outside the vault')
    parser.add_argument('--allow-running', action='store_true', help='Execute even while the service is running')
    args = parser.parse_args()
    root = review_dir(args)
    if not root.is_dir():
        raise SystemExit('Export folder not found: ' + str(root))
    db_path = Path(args.data_dir) / 'reviews.sqlite3'
    reviews, history, mapped = read_db(db_path)
    items, folders = scan(root, reviews, history, mapped)
    today = datetime.now().strftime('%Y%m%d')
    executed = None
    if args.execute:
        if server_running() and not args.allow_running:
            raise SystemExit('Writing Review is running. Close it first (or pass --allow-running).')
        archive = args.archive or args.backup_root / ('cleanup_archive_' + datetime.now().strftime('%Y%m%d_%H%M%S') + '.zip')
        executed = execute(root, items, args.backup_root, archive)
    out = args.report or PROJECT / 'docs' / (('清理清单_executed_' if executed else '清理清单_dryrun_') + today + '.md')
    total = report(root, db_path, items, folders, reviews, out, executed)
    print(('Executed' if executed else 'Dry run') + ': ' + str(len(items)) + ' items, ' + human(total) + ' -> ' + str(out))

if __name__ == '__main__':
    main()
