"""
E听说进程探测模块
枚举系统中疑似 E听说 的进程并读取其窗口标题（只读，无侵入）。
仅用于平时练习/复习场景，正式考试中请勿使用本程序。
"""
import ctypes
from ctypes import wintypes

_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def find_ets_processes():
    """枚举系统中疑似 E听说 的进程，返回 [(pid, exe_path)]"""
    kernel32 = ctypes.windll.kernel32
    psapi = ctypes.windll.psapi
    arr = (wintypes.DWORD * 2048)()
    cb = wintypes.DWORD()
    if not psapi.EnumProcesses(ctypes.byref(arr), ctypes.sizeof(arr), ctypes.byref(cb)):
        return []
    count = cb.value // ctypes.sizeof(wintypes.DWORD)
    result = []
    for i in range(count):
        pid = arr[i]
        if not pid:
            continue
        handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            continue
        try:
            buf = ctypes.create_unicode_buffer(260)
            size = wintypes.DWORD(260)
            if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                exe_path = buf.value
                base = exe_path.rsplit("\\", 1)[-1].lower()
                if "ets" in base or "listen" in base or "xst" in base:
                    result.append((pid, exe_path))
        finally:
            kernel32.CloseHandle(handle)
    return result


def get_window_titles(pid):
    """枚举指定进程的可见窗口标题"""
    user32 = ctypes.windll.user32
    titles = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, _):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(hwnd):
            buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, buf, 256)
            if buf.value:
                titles.append(buf.value)
        return True

    user32.EnumWindows(callback, 0)
    return titles
