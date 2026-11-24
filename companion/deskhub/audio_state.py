"""Windows speaker and microphone mute, read (and set) through Core Audio.

Standard library only: plain ctypes calls into the COM interfaces
IMMDeviceEnumerator -> IMMDevice -> IAudioEndpointVolume, so no extra package
is needed. Every call runs on the caller's thread, which must have COM
initialised (see `com_thread`).
"""
import ctypes
import sys
import uuid
from ctypes import wintypes

E_RENDER, E_CAPTURE = 0, 1   # EDataFlow: speakers, microphone
E_CONSOLE = 0                # ERole
CLSCTX_ALL = 0x17

CLSID_MMDeviceEnumerator = "{BCDE0395-E52F-467C-8E3D-C4579291692E}"
IID_IMMDeviceEnumerator = "{A95664D2-9614-4F35-A746-DE8DB63617E6}"
IID_IAudioEndpointVolume = "{5CDF2C82-841E-4546-9722-0CF74078229A}"

# vtable slots (IUnknown takes 0-2)
_ENUM_GET_DEFAULT = 4      # IMMDeviceEnumerator::GetDefaultAudioEndpoint
_DEVICE_ACTIVATE = 3       # IMMDevice::Activate
_VOL_SET_MUTE = 14         # IAudioEndpointVolume::SetMute
_VOL_GET_MUTE = 15         # IAudioEndpointVolume::GetMute
_RELEASE = 2


class GUID(ctypes.Structure):
    _fields_ = [("data", ctypes.c_byte * 16)]

    def __init__(self, text: str):
        super().__init__()
        ctypes.memmove(self.data, uuid.UUID(text).bytes_le, 16)


def _method(obj: ctypes.c_void_p, slot: int, *argtypes):
    vtable = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    return ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, *argtypes)(vtable[slot])


def _release(obj: ctypes.c_void_p):
    if obj:
        ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(
            ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents[_RELEASE])(obj)


def _endpoint_volume(flow: int) -> ctypes.c_void_p:
    ole32 = ctypes.windll.ole32
    enum, dev, vol = ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_void_p()
    ole32.CoCreateInstance(ctypes.byref(GUID(CLSID_MMDeviceEnumerator)), None, CLSCTX_ALL,
                           ctypes.byref(GUID(IID_IMMDeviceEnumerator)), ctypes.byref(enum))
    try:
        _method(enum, _ENUM_GET_DEFAULT, ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p))(
            enum, flow, E_CONSOLE, ctypes.byref(dev))
        try:
            _method(dev, _DEVICE_ACTIVATE, ctypes.POINTER(GUID), wintypes.DWORD, ctypes.c_void_p,
                    ctypes.POINTER(ctypes.c_void_p))(
                dev, ctypes.byref(GUID(IID_IAudioEndpointVolume)), CLSCTX_ALL, None, ctypes.byref(vol))
        finally:
            _release(dev)
    finally:
        _release(enum)
    return vol


def is_muted(flow: int) -> bool | None:
    """Mute state of the default speaker (E_RENDER) or microphone (E_CAPTURE).
    None when there is no such device."""
    if sys.platform != "win32":
        return None
    try:
        vol = _endpoint_volume(flow)
    except OSError:
        return None  # e.g. no microphone plugged in
    try:
        muted = wintypes.BOOL()
        _method(vol, _VOL_GET_MUTE, ctypes.POINTER(wintypes.BOOL))(vol, ctypes.byref(muted))
        return bool(muted.value)
    finally:
        _release(vol)


def set_muted(flow: int, muted: bool) -> bool:
    if sys.platform != "win32":
        return False
    try:
        vol = _endpoint_volume(flow)
    except OSError:
        return False
    try:
        _method(vol, _VOL_SET_MUTE, wintypes.BOOL, ctypes.c_void_p)(vol, bool(muted), None)
        return True
    finally:
        _release(vol)


def toggle_mic() -> bool | None:
    """Flip the default microphone's mute; returns the new state."""
    now = is_muted(E_CAPTURE)
    if now is None:
        return None
    set_muted(E_CAPTURE, not now)
    return not now


# ---------------------------------------------------------------- playback devices (switch the default output)
CLSID_PolicyConfigClient = "{870AF99C-171D-4F9E-AF0D-E63DF40C2BC9}"
IID_IPolicyConfig = "{F8679F50-850A-41CF-9C72-430F290290C8}"
_ENUM_ENUM_ENDPOINTS = 3   # IMMDeviceEnumerator::EnumAudioEndpoints
_COLL_COUNT, _COLL_ITEM = 3, 4
_DEVICE_OPEN_PROPS, _DEVICE_GET_ID = 4, 5
_PROPS_GET_VALUE = 5       # IPropertyStore::GetValue
_POLICY_SET_DEFAULT = 13   # IPolicyConfig::SetDefaultEndpoint
DEVICE_ACTIVE = 1
_FRIENDLY_NAME = ("{A45C254E-DF1C-4EFD-8020-67D146A850E0}", 14)   # PKEY_Device_FriendlyName


class _PropKey(ctypes.Structure):
    _fields_ = [("fmtid", ctypes.c_byte * 16), ("pid", wintypes.DWORD)]


