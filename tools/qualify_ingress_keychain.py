"""Explicit disposable macOS Keychain tests; a skipped run cannot qualify native use."""

import os
import sys
import unittest
from pathlib import Path


def main() -> int:
    if sys.platform != "darwin":
        print("Native ingress Keychain qualification requires macOS.", file=sys.stderr)
        return 1
    # Explicit invocation authorizes only the suite's randomly scoped accounts.
    os.environ["MOS_EISLEY_NATIVE_KEYCHAIN_QUALIFICATION"] = "1"
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
    suite = unittest.defaultTestLoader.loadTestsFromName(
        "test_conversation_schedule_keychain.NativeKeychainTests"
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return int(
        not result.wasSuccessful() or bool(result.skipped) or result.testsRun < 5
    )


if __name__ == "__main__":
    raise SystemExit(main())
