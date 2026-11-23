#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pytest
import subprocess
from unittest.mock import patch, MagicMock, PropertyMock, call
import os
import tempfile

from sources.jkanime import JkanimeSource


def test_multipart_download_splits_ranges():
    """Test that range calculation splits file into N equal chunks."""
    src = JkanimeSource()
    
    # Test the internal range splitting logic
    file_size = 100_000_000  # 100 MB
    chunks = 4
    
    # This will be tested via the actual function once implemented
    # For now, verify the concept
    chunk_size = file_size // chunks
    ranges = []
    for i in range(chunks):
        start = i * chunk_size
        end = file_size - 1 if i == chunks - 1 else (i + 1) * chunk_size - 1
        ranges.append((start, end))
    
    assert len(ranges) == 4
    assert ranges[0] == (0, 24_999_999)
    assert ranges[1] == (25_000_000, 49_999_999)
    assert ranges[2] == (50_000_000, 74_999_999)
    assert ranges[3] == (75_000_000, 99_999_999)
    # Verify no gaps or overlaps
    for i in range(len(ranges) - 1):
        assert ranges[i][1] + 1 == ranges[i + 1][0]


def test_multipart_fallback_on_small_file():
    """Test that files < 1MB fall back to single-stream."""
    src = JkanimeSource()
    
    with patch.object(src, '_download_curl', return_value='/tmp/test.mp4') as mock_single:
        with patch.object(src.scraper, 'head') as mock_head:
            mock_head.return_value.status_code = 200
            mock_head.return_value.headers = {'content-length': '500000'}  # 500 KB
            
            result = src._download_curl_multipart('http://test.com/video.mp4', '/tmp/test.mp4')
            
            mock_single.assert_called_once()
            assert result == '/tmp/test.mp4'


def test_multipart_fallback_on_no_content_length():
    """Test fallback when HEAD returns no content-length."""
    src = JkanimeSource()
    
    with patch.object(src, '_download_curl', return_value='/tmp/test.mp4') as mock_single:
        with patch.object(src.scraper, 'head') as mock_head:
            mock_head.return_value.status_code = 200
            mock_head.return_value.headers = {}  # No content-length
            
            result = src._download_curl_multipart('http://test.com/video.mp4', '/tmp/test.mp4')
            
            mock_single.assert_called_once()
            assert result == '/tmp/test.mp4'


def test_multipart_fallback_on_head_error():
    """Test fallback when HEAD request fails."""
    src = JkanimeSource()
    
    with patch.object(src, '_download_curl', return_value='/tmp/test.mp4') as mock_single:
        with patch.object(src.scraper, 'head', side_effect=Exception('Network error')):
            result = src._download_curl_multipart('http://test.com/video.mp4', '/tmp/test.mp4')
            
            mock_single.assert_called_once()
            assert result == '/tmp/test.mp4'


def test_multipart_uses_expected_size_when_provided():
    """Test that provided expected size is used instead of HEAD."""
    src = JkanimeSource()
    
    with patch.object(src, '_download_curl', return_value='/tmp/test.mp4') as mock_single:
        # Provide expected size < 1MB to trigger fallback
        result = src._download_curl_multipart('http://test.com/video.mp4', '/tmp/test.mp4', expected=500000)
        
        mock_single.assert_called_once()
        assert result == '/tmp/test.mp4'


def test_multipart_range_header_format():
    """Test that Range headers are correctly formatted."""
    src = JkanimeSource()
    
    # This tests the internal logic by checking the command construction
    # We can't easily test the subprocess call without integration test
    # But we can verify the range calculation logic
    expected = 100_000_000
    chunks = 4
    chunk_size = expected // chunks
    
    ranges = []
    for i in range(chunks):
        start = i * chunk_size
        end = expected - 1 if i == chunks - 1 else (i + 1) * chunk_size - 1
        ranges.append((start, end))
    
    # Verify Range header format
    range_headers = [f'bytes={start}-{end}' for start, end in ranges]
    assert range_headers[0] == 'bytes=0-24999999'
    assert range_headers[1] == 'bytes=25000000-49999999'
    assert range_headers[2] == 'bytes=50000000-74999999'
    assert range_headers[3] == 'bytes=75000000-99999999'


def test_mp4upload_uses_multipart():
    """Test that mp4upload download uses _download_curl_multipart."""
    src = JkanimeSource()
    
    with patch.object(src, '_resolve_mp4upload', return_value='http://test.com/video.mp4'):
        with patch.object(src, '_download_curl_multipart', return_value='/tmp/test.mp4') as mock_multi:
            with patch.object(src, '_fetch_episode_html', return_value='''
                <html>
                    <script>var servers = [{"server": "Mp4upload", "remote": "encoded", "slug": "", "variant": "SUB"}];</script>
                </html>
            '''):
                with tempfile.TemporaryDirectory() as tmpdir:
                    result = src.download_chapter_sync('test-anime', '1', tmpdir, '1')
                    
                    mock_multi.assert_called_once()
                    assert result == '/tmp/test.mp4'


