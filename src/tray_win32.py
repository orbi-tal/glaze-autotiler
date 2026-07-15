"""Win32-native system tray icon implementation (replaces pystray/Pillow)."""

import ctypes
import logging
import queue
import threading
from ctypes import wintypes
from typing import Callable

user32 = ctypes.windll.user32
shell32 = ctypes.windll.shell32
kernel32 = ctypes.windll.kernel32

LRESULT = wintypes.LPARAM

# WINFUNCTYPE only exists on Windows Python builds. On other platforms this
# module still needs to be importable e.g. for pytest collection via
# conftest.py's mocks on Linux/macOS/CI even though the code inside it
# never actually runs there. CFUNCTYPE is a reasonable stand-in; the actual
# calling convention only matters on real Windows.
if hasattr(ctypes, "WINFUNCTYPE"):
    WINFUNCTYPE = ctypes.WINFUNCTYPE
else:
    WINFUNCTYPE = ctypes.CFUNCTYPE

user32.DefWindowProcW.argtypes = [wintypes.HWND, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = LRESULT

user32.CreateWindowExW.argtypes = [
    wintypes.DWORD,
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    wintypes.DWORD,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.HWND,
    wintypes.HMENU,
    wintypes.HINSTANCE,
    wintypes.LPVOID,
]
user32.CreateWindowExW.restype = wintypes.HWND

user32.LoadImageW.argtypes = [
    wintypes.HINSTANCE,
    wintypes.LPCWSTR,
    wintypes.UINT,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.UINT,
]
user32.LoadImageW.restype = wintypes.HANDLE

kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE

WM_DESTROY = 0x0002
WM_COMMAND = 0x0111
WM_USER = 0x0400
WM_APP = 0x8000
WM_TRAYICON = WM_APP + 1
WM_LBUTTONUP = 0x0202
WM_RBUTTONUP = 0x0205
WM_CONTEXTMENU = 0x007B

NIM_ADD = 0x00000000
NIM_MODIFY = 0x00000001
NIM_DELETE = 0x00000002

NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004

IMAGE_ICON = 1
LR_LOADFROMFILE = 0x00000010
LR_DEFAULTSIZE = 0x00000040

MF_STRING = 0x00000000
MF_SEPARATOR = 0x00000800
MF_CHECKED = 0x00000008
MF_UNCHECKED = 0x00000000
MF_GRAYED = 0x00000001
MF_ENABLED = 0x00000000

TPM_RIGHTBUTTON = 0x0002
TPM_RETURNCMD = 0x0100

WS_OVERLAPPED = 0x00000000
CW_USEDEFAULT = 0x80000000 - (1 << 32)

WNDPROC = WINFUNCTYPE(LRESULT, wintypes.HWND, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM)


class NOTIFYICONDATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
    ]