def _enumerator() -> ctypes.c_void_p:
    enum = ctypes.c_void_p()
    ctypes.windll.ole32.CoCreateInstance(ctypes.byref(GUID(CLSID_MMDeviceEnumerator)), None, CLSCTX_ALL,
                                         ctypes.byref(GUID(IID_IMMDeviceEnumerator)), ctypes.byref(enum))
    return enum


def _device_id(dev) -> str:
    p = ctypes.c_wchar_p()
    _method(dev, _DEVICE_GET_ID, ctypes.POINTER(ctypes.c_wchar_p))(dev, ctypes.byref(p))
    value = p.value or ""
    ctypes.windll.ole32.CoTaskMemFree(ctypes.cast(p, ctypes.c_void_p))
    return value


def _device_name(dev) -> str:
    props = ctypes.c_void_p()
    _method(dev, _DEVICE_OPEN_PROPS, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p))(dev, 0, ctypes.byref(props))
    try:
        key = _PropKey()
        ctypes.memmove(key.fmtid, uuid.UUID(_FRIENDLY_NAME[0]).bytes_le, 16)
        key.pid = _FRIENDLY_NAME[1]
        pv = (ctypes.c_byte * 24)()    # PROPVARIANT: vt at 0, the string pointer at 8
        _method(props, _PROPS_GET_VALUE, ctypes.POINTER(_PropKey), ctypes.c_void_p)(props, ctypes.byref(key), pv)
        try:
            if ctypes.c_ushort.from_buffer(pv, 0).value == 31:   # VT_LPWSTR
                return ctypes.c_wchar_p(ctypes.c_void_p.from_buffer(pv, 8).value).value or ""
            return ""
        finally:
            ctypes.windll.ole32.PropVariantClear(pv)
    finally:
        _release(props)


def list_outputs() -> list[tuple[str, str]]:
    """The active playback devices as (id, name), in Windows' order."""
    if sys.platform != "win32":
        return []
    out = []
    enum, coll = _enumerator(), ctypes.c_void_p()
    try:
        _method(enum, _ENUM_ENUM_ENDPOINTS, ctypes.c_int, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p))(
            enum, E_RENDER, DEVICE_ACTIVE, ctypes.byref(coll))
        try:
            n = wintypes.UINT()
            _method(coll, _COLL_COUNT, ctypes.POINTER(wintypes.UINT))(coll, ctypes.byref(n))
            for i in range(n.value):
                dev = ctypes.c_void_p()
                _method(coll, _COLL_ITEM, wintypes.UINT, ctypes.POINTER(ctypes.c_void_p))(coll, i, ctypes.byref(dev))
                try:
                    out.append((_device_id(dev), _device_name(dev)))
                finally:
                    _release(dev)
        finally:
            _release(coll)
    finally:
        _release(enum)
    return out


def default_output_id() -> str:
    enum, dev = _enumerator(), ctypes.c_void_p()
    try:
        _method(enum, _ENUM_GET_DEFAULT, ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p))(
            enum, E_RENDER, E_CONSOLE, ctypes.byref(dev))
        try:
            return _device_id(dev)
        finally:
            _release(dev)
    finally:
        _release(enum)


def set_default_output(device_id: str) -> None:
    """Make this device the default for sound, games and calls (what the Windows sound menu does)."""
    policy = ctypes.c_void_p()
    ctypes.windll.ole32.CoCreateInstance(ctypes.byref(GUID(CLSID_PolicyConfigClient)), None, CLSCTX_ALL,
                                         ctypes.byref(GUID(IID_IPolicyConfig)), ctypes.byref(policy))
    try:
        for role in (0, 1, 2):   # console, multimedia, communications
            _method(policy, _POLICY_SET_DEFAULT, ctypes.c_wchar_p, ctypes.c_int)(policy, device_id, role)
    finally:
        _release(policy)


def pick_output(devices: list[tuple[str, str]], wanted: str) -> tuple[str, str] | None:
    """The device whose name is `wanted` (exact first, then a part of the name), or None."""
    w = wanted.strip().lower()
    if not w:
        return None
    for d in devices:
        if d[1].lower() == w:
            return d
    for d in devices:
        if w in d[1].lower():
            return d
    return None


def toggle_output(target: str) -> str | None:
    """`target` is "Name A | Name B": make the one that is not the default the default.
    Returns the name now in use, or None when one of the two is not plugged in / switched on."""
    if sys.platform != "win32":
        return None
    parts = [p for p in target.split("|") if p.strip()]
    if len(parts) != 2:
        raise ValueError("an output tile needs two device names joined by |")
    devices = list_outputs()
    a, b = pick_output(devices, parts[0]), pick_output(devices, parts[1])
    if a is None or b is None:
        return None
    new = b if default_output_id() == a[0] else a
    set_default_output(new[0])
    return new[1]


def com_thread():
    """Initialiser for the worker thread that makes these calls."""
    if sys.platform == "win32":
        ctypes.windll.ole32.CoInitializeEx(None, 0x2)  # COINIT_APARTMENTTHREADED


def read_states() -> dict[str, bool]:
    out = {}
    for name, flow in (("speaker_mute", E_RENDER), ("mic_mute", E_CAPTURE)):
        m = is_muted(flow)
        if m is not None:
            out[name] = m
    return out
