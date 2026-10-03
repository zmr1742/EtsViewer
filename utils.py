"""
工具函数模块
包含字体缓存、HTML清理、系统相关工具
"""
import re
import html
import wx
import ctypes
from ctypes import wintypes

# 系统屏幕尺寸
GetSystemMetrics = ctypes.windll.user32.GetSystemMetrics
MAX_SIZE = (GetSystemMetrics(0), GetSystemMetrics(1))

# 字体缓存
_font_cache = {}

# Windows MCI 音频接口
_mci = ctypes.windll.winmm
_mci.mciSendStringW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.UINT, wintypes.HWND]
_mci.mciSendStringW.restype = wintypes.DWORD
_mci.mciGetErrorStringW.argtypes = [wintypes.DWORD, wintypes.LPWSTR, wintypes.UINT]
_mci.mciGetErrorStringW.restype = wintypes.BOOL

_AUDIO_ALIAS = "etsviewer_audio"


class GUID(ctypes.Structure):
    """Windows GUID 结构"""
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

    def __init__(self, text: str = None):
        if text:
            parts = [p for p in re.split(r"[-{}]", text) if p]
            self.Data1 = int(parts[0], 16)
            self.Data2 = int(parts[1], 16)
            self.Data3 = int(parts[2], 16)
            raw = bytes.fromhex(parts[3] + parts[4])
            self.Data4 = (ctypes.c_ubyte * 8)(*raw)


class ComObj(ctypes.Structure):
    """通用 COM 对象（仅用其虚表指针）"""
    pass


PCom = ctypes.POINTER(ComObj)
ComObj._fields_ = [("lpVtbl", ctypes.POINTER(ctypes.c_void_p))]

_ole32 = ctypes.windll.ole32
_HR = ctypes.c_long  # HRESULT = 32 位有符号 LONG
_ole32.CoInitializeEx.argtypes = (ctypes.c_void_p, wintypes.DWORD)
_ole32.CoInitializeEx.restype = _HR
_ole32.CoCreateInstance.argtypes = (ctypes.POINTER(GUID), ctypes.c_void_p, wintypes.DWORD,
                                    ctypes.POINTER(GUID), ctypes.POINTER(PCom))
_ole32.CoCreateInstance.restype = _HR

_CLSID_MMDeviceEnumerator = GUID("{BCDE0395-E52F-467C-8E3D-C4579291692E}")
_IID_IMMDeviceEnumerator = GUID("{A95664D2-9614-4F35-A746-DE8DB63617E6}")
_IID_IAudioSessionManager = GUID("{BFA971F1-4D5E-40BB-935E-967039BFBEE4}")

_CLSCTX_ALL = 0x17


def _com_call(obj, index, result_type, arg_types, *args):
    """调用 COM 接口虚表中第 index 个方法"""
    proto = ctypes.CFUNCTYPE(result_type, PCom, *arg_types)
    func = ctypes.cast(obj.contents.lpVtbl[index], proto)
    return func(obj, *args)


def _com_release(obj):
    if obj:
        _com_call(obj, 2, wintypes.ULONG, ())


class VolumeController:
    """基于 Core Audio (IAudioSessionManager) 的进程音量控制"""

    _com_init = False
    _volume_obj = None

    @classmethod
    def _ensure(cls) -> bool:
        """初始化并缓存 ISimpleAudioVolume 接口"""
        if cls._volume_obj:
            return True
        if not cls._com_init:
            _ole32.CoInitializeEx(None, 0)
            cls._com_init = True
        try:
            enumerator = PCom()
            hr = _ole32.CoCreateInstance(ctypes.byref(_CLSID_MMDeviceEnumerator), None,
                                         _CLSCTX_ALL, ctypes.byref(_IID_IMMDeviceEnumerator),
                                         ctypes.byref(enumerator))
            if hr < 0 or not enumerator:
                return False
            device = PCom()
            hr = _com_call(enumerator, 4, _HR, (wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(PCom)),
                           0, 0, ctypes.byref(device))
            if hr < 0 or not device:
                _com_release(enumerator)
                return False
            manager = PCom()
            hr = _com_call(device, 3, _HR, (ctypes.POINTER(GUID), wintypes.DWORD, ctypes.c_void_p,
                                            ctypes.POINTER(PCom)),
                           ctypes.byref(_IID_IAudioSessionManager), _CLSCTX_ALL, None, ctypes.byref(manager))
            if hr < 0 or not manager:
                _com_release(device)
                _com_release(enumerator)
                return False
            volume = PCom()
            hr = _com_call(manager, 4, _HR, (ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(PCom)),
                           None, 0, ctypes.byref(volume))
            if hr < 0 or not volume:
                _com_release(manager)
                _com_release(device)
                _com_release(enumerator)
                return False
            cls._volume_obj = volume
            _com_release(manager)
            _com_release(device)
            _com_release(enumerator)
            return True
        except Exception:
            return False

    @classmethod
    def set_volume(cls, percent: int) -> bool:
        """设置进程主音量（0-100）"""
        if not cls._ensure():
            return False
        hr = _com_call(cls._volume_obj, 3, _HR, (ctypes.c_float, ctypes.c_void_p),
                       ctypes.c_float(percent / 100.0), None)
        return hr >= 0

    @classmethod
    def get_volume(cls):
        """读取进程主音量（0-100），失败返回 None"""
        if not cls._ensure():
            return None
        value = ctypes.c_float()
        hr = _com_call(cls._volume_obj, 4, _HR, (ctypes.POINTER(ctypes.c_float),), ctypes.byref(value))
        if hr < 0:
            return None
        return int(round(value.value * 100))


