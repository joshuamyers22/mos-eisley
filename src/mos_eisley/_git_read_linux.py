"""Small Linux launcher that confines one Git process before replacing itself.

It is invoked with Python isolated mode from the installed package. No untrusted
workspace module or environment path participates in loading this launcher.
"""

import ctypes
import errno
import os
import platform
import sys
from pathlib import Path


class _SockFilter(ctypes.Structure):
    _fields_ = [
        ("code", ctypes.c_ushort),
        ("jt", ctypes.c_ubyte),
        ("jf", ctypes.c_ubyte),
        ("k", ctypes.c_uint),
    ]


class _SockFProg(ctypes.Structure):
    _fields_ = [
        ("length", ctypes.c_ushort),
        ("instructions", ctypes.POINTER(_SockFilter)),
    ]


# Linux audit architectures and syscall numbers from the x86_64 and asm-generic
# UAPI headers. Child creation, socket I/O and io_uring are denied. Unknown
# architectures refuse rather than running Git without a filter.
_X86_64_DENIED = {
    "socket": 41,
    "connect": 42,
    "accept": 43,
    "sendto": 44,
    "recvfrom": 45,
    "sendmsg": 46,
    "recvmsg": 47,
    "bind": 49,
    "listen": 50,
    "socketpair": 53,
    "clone": 56,
    "fork": 57,
    "vfork": 58,
    "accept4": 288,
    "recvmmsg": 299,
    "sendmmsg": 307,
    "execveat": 322,
    "io_uring_setup": 425,
    "io_uring_enter": 426,
    "io_uring_register": 427,
    "clone3": 435,
}
_AARCH64_DENIED = {
    "socket": 198,
    "socketpair": 199,
    "bind": 200,
    "listen": 201,
    "accept": 202,
    "connect": 203,
    "sendto": 206,
    "recvfrom": 207,
    "sendmsg": 211,
    "recvmsg": 212,
    "clone": 220,
    "accept4": 242,
    "recvmmsg": 243,
    "sendmmsg": 269,
    "execveat": 281,
    "io_uring_setup": 425,
    "io_uring_enter": 426,
    "io_uring_register": 427,
    "clone3": 435,
}
_ARCH_SYSCALLS: dict[str, tuple[int, frozenset[int]]] = {
    "x86_64": (0xC000003E, frozenset(_X86_64_DENIED.values())),
    "aarch64": (0xC00000B7, frozenset(_AARCH64_DENIED.values())),
}


def _confine() -> None:
    identity = _ARCH_SYSCALLS.get(platform.machine())
    if identity is None or sys.platform != "linux":
        raise OSError(errno.ENOTSUP, "unsupported Linux syscall architecture")
    audit_arch, denied = identity
    # BPF loads seccomp_data.arch, then syscall nr; a mismatched ABI is killed.
    instructions = [
        _SockFilter(0x20, 0, 0, 4),
        _SockFilter(0x15, 1, 0, audit_arch),
        _SockFilter(0x06, 0, 0, 0x80000000),
        _SockFilter(0x20, 0, 0, 0),
    ]
    if audit_arch == 0xC000003E:
        # x32 uses the x86_64 audit arch with a high syscall-number bit.
        instructions.extend(
            [
                _SockFilter(0x35, 0, 1, 0x40000000),
                _SockFilter(0x06, 0, 0, 0x80000000),
            ]
        )
    for number in sorted(denied):
        instructions.extend(
            [
                _SockFilter(0x15, 0, 1, number),
                _SockFilter(0x06, 0, 0, 0x00050000 | errno.EPERM),
            ]
        )
    instructions.append(_SockFilter(0x06, 0, 0, 0x7FFF0000))
    program_bytes = (_SockFilter * len(instructions))(*instructions)
    program = _SockFProg(len(instructions), program_bytes)
    libc = ctypes.CDLL(None, use_errno=True)
    libc.prctl.restype = ctypes.c_int
    if libc.prctl(38, 1, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "no_new_privs failed")
    if (
        libc.prctl(
            22,
            ctypes.c_ulong(2),
            ctypes.cast(ctypes.byref(program), ctypes.c_void_p),
            0,
            0,
        )
        != 0
    ):
        raise OSError(ctypes.get_errno(), "seccomp filter failed")


def main() -> int:
    if len(sys.argv) < 2:
        return 2
    executable = Path(sys.argv[1])
    if not executable.is_absolute():
        return 2
    try:
        _confine()
        os.execv(executable, [str(executable), *sys.argv[2:]])
    except OSError:
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
