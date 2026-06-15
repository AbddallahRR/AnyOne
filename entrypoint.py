#!/usr/bin/env python3
import os
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

os.setgroups([])
os.setgid(TARGET_GID)
os.setuid(TARGET_UID)
os.execvp(sys.argv[1], sys.argv[1:])