class AudioPlayer:
    """基于 Windows MCI 的音频播放器（支持 MP3/WAV），音量走 Core Audio"""

    _opened = False
    _volume = 80

    @classmethod
    def play(cls, path: str) -> bool:
        """播放音频文件，返回是否成功"""
        cls.stop()
        if not path:
            return False
        err = _mci.mciSendStringW(f'open "{path}" alias {_AUDIO_ALIAS}', None, 0, None)
        if err:
            return False
        _mci.mciSendStringW(f"set {_AUDIO_ALIAS} time format milliseconds", None, 0, None)
        _mci.mciSendStringW(f"play {_AUDIO_ALIAS}", None, 0, None)
        cls._opened = True
        VolumeController.set_volume(cls._volume)
        return True

    @classmethod
    def play_from(cls, ms: int):
        """从指定毫秒位置开始播放"""
        if cls._opened:
            _mci.mciSendStringW(f"play {_AUDIO_ALIAS} from {int(ms)}", None, 0, None)

    @classmethod
    def stop(cls):
        """停止并释放当前音频"""
        cls._opened = False
        _mci.mciSendStringW(f"close {_AUDIO_ALIAS}", None, 0, None)

    @classmethod
    def is_playing(cls) -> bool:
        """判断当前是否正在播放"""
        if not cls._opened:
            return False
        buf = ctypes.create_unicode_buffer(32)
        err = _mci.mciSendStringW(f"status {_AUDIO_ALIAS} mode", buf, 32, None)
        return err == 0 and buf.value.lower() == "playing"

    @classmethod
    def is_open(cls) -> bool:
        """判断音频设备是否已打开"""
        return cls._opened

    @classmethod
    def get_position(cls) -> int:
        """获取当前播放位置（毫秒）"""
        if not cls._opened:
            return 0
        buf = ctypes.create_unicode_buffer(64)
        err = _mci.mciSendStringW(f"status {_AUDIO_ALIAS} position", buf, 64, None)
        if err:
            return 0
        try:
            return int(buf.value)
        except ValueError:
            return 0

    @classmethod
    def get_length(cls) -> int:
        """获取音频总时长（毫秒）"""
        if not cls._opened:
            return 0
        buf = ctypes.create_unicode_buffer(64)
        err = _mci.mciSendStringW(f"status {_AUDIO_ALIAS} length", buf, 64, None)
        if err:
            return 0
        try:
            return int(buf.value)
        except ValueError:
            return 0

    @classmethod
    def set_volume(cls, percent: int):
        """设置音量（0-100），走 Core Audio 进程音量"""
        cls._volume = max(0, min(100, int(percent)))
        VolumeController.set_volume(cls._volume)


def get_font(size: int) -> wx.Font:
    """获取指定大小的系统字体（带缓存）"""
    if size not in _font_cache:
        system_font: wx.Font = wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT)
        system_font.SetPointSize(size)
        _font_cache[size] = system_font
    return _font_cache[size]


def clean_html_tags(content: str) -> str:
    """清理HTML标签，返回纯文本"""
    if not content:
        return ""
    content = re.sub(r"<!--.*?-->", "", content, flags=re.DOTALL)
    content = re.sub(r"<[^>]*>", "", content)
    content = html.unescape(content)
    content = re.sub(r"\n\s*\n", "\n", content).strip()
    return content
