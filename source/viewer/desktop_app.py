#!/usr/bin/env python3
"""Standalone desktop shell for the NBA 2K16 MyTEAM archive."""

from __future__ import annotations

from http.server import ThreadingHTTPServer
import sys
import threading
from urllib.request import urlopen
from urllib.parse import urlencode

import webview

from server import ViewerHandler


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
            "NBA 2K16 MyTEAM Archive",
            start_url,
            width=1440,
            height=900,
            min_size=(980, 650),
            hidden=ui_smoke_test,
            background_color="#070b11",
        )

        def finish_smoke_test() -> None:
            window.events.loaded.wait(20)
            window.destroy()

        webview.start(finish_smoke_test if ui_smoke_test else None, debug=False, private_mode=False)
    finally:
        server.shutdown()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
