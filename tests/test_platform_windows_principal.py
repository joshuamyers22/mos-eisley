"""Bounded candidate-token faults and actual Windows qualification evidence."""

import base64
import ctypes
import os
import subprocess
import sys
import unittest
from collections.abc import Callable
from types import SimpleNamespace
from unittest.mock import patch

from mos_eisley.platform import windows_identity as native
from mos_eisley.platform.identity import (
    IdentityContextError,
    IdentityQueryError,
    UnsupportedPlatformError,
    WindowsPrincipal,
    current_principal,
)

SID = (
    bytes((1, 2, 0, 0, 0, 0, 0, 5))
    + (21).to_bytes(4, "little")
    + (0xFEDCBA98).to_bytes(4, "little")
)


class FakeApi:
    def __init__(self) -> None:
        self.closed: list[int] = []
        self.threads: list[int | None | OSError] = [None, None]
        self.calls: list[int] = []
        self.opened = 0
        self.required = ctypes.sizeof(native.TokenUser) + len(SID)
        self.returned = self.required
        self.pointer_offset: int | None = ctypes.sizeof(native.TokenUser)
        self.data = SID
        self.native_length = len(SID)
        self.query_errors: list[native.NativeTokenError] = []
        self.close_error: OSError | None = None
        self.process_error: OSError | None = None
        self.validation_error: ValueError | None = None
        self.validated: list[bytes] = []
        self.sizing_success = False
        self.sizing_error: native.NativeTokenError | None = None

    def thread_token(self) -> int | None:
        value = self.threads.pop(0)
        if isinstance(value, OSError):
            raise value
        return value

    def process_token(self) -> int:
        self.opened += 1
        if self.process_error:
            raise self.process_error
        return 17

    def token_user(self, token: int, buffer: native.TokenBuffer | None) -> int:
        assert token == 17
        self.calls.append(0 if buffer is None else ctypes.sizeof(buffer))
        if buffer is None:
            if self.sizing_success:
                return self.required
            if self.sizing_error:
                raise self.sizing_error
            raise native.NativeTokenError(122, self.required)
        if self.query_errors:
            raise self.query_errors.pop(0)
        base = ctypes.addressof(buffer)
        native.TokenUser.from_buffer(buffer).sid = (
            None if self.pointer_offset is None else base + self.pointer_offset
        )
        # Fixture writes never dereference a fault-injected pointer.
        offset = ctypes.sizeof(native.TokenUser)
        if offset + len(self.data) <= ctypes.sizeof(buffer):
            ctypes.memmove(base + offset, self.data, len(self.data))
        return self.returned

    def sid_length(self, sid: bytes) -> int:
        self.validated.append(sid)
        if self.validation_error:
            raise self.validation_error
        return self.native_length

    def close(self, token: int) -> None:
        self.closed.append(token)
        if self.close_error:
            raise self.close_error