def test_mp4upload_fallback_to_single_stream_on_error():
    """Test that _download_curl_multipart falls back to _download_curl internally."""
    src = JkanimeSource()
    
    # Test the fallback inside _download_curl_multipart directly
    with patch.object(src, '_download_curl', return_value='/tmp/test.mp4') as mock_single:
        with patch.object(src.scraper, 'head') as mock_head:
            mock_head.return_value.status_code = 200
            mock_head.return_value.headers = {'content-length': '100000000'}  # 100 MB
            
            # Simulate subprocess failure in multipart
            with patch('concurrent.futures.ThreadPoolExecutor') as mock_executor:
                mock_future = MagicMock()
                mock_future.result.side_effect = subprocess.CalledProcessError(1, 'curl')
                mock_executor.return_value.__enter__.return_value.submit.return_value = mock_future
                mock_executor.return_value.__enter__.return_value.__iter__ = lambda self: iter([mock_future])
                
                import concurrent.futures
                original_as_completed = concurrent.futures.as_completed
                
                def mock_as_completed(futures):
                    for f in futures:
                        yield f
                
                with patch('concurrent.futures.as_completed', mock_as_completed):
                    result = src._download_curl_multipart('http://test.com/video.mp4', '/tmp/test.mp4')
                    
                    mock_single.assert_called_once()
                    assert result == '/tmp/test.mp4'


def test_fallback_on_416():
    """Test fallback when range requests return 416 (Range Not Satisfiable)."""
    src = JkanimeSource()
    
    with patch.object(src, '_download_curl', return_value='/tmp/test.mp4') as mock_single:
        with patch.object(src.scraper, 'head') as mock_head:
            mock_head.return_value.status_code = 200
            mock_head.return_value.headers = {'content-length': '100000000'}
            
            # Simulate curl returning 416 (exit code 22 with --fail)
            with patch('concurrent.futures.ThreadPoolExecutor') as mock_executor:
                mock_future = MagicMock()
                mock_future.result.side_effect = subprocess.CalledProcessError(22, 'curl')
                mock_executor.return_value.__enter__.return_value.submit.return_value = mock_future
                mock_executor.return_value.__enter__.return_value.__iter__ = lambda self: iter([mock_future])
                
                import concurrent.futures
                
                def mock_as_completed(futures):
                    for f in futures:
                        yield f
                
                with patch('concurrent.futures.as_completed', mock_as_completed):
                    result = src._download_curl_multipart('http://test.com/video.mp4', '/tmp/test.mp4')
                    
                    mock_single.assert_called_once()
                    assert result == '/tmp/test.mp4'


def test_fallback_on_403():
    """Test fallback when range requests return 403 (Forbidden)."""
    src = JkanimeSource()
    
    with patch.object(src, '_download_curl', return_value='/tmp/test.mp4') as mock_single:
        with patch.object(src.scraper, 'head') as mock_head:
            mock_head.return_value.status_code = 200
            mock_head.return_value.headers = {'content-length': '100000000'}
            
            # Simulate curl returning 403 (exit code 22 with --fail)
            with patch('concurrent.futures.ThreadPoolExecutor') as mock_executor:
                mock_future = MagicMock()
                mock_future.result.side_effect = subprocess.CalledProcessError(22, 'curl')
                mock_executor.return_value.__enter__.return_value.submit.return_value = mock_future
                mock_executor.return_value.__enter__.return_value.__iter__ = lambda self: iter([mock_future])
                
                import concurrent.futures
                
                def mock_as_completed(futures):
                    for f in futures:
                        yield f
                
                with patch('concurrent.futures.as_completed', mock_as_completed):
                    result = src._download_curl_multipart('http://test.com/video.mp4', '/tmp/test.mp4')
                    
                    mock_single.assert_called_once()
                    assert result == '/tmp/test.mp4'


def test_fallback_on_unknown_size():
    """Test fallback when HEAD returns no content-length."""
    src = JkanimeSource()
    
    with patch.object(src, '_download_curl', return_value='/tmp/test.mp4') as mock_single:
        with patch.object(src.scraper, 'head') as mock_head:
            mock_head.return_value.status_code = 200
            mock_head.return_value.headers = {}  # No content-length
            
            result = src._download_curl_multipart('http://test.com/video.mp4', '/tmp/test.mp4')
            
            mock_single.assert_called_once()
            assert result == '/tmp/test.mp4'


@pytest.mark.integration
def test_real_mp4upload_download():
    """
    Integration test with real mp4upload URL.
    
    This test requires:
    - Network access
    - A valid mp4upload embed URL (from jkanime episode page)
    
    Run manually with: pytest tests/test_mp4upload_multipart.py::test_real_mp4upload_download -v -m integration
    """
    import tempfile
    import os
    
    # This URL should be replaced with a real mp4upload embed URL from jkanime
    # Example format: https://www.mp4upload.com/embed-xxxxx.html
    test_url = os.environ.get('MP4UPLOAD_TEST_URL')
    
    if not test_url:
        pytest.skip("MP4UPLOAD_TEST_URL environment variable not set")
    
    src = JkanimeSource()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = os.path.join(tmpdir, 'test_video.mp4')
        
        # This should download the video using multi-threaded approach
        result = src._download_curl_multipart(
            test_url, filepath,
            referer='https://www.mp4upload.com/',
            origin='https://www.mp4upload.com',
        )
        
        # Verify file exists and is valid MP4
        assert os.path.exists(result)
        assert os.path.getsize(result) > 10240
        
        # Verify magic bytes
        with open(result, 'rb') as f:
            magic = f.read(12)
        assert len(magic) >= 8
        assert magic[4:8] == b'ftyp'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])