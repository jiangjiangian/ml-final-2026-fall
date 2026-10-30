"""Collect linked public Lin MOOC handouts; preserve PDF, Markdown and page text.

Run with the isolated MarkItDown interpreter. Outputs must remain outside Git.
No lecture content is sent to an LLM/OCR service; conversion blocks socket calls.
"""

import argparse
import hashlib
import json
import os
import socket
import tempfile
from datetime import datetime, timezone
from html.parser import HTMLParser
from importlib.metadata import version
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urljoin

import requests

INDEX_URL = 'https://www.csie.ntu.edu.tw/~htlin/mooc/'
MAX_PDF_BYTES = 30 * 1024 * 1024


class LectureLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = set()

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            href = dict(attrs).get('href')
            if href:
                self.links.add(urljoin(INDEX_URL, href))


def lecture_urls(course, index_html):
    if course not in {'foundations', 'techniques'}:
        raise ValueError('unknown public course')
    parsed = LectureLinks()
    parsed.feed(index_html)
    numbers = range(1, 17) if course == 'foundations' else range(201, 217)
    urls = [INDEX_URL + f'doc/{number:02d}_handout.pdf' for number in numbers]
    if not set(urls) <= parsed.links:
        raise ValueError('official index does not link every requested handout')
    return urls


def validate_output_root(path):
    root = Path(path).resolve()
    if any((parent / '.git').exists() for parent in (root, *root.parents)):
        raise ValueError('lecture corpus must be stored outside Git')
    return root


def fetch_pdf(url):
    # Only URLs constructed from the fixed official index are accepted.
    if not url.startswith(INDEX_URL + 'doc/') or not url.endswith('_handout.pdf'):
        raise ValueError('not an official handout URL')
    with requests.get(url, timeout=(10, 90), stream=True, allow_redirects=False, verify=True) as response:
        response.raise_for_status()
        chunks, size = [], 0
        for chunk in response.iter_content(65536):
            size += len(chunk)
            if size > MAX_PDF_BYTES:
                raise ValueError('lecture PDF exceeds size limit')
            chunks.append(chunk)
    payload = b''.join(chunks)
    if not payload.startswith(b'%PDF-'):
        raise ValueError('official handout response is not a PDF')
    return payload


def private_write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix='.lecture-')
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(payload)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def collect_one(url, root):
    import pdfplumber
    from markitdown import MarkItDown

    name = url.rsplit('/', 1)[1]
    payload = fetch_pdf(url)
    digest = hashlib.sha256(payload).hexdigest()
    directory = root / name.removesuffix('.pdf') / digest[:16]
    pdf_path = directory / name
    private_write(pdf_path, payload)
    # Guard local parsing against accidental network/provider access.
    with patch.object(socket.socket, 'connect', side_effect=RuntimeError('network disabled during local conversion')):
        markdown = MarkItDown(enable_plugins=False).convert_local(pdf_path).markdown
    if not markdown.strip():
        raise ValueError('empty Markdown conversion')
    private_write(directory / 'lecture.md', markdown.encode())
    with pdfplumber.open(pdf_path) as document:
        pages = [{'pdf_page': i + 1, 'text': page.extract_text() or ''}
                 for i, page in enumerate(document.pages)]
    private_write(directory / 'pages.json', (json.dumps(pages, ensure_ascii=False, indent=2) + '\n').encode())
    # Page-numbered text is easier to audit than inferred Markdown layout.
    paged = '\n\n'.join(f"## PDF page {p['pdf_page']}\n\n{p['text']}" for p in pages)
    private_write(directory / 'pages.md', (paged + '\n').encode())
    manifest = {
        'source_url': url, 'official_index': INDEX_URL,
        'fetched_at': datetime.now(timezone.utc).isoformat(),
        'source_sha256': digest, 'source_bytes': len(payload),
        'markitdown_version': version('markitdown'), 'plugins_enabled': False,
        'network_during_conversion': 'socket connect blocked',
        'pdf_pages': len(pages), 'markdown_chars': len(markdown),
        'markdown_sha256': hashlib.sha256(markdown.encode()).hexdigest(),
        'page_text_sha256': hashlib.sha256(paged.encode()).hexdigest(),
        'pdf_path': str(pdf_path), 'markdown_path': str(directory / 'lecture.md'),
        'pages_path': str(directory / 'pages.json'),
        'reading_status': 'converted_not_yet_read',
        'limitation': 'PDF is authoritative; page text/Markdown can lose formulas and diagrams.',
    }
    private_write(directory / 'manifest.json', (json.dumps(manifest, indent=2) + '\n').encode())
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--course', choices=('foundations', 'techniques'), required=True)
    parser.add_argument('--out-dir', type=Path, required=True)
    args = parser.parse_args()
    root = validate_output_root(args.out_dir)
    with requests.get(INDEX_URL, timeout=(10, 30), allow_redirects=False, verify=True) as response:
        response.raise_for_status()
        index_html = response.text
    urls = lecture_urls(args.course, index_html)
    # Downloads/conversions sequential: the socket guard is process-global.
    results = []
    for url in urls:
        result = collect_one(url, root)
        results.append(result)
        private_write(root / 'catalog.json', (json.dumps(results, ensure_ascii=False, indent=2) + '\n').encode())
        print(json.dumps({k: result[k] for k in ('source_url', 'pdf_pages', 'markdown_chars', 'source_sha256')}), flush=True)


if __name__ == '__main__':
    main()