class WindowsPrincipalFaultTests(unittest.TestCase):
    def test_adapter_import_is_inert_in_clean_process(self) -> None:
        code = """
import ctypes
from unittest.mock import patch
with patch.object(ctypes, 'WinDLL', create=True,
                  side_effect=AssertionError('eager system DLL loading')):
    import mos_eisley.platform.windows_identity
"""
        subprocess.run([sys.executable, "-c", code], check=True, timeout=5)

    def query(self, api: FakeApi) -> WindowsPrincipal:
        with (
            patch.object(native, "_require_candidate_host"),
            patch.object(native, "_token_api", return_value=api),
        ):
            return native.current_principal()

    def test_fresh_full_sid_and_cleanup(self) -> None:
        api = FakeApi()
        self.assertEqual(self.query(api), WindowsPrincipal(SID))
        self.assertEqual(api.calls, [0, api.required])
        self.assertEqual(api.closed, [17])
        api.threads = [None, None]
        api.data = SID[:-4] + (123).to_bytes(4, "little")
        self.assertEqual(self.query(api), WindowsPrincipal(api.data))
        self.assertEqual(api.opened, 2)
        self.assertEqual(api.closed, [17, 17])

    def test_reuse_bindings_but_never_cache_token_or_principal(self) -> None:
        api = FakeApi()
        api.threads = [None, None, None, None]
        with (
            patch.object(native, "_require_candidate_host"),
            patch.object(native, "_bindings", None),
            patch.object(native, "NativeTokenApi", return_value=api) as factory,
        ):
            first = native.current_principal()
            api.data = SID[:-4] + (999).to_bytes(4, "little")
            second = native.current_principal()
        factory.assert_called_once_with()
        self.assertNotEqual(first, second)
        self.assertEqual(api.opened, 2)
        self.assertEqual(api.closed, [17, 17])

    def test_impersonation_before_and_after_query(self) -> None:
        for threads, opened, closed in (([99], 0, [99]), ([None, 99], 1, [99, 17])):
            api = FakeApi()
            api.threads = list(threads)
            with self.subTest(threads=threads), self.assertRaises(IdentityContextError):
                self.query(api)
            self.assertEqual(api.opened, opened)
            self.assertEqual(api.closed, closed)

    def test_thread_errors_never_fall_back(self) -> None:
        for code in (5, 1347, 999):
            for phase in (0, 1):
                api = FakeApi()
                error = native.NativeTokenError(code)
                api.threads = [error] if phase == 0 else [None, error]
                with self.subTest(code=code, phase=phase):
                    with self.assertRaises(IdentityQueryError) as caught:
                        self.query(api)
                    self.assertIs(caught.exception.__cause__, error)
                self.assertEqual(api.opened, phase)
                self.assertEqual(api.closed, [] if phase == 0 else [17])

    def test_process_open_and_cleanup_errors(self) -> None:
        for phase in ("process", "close"):
            api = FakeApi()
            error = OSError("private native diagnostic")
            if phase == "process":
                api.process_error = error
            else:
                api.close_error = error
            with (
                self.subTest(phase=phase),
                self.assertRaises(IdentityQueryError) as caught,
            ):
                self.query(api)
            self.assertIs(caught.exception.__cause__, error)
            self.assertNotIn("private", str(caught.exception))
            self.assertEqual(api.closed, [] if phase == "process" else [17])

    def test_sizing_bounds_before_allocation(self) -> None:
        minimum = ctypes.sizeof(native.TokenUser) + 8
        for required in (0, minimum - 1, 65537, 2**32 - 1):
            api = FakeApi()
            api.required = required
            with self.subTest(size=required), self.assertRaises(IdentityQueryError):
                self.query(api)
            self.assertEqual(api.calls, [0])
            self.assertEqual(api.closed, [17])

    def test_one_growth_retry_and_ceiling(self) -> None:
        api = FakeApi()
        api.query_errors = [native.NativeTokenError(122, 65536)]
        self.assertEqual(self.query(api), WindowsPrincipal(SID))
        self.assertEqual(api.calls, [0, api.required, 65536])
        for errors in (
            [native.NativeTokenError(5)],
            [native.NativeTokenError(122, api.required)],
            [native.NativeTokenError(122, 65537)],
            [native.NativeTokenError(122, 100), native.NativeTokenError(122, 200)],
        ):
            api = FakeApi()
            api.query_errors = errors
            with (
                self.subTest(errors=len(errors)),
                self.assertRaises(IdentityQueryError),
            ):
                self.query(api)
            self.assertLessEqual(len(api.calls), 3)
            self.assertEqual(api.closed, [17])

    def test_sizing_failure_and_unexpected_success(self) -> None:
        for succeeds in (True, False):
            api = FakeApi()
            api.sizing_success = succeeds
            api.sizing_error = native.NativeTokenError(5)
            with self.subTest(success=succeeds), self.assertRaises(IdentityQueryError):
                self.query(api)
            self.assertEqual(api.calls, [0])
            self.assertEqual(api.closed, [17])

    def test_allocation_failure_closes_process_token(self) -> None:
        api = FakeApi()
        error = MemoryError("allocation failed")
        with (
            patch("ctypes.create_string_buffer", side_effect=error),
            self.assertRaises(IdentityQueryError) as caught,
        ):
            self.query(api)
        self.assertIs(caught.exception.__cause__, error)
        self.assertEqual(api.closed, [17])

    def test_returned_length_and_pointer_bounds_before_validation(self) -> None:
        for returned in (0, ctypes.sizeof(native.TokenUser) - 1, 65537):
            api = FakeApi()
            api.returned = returned
            with self.subTest(length=returned), self.assertRaises(IdentityQueryError):
                self.query(api)
            self.assertEqual(api.validated, [])
            self.assertEqual(api.closed, [17])
        for offset in (
            None,
            -1,
            0,
            ctypes.sizeof(native.TokenUser) - 1,
            25,
            32,
            100000,
        ):
            api = FakeApi()
            api.pointer_offset = offset
            with self.subTest(offset=offset), self.assertRaises(IdentityQueryError):
                self.query(api)
            self.assertEqual(api.validated, [])
            self.assertEqual(api.closed, [17])

    def test_sid_shape_and_native_validation(self) -> None:
        for data in (
            bytes((2, 2)) + SID[2:],
            bytes((1, 16)) + SID[2:],
            bytes((1, 15)) + SID[2:],
        ):
            api = FakeApi()
            api.data = data
            with self.subTest(header=data[:2]), self.assertRaises(IdentityQueryError):
                self.query(api)
            self.assertEqual(api.validated, [])
            self.assertEqual(api.closed, [17])
        for native_length in (0, len(SID) - 1, len(SID) + 1):
            api = FakeApi()
            api.native_length = native_length
            with (
                self.subTest(length=native_length),
                self.assertRaises(IdentityQueryError),
            ):
                self.query(api)
            self.assertEqual(api.closed, [17])
        api = FakeApi()
        api.validation_error = ValueError("native validation refusal")
        with self.assertRaises(IdentityQueryError):
            self.query(api)
        self.assertEqual(api.closed, [17])

    def test_unqualified_host_refuses_before_dll_load(self) -> None:
        for target in ("linux", "darwin", "unknown"):
            with (
                self.subTest(platform=target),
                patch("sys.platform", target),
                patch.object(native, "NativeTokenApi") as loader,
                self.assertRaises(UnsupportedPlatformError),
            ):
                native.current_principal()
            loader.assert_not_called()

    def test_candidate_architecture_and_version_refuse_before_loading(self) -> None:
        for width, machine, build in (
            (4, "AMD64", 17763),
            (8, "ARM64", 17763),
            (8, "AMD64", 17762),
        ):
            with (
                self.subTest(width=width, machine=machine, build=build),
                patch("sys.platform", "win32"),
                patch("os.name", "nt"),
                patch("struct.calcsize", return_value=width),
                patch("platform.machine", return_value=machine),
                patch.object(
                    sys,
                    "getwindowsversion",
                    return_value=SimpleNamespace(build=build),
                    create=True,
                ),
                patch.object(native, "NativeTokenApi") as loader,
                self.assertRaises(UnsupportedPlatformError),
            ):
                native.current_principal()
            loader.assert_not_called()

    def test_public_selector_stays_closed_on_windows(self) -> None:
        with (
            patch("sys.platform", "win32"),
            patch.object(native, "current_principal") as query,
            self.assertRaises(UnsupportedPlatformError),
        ):
            current_principal()
        query.assert_not_called()


