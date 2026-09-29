import os
import tempfile

# Must run before core.settings is imported anywhere: the app reads db_dir and the
# download dirs from the environment at import time. Point them at a scratch dir so
# tests never touch the real database or the user's ~/DescargasComics.
_TMP = tempfile.mkdtemp(prefix='anyone-tests-')
os.environ.setdefault('db_dir', _TMP)
os.environ.setdefault('base_download_dir', _TMP)
