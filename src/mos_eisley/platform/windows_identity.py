"""Candidate native principal adapter; public selector admission is separate.

Imports are inert. Only direct qualification queries load Windows system DLLs.
No file identity, storage policy, privilege change or impersonation change exists.
"""

import ctypes
import os
import platform
import struct
import sys
from collections.abc import Callable
from threading import Lock
from typing import Protocol, cast

from mos_eisley.platform.identity import (
    IdentityContextError,
    IdentityQueryError,
    UnsupportedPlatformError,
    WindowsPrincipal,
)

_TOKEN_QUERY = 0x0008
_TOKEN_USER = 1
_NO_TOKEN = 1008
_INSUFFICIENT_BUFFER = 122
_MAX_BUFFER = 64 * 1024
_DWORD = ctypes.c_uint32
TokenBuffer = ctypes.Array[ctypes.c_char]


class TokenUser(ctypes.Structure):
    _fields_ = [("sid", ctypes.c_void_p), ("attributes", _DWORD)]


class NativeTokenError(OSError):
    def __init__(self, code: int, required_size: int = 0) -> None:
        super().__init__("native token operation failed")
        self.winerror = code
        self.required_size = required_size


class TokenApi(Protocol):
    def thread_token(self) -> int | None: ...
    def process_token(self) -> int: ...
    def token_user(self, token: int, buffer: TokenBuffer | None) -> int: ...
    def sid_length(self, sid: bytes) -> int: ...
    def close(self, token: int) -> None: ...


class _NativeFunction(Protocol):
    argtypes: list[object]
    restype: object

    def __call__(self, *args: object) -> int: ...


class _WindowsVersion(Protocol):
    build: int


def _symbol(library: object, name: str) -> object:
    """Narrow the dynamic ctypes/Windows-only boundary before native calls."""
    return getattr(library, name)


def _last_error() -> int:
    return cast(Callable[[], int], _symbol(ctypes, "get_last_error"))()


