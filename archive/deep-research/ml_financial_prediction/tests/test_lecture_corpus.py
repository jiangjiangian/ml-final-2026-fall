"""Pure contract checks; no real PDF or external request in CI."""

import importlib.util
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / 'scripts/collect_lecture_corpus.py'
spec = importlib.util.spec_from_file_location('lecture_collector', MODULE)
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)


class LectureCorpusTests(unittest.TestCase):
    def test_requires_all_official_links_and_correct_course(self):
        links = ''.join(f'<a href="doc/{i:02d}_handout.pdf">lecture</a>' for i in range(1, 17))
        urls = collector.lecture_urls('foundations', links)
        self.assertEqual(len(urls), 16)
        self.assertTrue(urls[0].endswith('/01_handout.pdf'))
        with self.assertRaises(ValueError):
            collector.lecture_urls('techniques', links)
        with self.assertRaises(ValueError):
            collector.lecture_urls('other', links)

    def test_refuses_git_checkout_but_allows_external_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / '.git').mkdir()
            with self.assertRaises(ValueError):
                collector.validate_output_root(root / 'corpus')
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(collector.validate_output_root(tmp), Path(tmp).resolve())

    def test_unsafe_url_rejected_before_network(self):
        for url in ('https://example.com/doc/01_handout.pdf', 'file:///tmp/01_handout.pdf'):
            with self.assertRaises(ValueError):
                collector.fetch_pdf(url)


if __name__ == '__main__':
    unittest.main()