class WNDCLASS(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


class MenuItem:
    def __init__(
        self,
        label: str | None = None,
        callback: Callable[[], object] | None = None,
        checked: bool | Callable[[], bool] = False,
        enabled: bool | Callable[[], bool] = True,
    ):
        self.label = label
        self.callback = callback
        self.checked = checked
        self.enabled = enabled

    def is_checked(self) -> bool:
        return self.checked() if callable(self.checked) else self.checked

    def is_enabled(self) -> bool:
        return self.enabled() if callable(self.enabled) else self.enabled


class TrayIcon:
    _CLASS_NAME = "GlazeAutotilerTrayWndClass"
    _TRAY_UID = 1

    def __init__(self, title, icon_path, menu_factory):
        self.title = title
        self.icon_path = icon_path
        self.menu_factory = menu_factory
        self._hwnd = None
        self._hicon = None
        self._hinstance = kernel32.GetModuleHandleW(None)
        self._wndproc_ref = WNDPROC(self._wndproc)
        self._tooltip = title
        self._running = False
        self._ready_event = threading.Event()
        self._work_queue = queue.Queue()

    def run(self):
        self._create_window()
        self._load_icon()
        self._add_tray_icon()
        self._running = True
        self._ready_event.set()

        msg = wintypes.MSG()
        while self._running:
            has_msg = user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1)
            if has_msg:
                if msg.message == WM_DESTROY:
                    break
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            self._drain_work_queue()
            if not has_msg:
                user32.MsgWaitForMultipleObjects(0, None, False, 50, 0x04FF)

        self._remove_tray_icon()
        if self._hwnd:
            user32.DestroyWindow(self._hwnd)

    def set_tooltip(self, text):
        self._work_queue.put(("tooltip", text))
        self._wake()

    def refresh_menu(self):
        pass

    def stop(self):
        self._work_queue.put(("stop", None))
        self._wake()

    def wait_until_ready(self, timeout=5.0):
        return self._ready_event.wait(timeout)

    def _wake(self):
        if self._hwnd:
            user32.PostMessageW(self._hwnd, 0x0000, 0, 0)

    def _drain_work_queue(self):
        while True:
            try:
                kind, payload = self._work_queue.get_nowait()
            except queue.Empty:
                return
            if kind == "tooltip":
                self._tooltip = payload
                self._update_tray_icon_tip()
            elif kind == "stop":
                self._running = False

    def _create_window(self):
        wndclass = WNDCLASS()
        wndclass.style = 0
        wndclass.lpfnWndProc = self._wndproc_ref
        wndclass.cbClsExtra = 0
        wndclass.cbWndExtra = 0
        wndclass.hInstance = self._hinstance
        wndclass.hIcon = None
        wndclass.hCursor = None
        wndclass.hbrBackground = None
        wndclass.lpszMenuName = None
        wndclass.lpszClassName = self._CLASS_NAME

        if not user32.RegisterClassW(ctypes.byref(wndclass)):
            err = kernel32.GetLastError()
            if err != 1410:
                logging.warning("RegisterClassW failed with error %s", err)

        self._hwnd = user32.CreateWindowExW(
            0,
            self._CLASS_NAME,
            self.title,
            WS_OVERLAPPED,
            CW_USEDEFAULT,
            CW_USEDEFAULT,
            CW_USEDEFAULT,
            CW_USEDEFAULT,
            None,
            None,
            self._hinstance,
            None,
        )
        if not self._hwnd:
            raise OSError("Failed to create tray message window (CreateWindowExW)")

    def _load_icon(self):
        self._hicon = user32.LoadImageW(
            None, self.icon_path, IMAGE_ICON, 0, 0, LR_LOADFROMFILE | LR_DEFAULTSIZE
        )
        if not self._hicon:
            raise OSError(f"Failed to load icon from {self.icon_path}")

    def _make_nid(self):
        nid = NOTIFYICONDATA()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATA)
        nid.hWnd = self._hwnd
        nid.uID = self._TRAY_UID
        nid.uFlags = NIF_ICON | NIF_MESSAGE | NIF_TIP
        nid.uCallbackMessage = WM_TRAYICON
        nid.hIcon = self._hicon
        nid.szTip = self._tooltip[:127]
        return nid

    def _add_tray_icon(self):
        shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(self._make_nid()))

    def _update_tray_icon_tip(self):
        shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(self._make_nid()))

    def _remove_tray_icon(self):
        nid = NOTIFYICONDATA()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATA)
        nid.hWnd = self._hwnd
        nid.uID = self._TRAY_UID
        shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))

    def _show_menu(self):
        items = self.menu_factory()
        hmenu = user32.CreatePopupMenu()
        callbacks = {}
        cmd_id = 1
        for entry in items:
            if entry.label is None:
                user32.AppendMenuW(hmenu, MF_SEPARATOR, 0, None)
                continue
            flags = MF_STRING
            flags |= MF_CHECKED if entry.is_checked() else MF_UNCHECKED
            flags |= MF_GRAYED if not entry.is_enabled() else MF_ENABLED
            user32.AppendMenuW(hmenu, flags, cmd_id, entry.label)
            callbacks[cmd_id] = entry.callback
            cmd_id += 1

        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        user32.SetForegroundWindow(self._hwnd)
        chosen = user32.TrackPopupMenu(
            hmenu, TPM_RIGHTBUTTON | TPM_RETURNCMD, pt.x, pt.y, 0, self._hwnd, None
        )
        user32.PostMessageW(self._hwnd, 0x0000, 0, 0)
        user32.DestroyMenu(hmenu)

        if chosen and chosen in callbacks and callbacks[chosen] is not None:
            try:
                callbacks[chosen]()
            except Exception:
                logging.exception("Error running tray menu callback")

    def _wndproc(self, hwnd, msg, wparam, lparam):
        if msg == WM_TRAYICON:
            if lparam in (WM_LBUTTONUP,):
                pass
            elif lparam in (WM_RBUTTONUP, WM_CONTEXTMENU):
                self._show_menu()
            return 0
        if msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)
