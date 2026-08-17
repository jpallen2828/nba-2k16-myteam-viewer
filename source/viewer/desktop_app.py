#!/usr/bin/env python3
"""Standalone desktop shell for the NBA 2K16 MyTEAM archive."""

from __future__ import annotations

from http.server import ThreadingHTTPServer
import os
import sys
import threading
from urllib.request import urlopen
from urllib.parse import urlencode

import webview

from server import ViewerHandler


WINDOW_TITLE = "NBA 2K16 MyTEAM Archive"
WINDOW_APP_ID = "NBA2K16.MyTEAMViewer"


def configure_windows_app_identity() -> None:
    """Give Windows a stable identity before the desktop window is created."""
    if sys.platform != "win32":
        return
    import ctypes

    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(WINDOW_APP_ID)


def apply_windows_taskbar_icon() -> bool:
    """Assign the executable's embedded icon to pywebview's native window."""
    if sys.platform != "win32":
        return False
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    shell32 = ctypes.windll.shell32
    large_icon = wintypes.HICON()
    small_icon = wintypes.HICON()
    if shell32.ExtractIconExW(sys.executable, 0, ctypes.byref(large_icon), ctypes.byref(small_icon), 1) == 0:
        return False

    applied = False
    current_pid = os.getpid()
    wm_seticon = 0x0080
    icon_small = 0
    icon_big = 1
    gclp_hicon = -14
    gclp_hiconsm = -34
    set_class_icon = user32.SetClassLongPtrW if ctypes.sizeof(ctypes.c_void_p) == 8 else user32.SetClassLongW
    set_class_icon.argtypes = (wintypes.HWND, ctypes.c_int, ctypes.c_void_p)
    set_class_icon.restype = ctypes.c_void_p
    user32.SendMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
    user32.SendMessageW.restype = wintypes.LPARAM

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def assign_icon(hwnd: int, _lparam: int) -> bool:
        nonlocal applied
        process_id = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        if process_id.value != current_pid or not user32.IsWindowVisible(hwnd):
            return True
        title_length = user32.GetWindowTextLengthW(hwnd)
        title = ctypes.create_unicode_buffer(title_length + 1)
        user32.GetWindowTextW(hwnd, title, len(title))
        if title.value != WINDOW_TITLE:
            return True
        big = large_icon.value or small_icon.value
        small = small_icon.value or large_icon.value
        user32.SendMessageW(hwnd, wm_seticon, icon_big, wintypes.LPARAM(big))
        user32.SendMessageW(hwnd, wm_seticon, icon_small, wintypes.LPARAM(small))
        set_class_icon(hwnd, gclp_hicon, ctypes.c_void_p(big))
        set_class_icon(hwnd, gclp_hiconsm, ctypes.c_void_p(small))
        applied = True
        return True

    user32.EnumWindows(assign_icon, 0)
    return applied


def start_server() -> tuple[ThreadingHTTPServer, str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), ViewerHandler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, name="myteam-viewer", daemon=True).start()
    return server, f"http://127.0.0.1:{port}"


def smoke_test() -> int:
    server, address = start_server()
    try:
        with urlopen(f"{address}/health", timeout=5) as response:
            return 0 if response.status == 200 and response.read() == b'{"ok":true}' else 1
    finally:
        server.shutdown()
        server.server_close()


def main() -> int:
    if "--smoke-test" in sys.argv:
        return smoke_test()

    ui_smoke_test = "--ui-smoke-test" in sys.argv
    configure_windows_app_identity()
    server, address = start_server()
    try:
        mode = ""
        for arg in sys.argv:
            if arg.startswith("--mode="):
                mode = arg.split("=", 1)[1].strip().lower()
        start_url = address
        if mode in {"draft", "random", "custom", "inject"}:
            start_url = f"{address}?{urlencode({'mode': mode})}"

        window = webview.create_window(
            WINDOW_TITLE,
            start_url,
            width=1440,
            height=900,
            min_size=(980, 650),
            hidden=ui_smoke_test,
            background_color="#070b11",
        )

        def initialize_window() -> None:
            window.events.loaded.wait(20)
            apply_windows_taskbar_icon()
            if ui_smoke_test:
                window.destroy()

        webview.start(initialize_window, debug=False, private_mode=False)
    finally:
        server.shutdown()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