class NativeTokenApi:
    def __init__(self) -> None:
        # Resolve only trusted system DLLs, with pointer-sized HANDLE results.
        loader = cast(Callable[..., object], _symbol(ctypes, "WinDLL"))
        kernel = loader("kernel32.dll", use_last_error=True, winmode=0x0800)
        security = loader("advapi32.dll", use_last_error=True, winmode=0x0800)
        self._thread = cast(_NativeFunction, _symbol(kernel, "GetCurrentThread"))
        self._process = cast(_NativeFunction, _symbol(kernel, "GetCurrentProcess"))
        self._open_thread = cast(_NativeFunction, _symbol(security, "OpenThreadToken"))
        self._open_process = cast(
            _NativeFunction, _symbol(security, "OpenProcessToken")
        )
        self._information = cast(
            _NativeFunction, _symbol(security, "GetTokenInformation")
        )
        self._valid_sid = cast(_NativeFunction, _symbol(security, "IsValidSid"))
        self._length_sid = cast(_NativeFunction, _symbol(security, "GetLengthSid"))
        self._close = cast(_NativeFunction, _symbol(kernel, "CloseHandle"))
        for function in (self._thread, self._process):
            function.argtypes = []
            function.restype = ctypes.c_void_p
        self._open_thread.argtypes = [
            ctypes.c_void_p,
            _DWORD,
            ctypes.c_int32,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        self._open_process.argtypes = [
            ctypes.c_void_p,
            _DWORD,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        self._information.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int32,
            ctypes.c_void_p,
            _DWORD,
            ctypes.POINTER(_DWORD),
        ]
        for function in (self._valid_sid, self._length_sid):
            function.argtypes = [ctypes.c_void_p]
        self._close.argtypes = [ctypes.c_void_p]
        for function in (
            self._open_thread,
            self._open_process,
            self._information,
            self._valid_sid,
            self._close,
        ):
            function.restype = ctypes.c_int32
        self._length_sid.restype = _DWORD

    def thread_token(self) -> int | None:
        token = ctypes.c_void_p()
        if self._open_thread(self._thread(), _TOKEN_QUERY, 1, ctypes.byref(token)):
            if token.value is None:
                raise ValueError("native token handle is missing")
            return token.value
        code = _last_error()
        if code == _NO_TOKEN:
            return None
        raise NativeTokenError(code)

    def process_token(self) -> int:
        token = ctypes.c_void_p()
        if not self._open_process(self._process(), _TOKEN_QUERY, ctypes.byref(token)):
            raise NativeTokenError(_last_error())
        if token.value is None:
            raise ValueError("native token handle is missing")
        return token.value

    def token_user(self, token: int, buffer: TokenBuffer | None) -> int:
        returned = _DWORD()
        capacity = 0 if buffer is None else ctypes.sizeof(buffer)
        if not self._information(
            token, _TOKEN_USER, buffer, capacity, ctypes.byref(returned)
        ):
            # Retain only the scalar sizing result, never native bytes/pointers.
            raise NativeTokenError(_last_error(), returned.value)
        return returned.value

    def sid_length(self, sid: bytes) -> int:
        owned = ctypes.create_string_buffer(sid, len(sid))
        if not self._valid_sid(owned):
            raise ValueError("native SID validation failed")
        return self._length_sid(owned)

    def close(self, token: int) -> None:
        if not self._close(token):
            raise NativeTokenError(_last_error())


_bindings: NativeTokenApi | None = None
_binding_lock = Lock()


def _token_api() -> NativeTokenApi:
    # Keep two system DLL bindings for the process lifetime; never cache tokens,
    # contexts, buffers or identifiers. Serialize first binding across threads.
    global _bindings
    with _binding_lock:
        if _bindings is None:
            _bindings = NativeTokenApi()
        return _bindings


def _require_candidate_host() -> None:
    if (
        sys.platform != "win32"
        or os.name != "nt"
        or struct.calcsize("P") != 8
        or platform.machine().upper() != "AMD64"
    ):
        raise UnsupportedPlatformError("native principal target is unsupported")
    version = cast(Callable[[], _WindowsVersion], _symbol(sys, "getwindowsversion"))()
    if version.build < 17763:
        raise UnsupportedPlatformError("native principal target is unsupported")


def _check_thread(api: TokenApi) -> None:
    token = api.thread_token()
    if token is not None:
        try:
            raise IdentityContextError("current principal context is unsupported")
        finally:
            api.close(token)


def _bounded_size(size: int) -> int:
    if not ctypes.sizeof(TokenUser) + 8 <= size <= _MAX_BUFFER:
        raise ValueError("native token buffer size is invalid")
    return size


def _read_user(api: TokenApi, token: int) -> WindowsPrincipal:
    try:
        api.token_user(token, None)
    except NativeTokenError as error:
        if error.winerror != _INSUFFICIENT_BUFFER:
            raise
        size = _bounded_size(error.required_size)
    else:
        raise ValueError("native token sizing returned an invalid success")
    for attempt in range(2):
        buffer = ctypes.create_string_buffer(size)
        try:
            returned = api.token_user(token, buffer)
        except NativeTokenError as error:
            if error.winerror != _INSUFFICIENT_BUFFER or attempt == 1:
                raise
            required = _bounded_size(error.required_size)
            if required <= size:
                raise ValueError("native token buffer did not grow") from error
            size = required
            continue
        if not ctypes.sizeof(TokenUser) <= returned <= size:
            raise ValueError("native token returned length is invalid")
        pointer = TokenUser.from_buffer(buffer).sid
        base = ctypes.addressof(buffer)
        start = base + ctypes.sizeof(TokenUser)
        end = base + returned
        if pointer is None or not start <= pointer <= end - 8:
            raise ValueError("native SID header is outside owned storage")
        offset = pointer - base
        header = buffer.raw[offset : offset + 8]
        length = 8 + 4 * header[1]
        if header[0] != 1 or header[1] > 15 or pointer + length > end:
            raise ValueError("native SID body is outside owned storage")
        sid = bytes(buffer.raw[offset : offset + length])
        principal = WindowsPrincipal(sid)
        if api.sid_length(sid) != length:
            raise ValueError("native SID length disagrees with bounded bytes")
        return principal
    raise AssertionError("bounded token query exhausted")


def _query_principal(api: TokenApi) -> WindowsPrincipal:
    _check_thread(api)
    token = api.process_token()
    try:
        principal = _read_user(api, token)
        _check_thread(api)
        return principal
    finally:
        api.close(token)


def current_principal() -> WindowsPrincipal:
    """Fresh process TokenUser, refusing impersonation before and after query.

    Direct candidate adapter entry point for native qualification. Does not admit
    the public Windows selector or establish subsequent context stability.
    """
    _require_candidate_host()
    try:
        return _query_principal(_token_api())
    except IdentityContextError:
        raise
    except (OSError, ValueError, MemoryError) as error:
        raise IdentityQueryError("current principal query failed") from error
