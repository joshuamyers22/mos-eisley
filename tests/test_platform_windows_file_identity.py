"""Portable native-boundary faults and real local-NTFS qualification cases."""

import ctypes
import subprocess
import sys
import unittest
from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock, patch

from mos_eisley.platform import windows_file_identity as native
from mos_eisley.platform.identity import (
    IdentityQueryError,
    PosixDescriptor,
    UnsupportedPlatformError,
    WindowsFileIdentity,
    WindowsHandle,
    file_identity,
)


def output[T](value: object, kind: type[T]) -> T:
    attribute = "_obj"
    result = getattr(value, attribute)
    assert isinstance(result, kind)
    return result


def query(api: object, handle: int) -> WindowsFileIdentity:
    with (
        patch.object(native, "_require_candidate_host"),
        patch.object(native, "_file_api", return_value=api),
    ):
        return native.file_identity(WindowsHandle(handle))


IDENTITY = WindowsFileIdentity(0xFEDCBA9876543210, bytes(range(16)))


class WindowsFileFaultTests(unittest.TestCase):
    def test_native_fixture_compiles(self) -> None:
        compile(NATIVE_FIXTURE, "native-file-fixture", "exec")

    def api(self) -> SimpleNamespace:
        return SimpleNamespace(
            disk=MagicMock(return_value=True),
            device=MagicMock(return_value=(7, 0x120)),
            filesystem=MagicMock(return_value="NTFS"),
            standard=MagicMock(),
            identity=MagicMock(return_value=IDENTITY),
        )

    def test_adapter_import_is_inert(self) -> None:
        code = """
import ctypes
from unittest.mock import patch
with patch.object(ctypes, 'WinDLL', create=True,
                  side_effect=AssertionError('eager DLL loading')):
    import mos_eisley.platform.windows_file_identity
"""
        subprocess.run([sys.executable, "-c", code], check=True)

    def test_typed_reference_before_host_or_native_access(self) -> None:
        class Derived(WindowsHandle):
            pass

        with patch.object(native, "_require_candidate_host") as host:
            for value in (1, True, None, PosixDescriptor(1), Derived(1)):
                with self.subTest(value=type(value)), self.assertRaises(ValueError):
                    native.file_identity(value)  # pyright: ignore[reportArgumentType]
            host.assert_not_called()

    def test_candidate_host_and_public_selector_refusal(self) -> None:
        cases = [
            ("linux", "nt", "AMD64", 8, 17763),
            ("win32", "posix", "AMD64", 8, 17763),
            ("win32", "nt", "ARM64", 8, 17763),
            ("win32", "nt", "AMD64", 4, 17763),
            ("win32", "nt", "AMD64", 8, 17762),
        ]
        for target, name, machine, width, build in cases:
            with (
                self.subTest(target=target, machine=machine, build=build),
                patch.object(native.sys, "platform", target),
                patch.object(native.os, "name", name),
                patch.object(native.platform, "machine", return_value=machine),
                patch.object(native.struct, "calcsize", return_value=width),
                patch.object(
                    native.sys,
                    "getwindowsversion",
                    create=True,
                    return_value=SimpleNamespace(build=build),
                ),
                patch.object(native, "_file_api") as factory,
                self.assertRaises(UnsupportedPlatformError),
            ):
                native.file_identity(WindowsHandle(1))
            factory.assert_not_called()
        with (
            patch("mos_eisley.platform.identity.sys.platform", "win32"),
            self.assertRaises(UnsupportedPlatformError),
        ):
            file_identity(WindowsHandle(1))

    def test_eligible_full_width_and_query_order(self) -> None:
        api = self.api()
        calls = MagicMock()
        for name in ("disk", "device", "filesystem", "standard", "identity"):
            calls.attach_mock(getattr(api, name), name)
        handle = 2**63 + 123
        self.assertEqual(query(api, handle), IDENTITY)
        self.assertEqual(
            [call[0] for call in calls.mock_calls],
            ["disk", "device", "filesystem", "standard", "identity"],
        )
        for operation in (
            api.disk,
            api.device,
            api.filesystem,
            api.standard,
            api.identity,
        ):
            operation.assert_called_once_with(handle)

    def test_all_unqualified_device_characteristics_refuse(self) -> None:
        for flag in (
            1,
            4,
            8,
            16,
            64,
            0x200,
            0x300,
            0x1000,
            0x2000,
            0x4000,
            0x8000,
            0x10000,
            0x40000,
            0x80000,
            0x80000000,
        ):
            api = self.api()
            api.device.return_value = (7, 0x120 | flag)
            with self.subTest(flag=flag), self.assertRaises(IdentityQueryError):
                query(api, 1)
            api.filesystem.assert_not_called()
            api.identity.assert_not_called()
        for kind in (0, 2, 3, 0x14, 0x24):
            api = self.api()
            api.device.return_value = (kind, 0)
            with self.subTest(kind=kind), self.assertRaises(IdentityQueryError):
                query(api, 1)

    def test_both_native_disk_device_types_and_known_flags(self) -> None:
        for kind in (7, 8):
            for flags in (0, 2, 0x20, 0x80, 0x100, 0x800, 0x20000, 0x209A2):
                api = self.api()
                api.device.return_value = (kind, flags)
                with self.subTest(kind=kind, flags=flags):
                    self.assertEqual(query(api, 1), IDENTITY)

    def test_binding_failure_is_safe_query_error(self) -> None:
        for error in (OSError("DLL failure"), AttributeError("missing native API")):
            with (
                patch.object(native, "_require_candidate_host"),
                patch.object(native, "_file_api", side_effect=error),
                self.assertRaises(IdentityQueryError) as caught,
            ):
                native.file_identity(WindowsHandle(1))
            self.assertIs(caught.exception.__cause__, error)

    def test_nondisk_and_non_ntfs_refuse_before_identity(self) -> None:
        api = self.api()
        api.disk.return_value = False
        with self.assertRaises(IdentityQueryError):
            query(api, 1)
        api.device.assert_not_called()
        for filesystem in ("ReFS", "FAT32", "ntfs", "", "NTFS\0other"):
            api = self.api()
            api.filesystem.return_value = filesystem
            with (
                self.subTest(filesystem=filesystem),
                self.assertRaises(IdentityQueryError),
            ):
                query(api, 1)
            api.identity.assert_not_called()

    def test_failures_wrap_causes_without_identifier_output(self) -> None:
        for operation in ("disk", "device", "filesystem", "standard", "identity"):
            for error in (
                native.NativeFileError(5),
                ValueError("fault"),
                MemoryError(),
            ):
                api = self.api()
                getattr(api, operation).side_effect = error
                with (
                    self.subTest(operation=operation, error=type(error)),
                    patch.object(native, "_require_candidate_host"),
                    patch.object(native, "_file_api", return_value=api),
                    self.assertRaises(IdentityQueryError) as caught,
                ):
                    native.file_identity(WindowsHandle(123))
                self.assertIs(caught.exception.__cause__, error)
                self.assertEqual(
                    str(caught.exception), "opened-file identity query failed"
                )

    def test_bindings_cached_but_identity_fresh(self) -> None:
        api = self.api()
        other = WindowsFileIdentity(42, b"x" * 16)
        api.identity.side_effect = [IDENTITY, other]
        with (
            patch.object(native, "_bindings", None),
            patch.object(native, "NativeFileApi", return_value=api) as factory,
            patch.object(native, "_require_candidate_host"),
        ):
            self.assertEqual(native.file_identity(WindowsHandle(1)), IDENTITY)
            self.assertEqual(native.file_identity(WindowsHandle(1)), other)
            factory.assert_called_once_with()
            self.assertEqual(api.device.call_count, 2)


class NativeFileBindingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.kernel = SimpleNamespace(
            **{
                name: MagicMock()
                for name in (
                    "GetFileType",
                    "GetVolumeInformationByHandleW",
                    "GetFileInformationByHandleEx",
                )
            }
        )
        self.nt = SimpleNamespace(NtQueryVolumeInformationFile=MagicMock())
        loader = patch.object(
            ctypes, "WinDLL", create=True, side_effect=[self.kernel, self.nt]
        )
        self.loader = loader.start()
        self.addCleanup(loader.stop)
        error = patch.object(ctypes, "get_last_error", create=True, return_value=5)
        error.start()
        self.addCleanup(error.stop)
        pending = patch.object(native, "_pending", None)
        pending.start()
        self.addCleanup(pending.stop)
        self.api = native.NativeFileApi()

    def test_abi_and_system_only_dll_loading(self) -> None:
        self.assertEqual(
            [call.args[0] for call in self.loader.call_args_list],
            ["kernel32.dll", "ntdll.dll"],
        )
        for call in self.loader.call_args_list:
            self.assertEqual(call.kwargs, {"use_last_error": True, "winmode": 0x0800})
        self.assertEqual(ctypes.sizeof(native.DeviceInformation), 8)
        self.assertEqual(ctypes.sizeof(native.IdInformation), 24)
        self.assertEqual(ctypes.sizeof(native.StandardInformation), 24)
        self.assertEqual(
            ctypes.sizeof(native.IoStatus), 2 * ctypes.sizeof(ctypes.c_void_p)
        )
        for function in (
            self.kernel.GetFileType,
            self.kernel.GetVolumeInformationByHandleW,
            self.kernel.GetFileInformationByHandleEx,
            self.nt.NtQueryVolumeInformationFile,
        ):
            self.assertIs(function.argtypes[0], ctypes.c_void_p)
        self.assertIs(self.nt.NtQueryVolumeInformationFile.restype, ctypes.c_int32)
        self.assertIs(self.kernel.GetFileType.restype, ctypes.c_uint32)

    def test_device_class_length_and_full_width_handle(self) -> None:
        def device_query(
            handle: object,
            status: object,
            buffer: object,
            length: object,
            information_class: object,
        ) -> int:
            self.assertEqual((handle, length, information_class), (2**63 + 3, 8, 4))
            output(status, native.IoStatus).information = 8
            output(buffer, native.DeviceInformation).device_type = 7
            output(buffer, native.DeviceInformation).characteristics = 0x120
            return 0

        self.nt.NtQueryVolumeInformationFile.side_effect = device_query
        self.assertEqual(self.api.device(2**63 + 3), (7, 0x120))

    def test_device_failures_and_malformed_completion(self) -> None:
        for result in (-1073741790, 1):
            self.nt.NtQueryVolumeInformationFile.return_value = result
            with self.subTest(result=result), self.assertRaises(native.NativeFileError):
                self.api.device(1)
        for status_value, length in ((0, 0), (0, 7), (0, 9), (5, 8)):

            def device_fault(
                *args: object, status_value: int = status_value, length: int = length
            ) -> int:
                status = output(args[1], native.IoStatus)
                status.status = status_value
                status.information = length
                return 0

            self.nt.NtQueryVolumeInformationFile.side_effect = device_fault
            with (
                self.subTest(status=status_value, length=length),
                self.assertRaises(ValueError),
            ):
                self.api.device(1)

    def test_pending_buffers_retained_and_further_queries_disabled(self) -> None:
        self.nt.NtQueryVolumeInformationFile.return_value = 0x103
        with self.assertRaises(native.NativeFileError):
            self.api.device(1)
        call = self.nt.NtQueryVolumeInformationFile.call_args
        pending = native.__dict__["_pending"]
        self.assertIs(pending[0], call.args[1]._obj)
        self.assertIs(pending[1], call.args[2]._obj)
        with self.assertRaises(ValueError):
            self.api.device(2)
        self.nt.NtQueryVolumeInformationFile.assert_called_once()

    def test_pending_completion_also_retains_outputs(self) -> None:
        def pending_completion(*args: object) -> int:
            status = output(args[1], native.IoStatus)
            status.status = 0x103
            status.information = 8
            return 0

        self.nt.NtQueryVolumeInformationFile.side_effect = pending_completion
        with self.assertRaises(native.NativeFileError):
            self.api.device(1)
        self.assertIsNotNone(native.__dict__["_pending"])
        with self.assertRaises(ValueError):
            self.api.device(2)
        self.nt.NtQueryVolumeInformationFile.assert_called_once()

    def test_unconfirmed_completion_exception_retains_outputs(self) -> None:
        self.nt.NtQueryVolumeInformationFile.side_effect = MemoryError()
        with self.assertRaises(MemoryError):
            self.api.device(1)
        self.assertIsNotNone(native.__dict__["_pending"])
        with self.assertRaises(ValueError):
            self.api.device(2)
        self.nt.NtQueryVolumeInformationFile.assert_called_once()

    def test_bounded_filesystem_output_and_errors(self) -> None:
        def volume(*args: object) -> int:
            self.assertEqual(args[:6], (123, None, 0, None, None, None))
            self.assertEqual(args[7], 261)
            name = cast(ctypes.Array[ctypes.c_wchar], args[6])
            name[:5] = "NTFS\0"
            return 1

        self.kernel.GetVolumeInformationByHandleW.side_effect = volume
        self.assertEqual(self.api.filesystem(123), "NTFS")

        def unterminated(*args: object) -> int:
            name = cast(ctypes.Array[ctypes.c_wchar], args[6])
            name[:] = "x" * 261
            return 1

        self.kernel.GetVolumeInformationByHandleW.side_effect = unterminated
        with self.assertRaises(ValueError):
            self.api.filesystem(1)
        self.kernel.GetVolumeInformationByHandleW.side_effect = None
        self.kernel.GetVolumeInformationByHandleW.return_value = 0
        with self.assertRaises(native.NativeFileError):
            self.api.filesystem(1)

    def test_standard_and_identity_classes_full_bytes(self) -> None:
        def information(
            handle: object, kind: object, buffer: object, length: object
        ) -> int:
            self.assertEqual(handle, 2**63 + 1)
            self.assertEqual(length, 24)
            if kind == 18:
                output(
                    buffer, native.IdInformation
                ).volume_serial = IDENTITY.volume_serial
                output(buffer, native.IdInformation).file_id[:] = IDENTITY.file_id
            else:
                self.assertEqual(kind, 1)
                output(buffer, native.StandardInformation).directory = 1
            return 1

        self.kernel.GetFileInformationByHandleEx.side_effect = information
        self.api.standard(2**63 + 1)
        self.assertEqual(self.api.identity(2**63 + 1), IDENTITY)

        def malformed(
            handle: object, kind: object, buffer: object, length: object
        ) -> int:
            output(buffer, native.StandardInformation).directory = 2
            return 1

        self.kernel.GetFileInformationByHandleEx.side_effect = malformed
        with self.assertRaises(ValueError):
            self.api.standard(1)
        self.kernel.GetFileInformationByHandleEx.side_effect = None
        self.kernel.GetFileInformationByHandleEx.return_value = 0
        for operation in (self.api.standard, self.api.identity):
            with self.assertRaises(native.NativeFileError):
                operation(1)

    def test_file_type_errors_and_pipe_character_refusal(self) -> None:
        for kind in (2, 3, 0x8001):
            self.kernel.GetFileType.return_value = kind
            self.assertFalse(self.api.disk(1))
        self.kernel.GetFileType.return_value = 1
        self.assertTrue(self.api.disk(1))
        self.kernel.GetFileType.return_value = 0
        with self.assertRaises(native.NativeFileError):
            self.api.disk(1)


