"""Return freed memory to the operating system."""

import ctypes
import gc
import sys
from ctypes import wintypes

from PyQt6.QtCore import QTimer


_RELEASE_DELAY_MS = 500  # lets deleteLater() of the released widgets run first


def release_unused_memory():
    """Collect garbage and hand freed memory back: trim the working set on Windows, the malloc heap on Linux."""
    gc.collect()
    if sys.platform == "win32":
        kernel32 = ctypes.windll.kernel32
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.SetProcessWorkingSetSize.argtypes = [wintypes.HANDLE, ctypes.c_size_t, ctypes.c_size_t]
        trim_all = ctypes.c_size_t(-1).value  # (SIZE_T)-1 asks Windows to trim the working set
        kernel32.SetProcessWorkingSetSize(kernel32.GetCurrentProcess(), trim_all, trim_all)
    elif sys.platform.startswith("linux"):
        try:
            ctypes.CDLL("libc.so.6").malloc_trim(0)
        except (OSError, AttributeError):
            pass  # not glibc


def release_memory_soon() -> None:
    """Release unused memory once the pending deleteLater() calls have run."""
    QTimer.singleShot(_RELEASE_DELAY_MS, release_unused_memory)
