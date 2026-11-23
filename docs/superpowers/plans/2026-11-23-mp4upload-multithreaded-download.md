# MP4Upload Multi-threaded Download Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Speed up MP4Upload downloads by splitting files into parallel range requests instead of single-stream curl.

**Architecture:** Modify `_download_curl` in `sources/jkanime.py` to detect file size via HEAD, split into N chunks (default 4), launch parallel curl processes with `Range: bytes=start-end` headers, and concatenate chunks on completion. Fall back to single-stream if range requests fail (416/403).

**Tech Stack:** Python 3.12+, curl, subprocess, threading/asyncio

**Spec:** This plan implements the multi-threaded download approach discussed in the conversation.

## Global Constraints

- Keep changes minimal — only modify `_download_curl` and add a helper function
- Preserve existing progress callback behavior (report combined progress)
- Preserve existing validation (magic bytes, size check, retry logic)
- Default to 4 parallel chunks, configurable via constant
- No new dependencies — use stdlib `concurrent.futures` or `threading`

## Review Focus

| Input / Condition | Expected Behavior |
|-------------------|-------------------|
| CDN returns 416 Range Not Satisfiable | Fall back to single-stream download |
| CDN returns 403 on range requests | Fall back to single-stream download |
| Partial chunk download fails | Retry that chunk once, then fail entire download |
| File size unknown (no Content-Length) | Fall back to single-stream download |
| Progress callback called | Reports combined bytes downloaded across all chunks |

---

### Task 1: Add multi-threaded download helper function

**Files:**
- Modify: `sources/jkanime.py:316-446` (around `_download_curl`)

**Interfaces:**
- Consumes: existing `_download_curl` signature
- Produces: new `_download_curl_multipart` function with same signature

- [ ] **Step 1: Write the failing test**

```python
# tests/test_mp4upload_multipart.py
import pytest
from sources.jkanime import JkanimeSource

def test_multipart_download_splits_ranges():
    src = JkanimeSource()
    # Mock HEAD response with content-length
    # Verify range calculation splits file into N chunks
    pass
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_mp4upload_multipart.py -v`
Expected: FAIL (function not defined)

- [ ] **Step 3: Implement `_download_curl_multipart` in `sources/jkanime.py`**

Add after `_download_curl`:
- `_MP4UPLOAD_CHUNKS = 4` constant
- `_download_curl_multipart(url, filepath, referer, origin, progress_cb, expected)`:
  1. HEAD request to get `content-length` (reuse existing logic)
  2. If no size or size < 1MB → delegate to `_download_curl`
  3. Split into N equal byte ranges
  4. Launch N parallel curl subprocesses with `Range: bytes=start-end` header
  5. Each writes to `filepath.part{N}`
  6. Track combined progress via callback
  7. On success: concatenate parts → `filepath`, validate magic bytes
  8. On any chunk failure (non-206, timeout, size mismatch): cleanup parts, fall back to `_download_curl`

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_mp4upload_multipart.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add sources/jkanime.py tests/test_mp4upload_multipart.py
git commit -m "feat: add multi-threaded download for mp4upload"
```

---

### Task 2: Integrate multi-threaded download into mp4upload resolver

**Files:**
- Modify: `sources/jkanime.py:930-950` (where `_download_curl` is called for Mp4upload)

**Interfaces:**
- Consumes: `_download_curl_multipart` from Task 1
- Produces: updated download flow

- [ ] **Step 1: Write the failing test**

```python
# tests/test_mp4upload_multipart.py
def test_mp4upload_uses_multipart():
    src = JkanimeSource()
    # Mock _resolve_mp4upload to return test URL
    # Verify _download_curl_multipart is called instead of _download_curl
    pass
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_mp4upload_multipart.py::test_mp4upload_uses_multipart -v`
Expected: FAIL

- [ ] **Step 3: Modify mp4upload download call site**

In `download_chapter_sync`, replace `_download_curl` call for Mp4upload with `_download_curl_multipart`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_mp4upload_multipart.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add sources/jkanime.py
git commit -m "feat: use multi-threaded download for mp4upload"
```

---

### Task 3: Add fallback handling and edge case tests

**Files:**
- Modify: `sources/jkanime.py` (fallback logic in `_download_curl_multipart`)
- Test: `tests/test_mp4upload_multipart.py`

**Interfaces:**
- Consumes: Task 1 & 2 implementation
- Produces: robust fallback behavior

- [ ] **Step 1: Write failing tests for fallback scenarios**

```python
def test_fallback_on_416():
    # Mock HEAD ok, range requests return 416
    # Verify falls back to _download_curl
    pass

def test_fallback_on_403():
    # Mock range requests return 403
    # Verify falls back to _download_curl
    pass

def test_fallback_on_unknown_size():
    # Mock HEAD returns no content-length
    # Verify falls back to _download_curl
    pass
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_mp4upload_multipart.py -v`
Expected: FAIL

- [ ] **Step 3: Implement fallback logic in `_download_curl_multipart`**

Add try/except around parallel download; on specific errors (416, 403, missing size), log warning and call `_download_curl`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_mp4upload_multipart.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add sources/jkanime.py tests/test_mp4upload_multipart.py
git commit -m "feat: add fallback for mp4upload multi-threaded download"
```

---

### Task 4: Integration test with real mp4upload URL (manual/optional)

**Files:**
- Test: `tests/test_mp4upload_multipart.py` (add integration test marked `@pytest.mark.integration`)

**Interfaces:**
- Consumes: Full implementation
- Produces: confidence it works end-to-end

- [ ] **Step 1: Add integration test (skipped by default)**

```python
@pytest.mark.integration
def test_real_mp4upload_download():
    # Requires network, real mp4upload embed URL
    # Verifies download completes and file is valid MP4
    pass
```

- [ ] **Step 2: Run manually to verify**

Run: `pytest tests/test_mp4upload_multipart.py::test_real_mp4upload_download -v -m integration`
Expected: PASS (manual verification)

- [ ] **Step 3: Commit**

```bash
git add tests/test_mp4upload_multipart.py
git commit -m "test: add integration test for mp4upload multi-threaded download"
```