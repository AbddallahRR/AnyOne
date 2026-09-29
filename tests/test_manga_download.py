import os
from concurrent.futures import ThreadPoolExecutor

from sources.common import MangaDownloadHelper


class FakeResponse:
    def __init__(self, body: bytes, fail: bool = False):
        self._body = body
        self._fail = fail

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def raise_for_status(self):
        if self._fail:
            raise RuntimeError('boom')

    def iter_content(self, size):
        yield self._body


def make_get(mapping: dict, errors: set | None = None):
    """Build a retry_get that serves *mapping* and fails for urls in *errors*."""
    errors = errors or set()

    def _get(url, **kwargs):
        if url in errors:
            return FakeResponse(b'', fail=True)
        return FakeResponse(mapping[url])

    return _get


class TestMakeChapterDir:
    def test_numeric_chapter_is_padded(self, tmp_path):
        d = MangaDownloadHelper.make_chapter_dir(str(tmp_path), '7')
        assert os.path.basename(d) == 'cap_0007'
        assert os.path.isdir(d)

    def test_decimal_chapter_keeps_fraction(self, tmp_path):
        d = MangaDownloadHelper.make_chapter_dir(str(tmp_path), '5.5')
        assert os.path.basename(d) == 'cap_0005_5'

    def test_non_numeric_chapter_used_verbatim(self, tmp_path):
        d = MangaDownloadHelper.make_chapter_dir(str(tmp_path), 'extra')
        assert os.path.basename(d) == 'cap_extra'


class TestDownloadImages:
    URLS = ['https://x.com/a.png', 'https://x.com/b.jpg']
    BODIES = {'https://x.com/a.png': b'AAA', 'https://x.com/b.jpg': b'BB'}

    def test_writes_numbered_files(self, tmp_path):
        failures = MangaDownloadHelper.download_images(
            self.URLS, str(tmp_path), retry_get=make_get(self.BODIES),
        )
        assert failures == 0
        assert sorted(os.listdir(tmp_path)) == ['0001.png', '0002.jpg']
        assert (tmp_path / '0001.png').read_bytes() == b'AAA'

    def test_reports_failures_without_raising(self, tmp_path):
        failures = MangaDownloadHelper.download_images(
            self.URLS, str(tmp_path),
            retry_get=make_get(self.BODIES, errors={'https://x.com/a.png'}),
        )
        assert failures == 1
        assert os.listdir(tmp_path) == ['0002.jpg']

    def test_skips_already_downloaded(self, tmp_path):
        (tmp_path / '0001.png').write_bytes(b'KEEP')
        calls: list[str] = []

        def _get(url, **kwargs):
            calls.append(url)
            return FakeResponse(self.BODIES[url])

        failures = MangaDownloadHelper.download_images(
            self.URLS, str(tmp_path), retry_get=_get,
        )
        assert failures == 0
        assert calls == ['https://x.com/b.jpg']
        assert (tmp_path / '0001.png').read_bytes() == b'KEEP'

    def test_progress_reports_every_image(self, tmp_path):
        seen: list[tuple[int, int]] = []
        MangaDownloadHelper.download_images(
            self.URLS, str(tmp_path), retry_get=make_get(self.BODIES),
            progress_cb=lambda i, total, msg: seen.append((i, total)),
        )
        assert seen == [(1, 2), (2, 2)]

    def test_concurrent_matches_sequential(self, tmp_path):
        seq_dir = tmp_path / 'seq'
        con_dir = tmp_path / 'con'
        seq_dir.mkdir()
        con_dir.mkdir()

        def _thread_local_get(url, **kwargs):
            # Mirrors what DynamicSource passes: own session per worker thread.
            with ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(lambda: FakeResponse(self.BODIES[url])).result()

        seq_failures = MangaDownloadHelper.download_images(
            self.URLS, str(seq_dir), retry_get=make_get(self.BODIES),
        )
        con_failures = MangaDownloadHelper.download_images(
            self.URLS, str(con_dir), retry_get=_thread_local_get, max_workers=4,
        )
        assert seq_failures == con_failures == 0
        assert sorted(os.listdir(seq_dir)) == sorted(os.listdir(con_dir))
        assert (con_dir / '0002.jpg').read_bytes() == b'BB'

    def test_concurrent_counts_failures(self, tmp_path):
        failures = MangaDownloadHelper.download_images(
            self.URLS, str(tmp_path),
            retry_get=make_get(self.BODIES, errors={'https://x.com/b.jpg'}),
            max_workers=2,
        )
        assert failures == 1
