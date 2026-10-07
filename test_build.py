"""Contract checks for Excel parsing, adaptive pages and missing-image errors."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, main
from unittest.mock import patch
from zipfile import ZipFile
import json
import build


class ContentTests(TestCase):
    def test_supplied_workbooks_preserve_content(self):
        pages = build.read_xlsx(build.ROOT / 'content/网站内容_中文版规范版.xlsx')
        self.assertEqual(pages[0]['title'], 'Sheet1')
        self.assertEqual(len(pages[0]['modules']), 7)
        self.assertEqual(pages[0]['modules'][0]['items'][1], 'photo.jpg')
        self.assertIn('\n', pages[0]['modules'][3]['items'][0])

    def test_sparse_columns_shared_strings_and_sheet_order(self):
        # Minimal OOXML fixtures exercise only the parser, not an exported workbook.
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'parser-fixture.xlsx'
            with ZipFile(path, 'w') as archive:
                archive.writestr('xl/workbook.xml', '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="关于我" r:id="rId1"/><sheet name="影像" r:id="rId2"/><sheet name="文字" r:id="rId3"/></sheets></workbook>')
                archive.writestr('xl/_rels/workbook.xml.rels', '<Relationships><Relationship Id="rId1" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Target="/xl/worksheets/sheet2.xml"/><Relationship Id="rId3" Target="worksheets/sheet3.xml"/></Relationships>')
                archive.writestr('xl/sharedStrings.xml', '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><r><t>研究</t></r><r><t>方向</t></r></si></sst>')
                archive.writestr('xl/worksheets/sheet1.xml', '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="AA1" t="s"><v>0</v></c></row><row r="3"><c r="AA3" t="inlineStr"><is><t>文学 &amp; 文化</t></is></c></row></sheetData></worksheet>')
                for index in (2, 3):
                    archive.writestr(f'xl/worksheets/sheet{index}.xml', '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData/></worksheet>')
            pages = build.read_xlsx(path)
            self.assertEqual([page['title'] for page in pages], ['关于我', '影像', '文字'])
            self.assertEqual(pages[0]['modules'], [{'title':'研究方向', 'items':['文学 & 文化']}])
            self.assertEqual(pages[1]['modules'], [])

    def test_adaptive_pages_images_and_missing_image(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / 'site.config.json').write_text(json.dumps({'workbooks':{'zh':'zh.xlsx', 'en':'en.xlsx'}}))
            for name in ('zh.xlsx', 'en.xlsx'):
                (root / name).touch()
            (root / 'assets').mkdir()
            (root / 'assets/图片 one.JPG').write_bytes(b'test-image')
            def pages(path):
                return [{'title':f'{path.stem}-{i}', 'modules':[{'title':'Module', 'items':['A <script>text</script>', '图片 one.JPG']}]} for i in range(3)]
            with patch.object(build, 'ROOT', root), patch.object(build, 'read_xlsx', side_effect=pages):
                result = build.build()
                self.assertEqual(len(result['languages']['zh']), 3)
                item = result['languages']['en'][2]['modules'][0]['items'][1]
                self.assertEqual(item['type'], 'image')
                self.assertIn('%20', item['src'])
                self.assertEqual(result['languages']['en'][0]['modules'][0]['items'][0]['text'], 'A <script>text</script>')
                (root / 'assets/图片 one.JPG').unlink()
                with self.assertRaisesRegex(ValueError, '未找到图片'):
                    build.build()

    def test_preview_rebuilds_only_after_content_changes(self):
        import preview
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / 'content').mkdir()
            (root / 'site.config.json').write_text('{}')
            workbook = root / 'content/test.xlsx'
            workbook.write_bytes(b'first')
            with patch.object(preview, 'ROOT', root), patch.object(preview, 'last_state', None), patch.object(preview, 'build') as generate:
                preview.refresh()
                preview.refresh()
                self.assertEqual(generate.call_count, 1)
                workbook.write_bytes(b'new workbook content')
                preview.refresh()
                self.assertEqual(generate.call_count, 2)


if __name__ == '__main__':
    main()