def byref_output(argument: object, name: str = "_obj") -> object:
    return getattr(argument, name)


class FakeFunction:
    def __init__(self, result: int = 1) -> None:
        self.argtypes: list[object] = []
        self.restype: object = None
        self.result = result
        self.calls: list[tuple[object, ...]] = []
        self.effect: Callable[..., int] | None = None

    def __call__(self, *arguments: object) -> int:
        self.calls.append(arguments)
        return self.result if self.effect is None else self.effect(*arguments)


class FakeDll:
    def __init__(self) -> None:
        self.functions: dict[str, FakeFunction] = {}

    def __getattr__(self, name: str) -> FakeFunction:
        return self.functions.setdefault(name, FakeFunction())


class NativeTokenBindingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.kernel = FakeDll()
        self.security = FakeDll()
        self.error = 1008
        loader_patch = patch.object(
            ctypes, "WinDLL", side_effect=[self.kernel, self.security], create=True
        )
        self.loader = loader_patch.start()
        self.addCleanup(loader_patch.stop)
        error_patch = patch.object(
            ctypes, "get_last_error", side_effect=lambda: self.error, create=True
        )
        error_patch.start()
        self.addCleanup(error_patch.stop)
        self.api = native.NativeTokenApi()

    def test_system_loading_and_native_abi(self) -> None:
        self.assertEqual(self.loader.call_count, 2)
        for call in self.loader.call_args_list:
            self.assertEqual(call.kwargs, {"use_last_error": True, "winmode": 0x0800})
        for name in ("GetCurrentThread", "GetCurrentProcess"):
            self.assertIs(self.kernel.functions[name].restype, ctypes.c_void_p)
        self.assertEqual(
            self.security.functions["OpenThreadToken"].argtypes,
            [
                ctypes.c_void_p,
                ctypes.c_uint32,
                ctypes.c_int32,
                ctypes.POINTER(ctypes.c_void_p),
            ],
        )
        self.assertIs(self.security.functions["GetLengthSid"].restype, ctypes.c_uint32)
        self.assertIs(self.kernel.functions["CloseHandle"].restype, ctypes.c_int32)

    def test_only_no_token_is_absence(self) -> None:
        function = self.security.functions["OpenThreadToken"]
        function.result = 0
        self.assertIsNone(self.api.thread_token())
        self.assertEqual(function.calls[-1][1:3], (8, 1))
        for code in (0, 5, 1347, 122):
            self.error = code
            with (
                self.subTest(code=code),
                self.assertRaises(native.NativeTokenError) as caught,
            ):
                self.api.thread_token()
            self.assertEqual(caught.exception.winerror, code)
        self.assertEqual(self.security.functions["OpenProcessToken"].calls, [])

    def test_full_width_handles_and_query_only_rights(self) -> None:
        token = 2 ** (8 * ctypes.sizeof(ctypes.c_void_p)) - 123

        def open_token(*args: object) -> int:
            output = byref_output(args[-1])
            assert isinstance(output, ctypes.c_void_p)
            output.value = token
            return 1

        self.security.functions["OpenThreadToken"].effect = open_token
        self.security.functions["OpenProcessToken"].effect = open_token
        self.assertEqual(self.api.thread_token(), token)
        self.assertEqual(self.api.process_token(), token)
        self.assertEqual(self.security.functions["OpenProcessToken"].calls[-1][1], 8)
        self.api.close(token)
        self.assertEqual(self.kernel.functions["CloseHandle"].calls[-1], (token,))

    def test_missing_handles_and_api_errors_refuse(self) -> None:
        for operation, name in (
            (self.api.thread_token, "OpenThreadToken"),
            (self.api.process_token, "OpenProcessToken"),
        ):
            with self.subTest(name=name), self.assertRaises(ValueError):
                operation()
            self.security.functions[name].result = 0
            self.error = 5
            with self.assertRaises(native.NativeTokenError):
                operation()
        self.kernel.functions["CloseHandle"].result = 0
        with self.assertRaises(native.NativeTokenError):
            self.api.close(123)

    def test_token_information_class_lengths_and_errors(self) -> None:
        function = self.security.functions["GetTokenInformation"]

        def query(*args: object) -> int:
            output = byref_output(args[-1])
            assert isinstance(output, ctypes.c_uint32)
            output.value = 42
            return function.result

        function.effect = query
        function.result = 0
        self.error = 122
        with self.assertRaises(native.NativeTokenError) as caught:
            self.api.token_user(123, None)
        self.assertEqual(caught.exception.required_size, 42)
        self.assertEqual(function.calls[-1][:4], (123, 1, None, 0))
        function.result = 1
        buffer = ctypes.create_string_buffer(100)
        self.assertEqual(self.api.token_user(123, buffer), 42)
        self.assertEqual(function.calls[-1][3], 100)

    def test_invalid_sid_never_calls_length_or_last_error(self) -> None:
        self.security.functions["IsValidSid"].result = 0
        with self.assertRaises(ValueError):
            self.api.sid_length(SID)
        self.assertEqual(self.security.functions["GetLengthSid"].calls, [])
        self.security.functions["IsValidSid"].result = 1
        self.security.functions["GetLengthSid"].result = len(SID)
        self.assertEqual(self.api.sid_length(SID), len(SID))


