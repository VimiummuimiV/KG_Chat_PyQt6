"""Return freed memory to the operating system."""

import ctypes
import gc
import sys
from ctypes import wintypes


def release_unused_memory():
    """Collect garbage and, on Windows, trim the working set so freed memory shows in the process size."""
    gc.collect()
    if sys.platform != "win32":
        return
    kernel32 = ctypes.windll.kernel32
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.SetProcessWorkingSetSize.argtypes = [wintypes.HANDLE, ctypes.c_size_t, ctypes.c_size_t]
    trim_all = ctypes.c_size_t(-1).value  # (SIZE_T)-1 asks Windows to trim the working set
    kernel32.SetProcessWorkingSetSize(kernel32.GetCurrentProcess(), trim_all, trim_all)
