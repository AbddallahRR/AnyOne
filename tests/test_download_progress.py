from core.download_progress import clear, get, report


class TestDownloadProgress:
    def test_report_with_total(self):
        report(1, 50, 100, 'Descargando video')
        fp = get(1)
        assert fp is not None
        assert fp['done'] == 50
        assert fp['total'] == 100
        assert fp['percent'] == 50
        assert fp['indeterminate'] is False
        assert fp['label'] == 'Descargando video'
        clear(1)

    def test_percent_rounds_down(self):
        report(2, 333, 1000)
        assert get(2)['percent'] == 33
        clear(2)

    def test_indeterminate_without_total(self):
        report(3, 0, None, 'Descargando HLS')
        fp = get(3)
        assert fp['percent'] is None
        assert fp['indeterminate'] is True
        clear(3)

    def test_indeterminate_with_total_zero(self):
        report(4, 10, 0)
        assert get(4)['indeterminate'] is True
        clear(4)

    def test_overwrite(self):
        report(5, 10, 100)
        report(5, 80, 100)
        assert get(5)['percent'] == 80
        clear(5)

    def test_get_unknown(self):
        assert get(999999) is None

    def test_clear(self):
        report(6, 1, 2)
        clear(6)
        assert get(6) is None

    def test_report_none_safe(self):
        report(7, 0, 0, '')
        fp = get(7)
        assert fp['indeterminate'] is True
        clear(7)