@unittest.skipUnless(sys.platform == "win32", "actual Windows principal qualification")
class NativeWindowsPrincipalTests(unittest.TestCase):
    def test_process_sid_matches_independent_dotnet_query(self) -> None:
        script = """
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
try {
    $sid = $identity.User
    $bytes = New-Object byte[] $sid.BinaryLength
    $sid.GetBinaryForm($bytes, 0)
    [Convert]::ToBase64String($bytes)
} finally { $identity.Dispose() }
"""
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            check=True,
            capture_output=True,
            text=True,
            timeout=20,
        )
        expected = WindowsPrincipal(
            base64.b64decode(result.stdout.strip(), validate=True)
        )
        with patch.dict(
            os.environ, {"USERNAME": "spoofed", "USER": "spoofed", "UID": "0"}
        ):
            self.assertTrue(
                native.current_principal() == expected, "native SID oracle mismatch"
            )
            self.assertTrue(
                native.current_principal() == expected, "fresh SID oracle mismatch"
            )

    def test_real_impersonation_refuses_in_disposable_process(self) -> None:
        code = """
import ctypes
from mos_eisley.platform.windows_identity import current_principal
from mos_eisley.platform.identity import IdentityContextError
api = ctypes.WinDLL('advapi32.dll', use_last_error=True, winmode=0x0800)
api.ImpersonateSelf.argtypes = [ctypes.c_int32]
api.ImpersonateSelf.restype = ctypes.c_int32
api.RevertToSelf.argtypes = []
api.RevertToSelf.restype = ctypes.c_int32
assert api.ImpersonateSelf(2), 'native impersonation fixture unavailable'
try:
    try:
        current_principal()
    except IdentityContextError:
        pass
    else:
        raise AssertionError('impersonation admitted')
finally:
    assert api.RevertToSelf(), 'native fixture cleanup failed'
current_principal()
"""
        subprocess.run([sys.executable, "-c", code], check=True, timeout=20)

    def test_repeated_queries_release_native_handles(self) -> None:
        code = """
import ctypes
from mos_eisley.platform.windows_identity import current_principal
kernel = ctypes.WinDLL('kernel32.dll', use_last_error=True, winmode=0x0800)
kernel.GetCurrentProcess.argtypes = []
kernel.GetCurrentProcess.restype = ctypes.c_void_p
kernel.GetProcessHandleCount.argtypes = [
    ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)
]
kernel.GetProcessHandleCount.restype = ctypes.c_int32
def count():
    value = ctypes.c_uint32()
    assert kernel.GetProcessHandleCount(kernel.GetCurrentProcess(), ctypes.byref(value))
    return value.value
current_principal()
before = count()
for _ in range(64):
    current_principal()
assert count() == before, 'native token handles leaked'
"""
        subprocess.run([sys.executable, "-c", code], check=True, timeout=20)

    def test_native_validation_matches_portable_sid_boundaries(self) -> None:
        api = native.NativeTokenApi()
        for count in (0, 1, 15):
            sid = bytes((1, count, 0, 0, 0, 0, 0, 5)) + bytes(4 * count)
            value = WindowsPrincipal(sid)
            self.assertEqual(api.sid_length(value.sid), len(sid))
        for revision, count in ((0, 1), (2, 1), (1, 16)):
            data = bytes((revision, count)) + bytes(6 + 4 * count)
            with self.subTest(revision=revision, count=count):
                with self.assertRaises(ValueError):
                    WindowsPrincipal(data)
                with self.assertRaises(ValueError):
                    api.sid_length(data)


if __name__ == "__main__":
    unittest.main()
