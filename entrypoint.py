#!/usr/bin/env python3
import os
import stat
import sys

TARGET_UID = 1000
TARGET_GID = 1000

for path in ['/data/descargas', '/data/config', '/app/cache']:
    try:
        st = os.stat(path)
        TARGET_UID = st.st_uid
        TARGET_GID = st.st_gid
        break
    except OSError:
        continue

# Ensure sources/ is writable by the target user (Docker COPY creates files as root)
sources_dir = '/app/sources'
cache_dir = '/app/cache'
try:
    os.chown(sources_dir, TARGET_UID, TARGET_GID)
    for root, dirs, files in os.walk(sources_dir):
        for d in dirs:
            os.chown(os.path.join(root, d), TARGET_UID, TARGET_GID)
        for f in files:
            os.chown(os.path.join(root, f), TARGET_UID, TARGET_GID)
except OSError:
    pass

try:
    os.makedirs(cache_dir, exist_ok=True)
    os.chown(cache_dir, TARGET_UID, TARGET_GID)
except OSError:
    pass

os.setgroups([])
os.setgid(TARGET_GID)
os.setuid(TARGET_UID)
os.execvp(sys.argv[1], sys.argv[1:])
