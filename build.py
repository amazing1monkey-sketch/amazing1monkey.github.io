"""Build a bilingual static site from XLSX files using Python's standard library."""
from pathlib import Path, PurePosixPath
from zipfile import ZipFile
from xml.etree import ElementTree as ET
import argparse
import json
import posixpath
import re
import shutil
import sys
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
NS = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
      'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.avif', '.svg', '.bmp'}


def column_index(address):
    match = re.match(r'^([A-Z]+)[0-9]+$', address)
    if not match:
        raise ValueError(f'Invalid cell address: {address}')
    value = 0
    for letter in match[1]:
        value = value * 26 + ord(letter) - 64
    return value - 1


def read_xlsx(path):
    """Read sheet order, names and displayed text, including shared/inline strings."""
    with ZipFile(path) as archive:
        strings = []
        if 'xl/sharedStrings.xml' in archive.namelist():
            xml = ET.fromstring(archive.read('xl/sharedStrings.xml'))
            strings = [''.join(t.text or '' for t in node.findall('.//m:t', NS)) for node in xml]
        relations = ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))
        targets = {node.get('Id'): node.get('Target') for node in relations}
        workbook = ET.fromstring(archive.read('xl/workbook.xml'))
        pages = []
        for entry in workbook.findall('m:sheets/m:sheet', NS):
            target = targets[entry.get(f'{{{NS["r"]}}}id')]
            member = target.lstrip('/') if target.startswith('/') else posixpath.normpath(posixpath.join('xl', target))
            xml = ET.fromstring(archive.read(member))
            cells = {}
            for row in xml.findall('m:sheetData/m:row', NS):
                for cell in row.findall('m:c', NS):
                    address = cell.get('r')
                    if cell.find('m:f', NS) is not None:
                        raise ValueError(f'{path.name} / {entry.get("name")} / {address}: 请将公式转换为文本或数值后保存。')
                    kind = cell.get('t')
                    raw = cell.findtext('m:v', default='', namespaces=NS)
                    if kind == 's':
                        text = strings[int(raw)] if raw else ''
                    elif kind == 'inlineStr':
                        text = ''.join(t.text or '' for t in cell.findall('m:is//m:t', NS))
                    elif kind == 'b':
                        text = 'TRUE' if raw == '1' else 'FALSE'
                    elif kind == 'e':
                        raise ValueError(f'{path.name} / {entry.get("name")} / {address}: 单元格错误 {raw}')
                    else:
                        text = raw
                    if text and text.strip():
                        # Respect real line breaks and accept literal \\n from pasted text.
                        cells[(int(re.search(r'\d+', address)[0]), column_index(address))] = text.strip().replace('\\n', '\n')
            modules = []
            columns = sorted({column for _, column in cells})
            for column in columns:
                header = cells.get((1, column))
                values = [(row, value) for (row, col), value in sorted(cells.items()) if col == column and row > 1]
                if not header:
                    raise ValueError(f'{path.name} / {entry.get("name")}: 第 {column+1} 列有内容但第一行缺少模块名称。')
                modules.append({'title': header, 'items': [value for _, value in values]})
            pages.append({'title': entry.get('name'), 'modules': modules})
        if not pages:
            raise ValueError(f'{path.name}: 没有工作表。')
        return pages


def workbook_path(config, language):
    configured = config.get('workbooks', {}).get(language)
    if configured:
        path = ROOT / configured
        if not path.is_file():
            raise ValueError(f'未找到表格：{path}')
        return path
    candidates = [p for p in (ROOT / 'content').glob('*.xlsx') if not p.name.startswith('~$')]
    selected = [p for p in candidates if ('中文' in p.stem if language == 'zh' else ('英文' in p.stem or re.search(r'(^|_)EN($|_)', p.stem, re.I)))]
    if len(selected) != 1:
        raise ValueError(f'无法唯一识别 {language} 表格；请在 site.config.json 的 workbooks 中指定文件名。')
    return selected[0]


def build(output=None):
    config = json.loads((ROOT / 'site.config.json').read_text(encoding='utf-8'))
    files = [p for p in ROOT.rglob('*') if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
             and not any(part.startswith('.') or part in {'dist', 'node_modules'} for part in p.relative_to(ROOT).parts)]
    by_name = {}
    for path in files:
        by_name.setdefault(path.name.casefold(), []).append(path)
    warnings = []
    used_images = set()

    def parse_item(value, context):
        normalized = value.replace('\\', '/')
        if '\n' not in normalized and PurePosixPath(normalized).suffix.lower() in IMAGE_EXTENSIONS:
            direct = ROOT / normalized
            matches = [direct] if direct.is_file() and direct.resolve().is_relative_to(ROOT) else by_name.get(PurePosixPath(normalized).name.casefold(), [])
            if len(matches) > 1:
                raise ValueError(f'{context}: 图片名重复 {value}，请在单元格填写相对路径，如 assets/{value}。')
            if not matches:
                raise ValueError(f'{context}: 未找到图片 {value}。请将图片放入 assets/ 文件夹。')
            path = matches[0].resolve()
            if not path.is_relative_to(ROOT):
                raise ValueError(f'{context}: 图片必须位于网站文件夹内。')
            relative = path.relative_to(ROOT).as_posix()
            used_images.add(relative)
            return {'type': 'image', 'src': quote(relative, safe='/'), 'name': path.name}
        return {'type': 'text', 'text': value}

    languages = {}
    for language in ('zh', 'en'):
        pages = read_xlsx(workbook_path(config, language))
        for page in pages:
            for module in page['modules']:
                module['items'] = [parse_item(value, f'{language} / {page["title"]} / {module["title"]}') for value in module['items']]
        languages[language] = pages
    if len(languages['zh']) != len(languages['en']):
        warnings.append('中英文工作表数量不同：切换语言时，缺少对应页会回到该语言第一页。')
    first_text = lambda pages: next((item['text'].split('\n')[0] for module in pages[0]['modules'] for item in module['items'] if item['type'] == 'text'), '')
    site = {'languages': languages, 'names': {lang: config.get('name', {}).get(lang) or re.split(r'[（(]', first_text(pages))[0].strip() or ('个人主页' if lang == 'zh' else 'Personal website') for lang, pages in languages.items()}}
    js = '/* 自动从 Excel 生成；请修改 content/ 中的表格。 */\nwindow.SITE_DATA = ' + json.dumps(site, ensure_ascii=False, indent=2) + ';\n'
    (ROOT / 'site-data.js').write_text(js, encoding='utf-8')
    if output:
        destination = Path(output).resolve()
        if destination == ROOT or not destination.is_relative_to(ROOT):
            raise ValueError('输出目录必须是网站文件夹的子目录。')
        destination.mkdir(parents=True, exist_ok=True)
        # Publish only the current, referenced site assets; never the source workbooks.
        for filename in ['index.html', 'gallery.html', 'writings.html', 'app.js', 'styles.css', 'site-data.js', '.nojekyll']:
            shutil.copy2(ROOT / filename, destination / filename)
        for relative in used_images:
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, target)
    for warning in warnings:
        print(f'提示：{warning}', file=sys.stderr)
    print('已生成网站：' + ', '.join(f'{lang} {len(pages)} 个切页 / {sum(len(p["modules"]) for p in pages)} 个模块' for lang, pages in languages.items()))
    return site


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', help='可选静态发布目录，例如 dist')
    args = parser.parse_args()
    try:
        build(ROOT / args.output if args.output else None)
    except (ValueError, KeyError, ET.ParseError) as error:
        print(f'生成失败：{error}', file=sys.stderr)
        raise SystemExit(1)