NATIVE_FIXTURE = r"""
import ctypes
import os
import struct
import unittest
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from mos_eisley.platform import windows_file_identity as native
from mos_eisley.platform.identity import (
    WindowsHandle, WindowsFileIdentity, IdentityQueryError,
)
class Fixture(unittest.TestCase):
    def setUp(self):
        loader = ctypes.WinDLL
        self.kernel = loader("kernel32.dll", use_last_error=True, winmode=0x0800)
        prototypes = {
            "CreateFileW": (
                [
                    ctypes.c_wchar_p,
                    ctypes.c_uint32,
                    ctypes.c_uint32,
                    ctypes.c_void_p,
                    ctypes.c_uint32,
                    ctypes.c_uint32,
                    ctypes.c_void_p,
                ],
                ctypes.c_void_p,
            ),
            "CloseHandle": ([ctypes.c_void_p], ctypes.c_int32),
            "GetCurrentProcess": ([], ctypes.c_void_p),
            "DuplicateHandle": (
                [
                    ctypes.c_void_p,
                    ctypes.c_void_p,
                    ctypes.c_void_p,
                    ctypes.c_void_p,
                    ctypes.c_uint32,
                    ctypes.c_int32,
                    ctypes.c_uint32,
                ],
                ctypes.c_int32,
            ),
            "GetFileInformationByHandleEx": (
                [ctypes.c_void_p, ctypes.c_int32, ctypes.c_void_p, ctypes.c_uint32],
                ctypes.c_int32,
            ),
            "SetFilePointerEx": (
                [ctypes.c_void_p, ctypes.c_int64, ctypes.c_void_p, ctypes.c_uint32],
                ctypes.c_int32,
            ),
            "GetHandleInformation": (
                [ctypes.c_void_p, ctypes.c_void_p],
                ctypes.c_int32,
            ),
            "SetHandleInformation": (
                [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32],
                ctypes.c_int32,
            ),
            "CreatePipe": (
                [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32],
                ctypes.c_int32,
            ),
        }
        for name, (arguments, result) in prototypes.items():
            function = getattr(self.kernel, name)
            function.argtypes = arguments
            function.restype = result
        temporary = TemporaryDirectory(prefix="mos-native-file-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    @contextmanager
    def opened(self, path):
        handle = self.kernel.CreateFileW(
            str(path), 0x80000000, 7, None, 3, 0x02000000, None
        )
        self.assertNotIn(handle, (None, ctypes.c_void_p(-1).value))
        try:
            yield WindowsHandle(handle)
        finally:
            self.assertTrue(self.kernel.CloseHandle(handle))

    def oracle(self, opened):
        # Independent raw-buffer marshalling; never use the adapter's structure
        # or eligibility/binding code to construct the expected native value.
        buffer = ctypes.create_string_buffer(24)
        self.assertTrue(
            self.kernel.GetFileInformationByHandleEx(opened.value, 18, buffer, 24)
        )
        serial, file_id = struct.unpack("<Q16s", buffer.raw)
        return WindowsFileIdentity(serial, file_id)

    def state(self, opened):
        flags = ctypes.c_uint32()
        position = ctypes.c_int64()
        self.assertTrue(
            self.kernel.GetHandleInformation(opened.value, ctypes.byref(flags))
        )
        self.assertTrue(
            self.kernel.SetFilePointerEx(opened.value, 0, ctypes.byref(position), 1)
        )
        return flags.value, position.value

    def test_file_directory_oracle_and_borrowed_state(self):
        path = self.root / "file"
        path.write_bytes(b"abcdef")
        with self.opened(path) as opened:
            self.assertTrue(self.kernel.SetFilePointerEx(opened.value, 3, None, 0))
            self.assertTrue(self.kernel.SetHandleInformation(opened.value, 1, 1))
            before = self.state(opened)
            for _ in range(32):
                self.assertEqual(native.file_identity(opened), self.oracle(opened))
            self.assertEqual(self.state(opened), before)
        with self.opened(self.root) as directory:
            self.assertEqual(native.file_identity(directory), self.oracle(directory))

    def test_duplicate_hardlink_rename_replacement_and_mutation(self):
        path = self.root / "original"
        link = self.root / "link"
        path.write_bytes(b"first")
        with self.opened(path) as original:
            identity = native.file_identity(original)
            duplicate = ctypes.c_void_p()
            process = self.kernel.GetCurrentProcess()
            self.assertTrue(
                self.kernel.DuplicateHandle(
                    process, original.value, process, ctypes.byref(duplicate), 0, 0, 2
                )
            )
            try:
                self.assertEqual(
                    native.file_identity(WindowsHandle(duplicate.value)), identity
                )
            finally:
                self.assertTrue(self.kernel.CloseHandle(duplicate))
            os.link(path, link)
            with self.opened(link) as hardlink:
                self.assertEqual(native.file_identity(hardlink), identity)
            renamed = self.root / "renamed"
            path.rename(renamed)
            with self.opened(renamed) as moved:
                self.assertEqual(native.file_identity(moved), identity)
            renamed.write_bytes(b"changed content")
            self.assertEqual(native.file_identity(original), identity)
            path.write_bytes(b"replacement")
            with self.opened(path) as replacement:
                other = native.file_identity(replacement)
                self.assertEqual(other.volume_serial, identity.volume_serial)
                self.assertNotEqual(other, identity)
            self.assertEqual(native.file_identity(original), identity)

    def test_closed_handle_refusal(self):
        path = self.root / "closed"
        path.touch()
        with self.opened(path) as opened:
            native.file_identity(opened)
        # No intervening native handle allocation; caller prevents reuse.
        with self.assertRaises(IdentityQueryError):
            native.file_identity(opened)

    def test_pipe_refusal_preserves_borrowed_handles(self):
        read = ctypes.c_void_p()
        write = ctypes.c_void_p()
        self.assertTrue(
            self.kernel.CreatePipe(ctypes.byref(read), ctypes.byref(write), None, 0)
        )
        try:
            for handle in (read, write):
                with self.assertRaises(IdentityQueryError):
                    native.file_identity(WindowsHandle(handle.value))
                flags = ctypes.c_uint32()
                self.assertTrue(
                    self.kernel.GetHandleInformation(handle, ctypes.byref(flags))
                )
        finally:
            self.assertTrue(self.kernel.CloseHandle(read))
            self.assertTrue(self.kernel.CloseHandle(write))

"""


@unittest.skipUnless(sys.platform == "win32", "requires actual native Windows")
class NativeWindowsFileIdentityTests(unittest.TestCase):
    def run_case(self, case: str) -> None:
        script = NATIVE_FIXTURE + f"\nunittest.main(defaultTest='Fixture.{case}')"
        subprocess.run([sys.executable, "-c", script], check=True, timeout=60)

    def test_file_directory_oracle_and_borrowed_state(self) -> None:
        self.run_case("test_file_directory_oracle_and_borrowed_state")

    def test_duplicate_hardlink_rename_replacement_and_mutation(self) -> None:
        self.run_case("test_duplicate_hardlink_rename_replacement_and_mutation")

    def test_closed_handle_refusal(self) -> None:
        self.run_case("test_closed_handle_refusal")

    def test_pipe_refusal_preserves_borrowed_handles(self) -> None:
        self.run_case("test_pipe_refusal_preserves_borrowed_handles")


if __name__ == "__main__":
    unittest.main()
