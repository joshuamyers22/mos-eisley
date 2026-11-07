"""Keep a real non-root PID stable until its scoped network observer is ready."""

import os
import sys

if os.getuid() == 0 or sys.stdin.buffer.readline(4) != b"go\n":
    raise SystemExit(1)
os.execv(sys.argv[1], sys.argv[1:])
