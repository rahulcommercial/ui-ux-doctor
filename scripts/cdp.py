"""
Minimal Chrome DevTools Protocol (CDP) client -- pure Python standard library.

No pip, no npm, no third-party WebSocket library. This hand-rolls just enough of
RFC 6455 (WebSocket) and CDP to:
  * launch (or attach to) an already-installed Chrome / Edge / Chromium,
  * navigate to a URL and wait for load,
  * evaluate JS in the page and read the result,
  * collect console messages, exceptions and failed network responses.

That lets ui-ux-doctor scan the *rendered* DOM of a running localhost app without
installing anything -- it drives the browser the machine already has.
"""

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from base64 import b64encode

# --------------------------------------------------------------------------- #
# Browser discovery / launch
# --------------------------------------------------------------------------- #

_MAC = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
]
_WIN = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]
_LINUX = [
    "/usr/bin/google-chrome", "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium", "/usr/bin/chromium-browser",
    "/usr/bin/microsoft-edge", "/usr/bin/brave-browser",
]


def find_browser():
    """Return a path to an installed Chromium-family browser, or None."""
    env = os.environ.get("UXD_BROWSER")
    if env and os.path.exists(env):
        return env
    cands = {"darwin": _MAC, "win32": _WIN}.get(sys.platform, _LINUX)
    for path in cands:
        if os.path.exists(path):
            return path
    return None


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class Browser:
    """Launches a headless browser with remote debugging, or attaches to one."""

    def __init__(self, browser_path=None, headless=True, port=None):
        self.proc = None
        self.profile = None
        if port:  # attach to an already-running browser
            self.port = port
            return
        self.port = _free_port()
        path = browser_path or find_browser()
        if not path:
            raise RuntimeError(
                "No Chrome/Edge/Chromium found. Install one (Edge ships with "
                "Windows), set UXD_BROWSER=/path/to/browser, or use --attach PORT "
                "after launching it yourself with --remote-debugging-port.")
        self.profile = tempfile.mkdtemp(prefix="uxd-cdp-")
        args = [
            path,
            "--remote-debugging-port=%d" % self.port,
            "--user-data-dir=" + self.profile,
            "--no-first-run", "--no-default-browser-check",
            "--disable-gpu", "--disable-dev-shm-usage", "--no-sandbox",
            "about:blank",
        ]
        is_shell = "headless-shell" in os.path.basename(path).lower()
        if headless and not is_shell:
            args.insert(1, "--headless=new")
        self.proc = subprocess.Popen(args, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
        self._wait_ready()

    def _wait_ready(self, timeout=15):
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                self.version()
                return
            except Exception:
                time.sleep(0.2)
        raise RuntimeError("Browser did not expose the CDP endpoint in time.")

    def _get(self, path):
        url = "http://127.0.0.1:%d%s" % (self.port, path)
        with urllib.request.urlopen(url, timeout=5) as r:
            return json.load(r)

    def version(self):
        return self._get("/json/version")

    def new_page(self, url="about:blank"):
        """Open a fresh tab and return its CDP WebSocket URL."""
        try:
            t = self._get("/json/new?" + url)
        except Exception:
            # Some builds reject /json/new; fall back to an existing page target.
            targets = [t for t in self._get("/json") if t.get("type") == "page"]
            if not targets:
                raise
            t = targets[0]
        return t["webSocketDebuggerUrl"]

    def close(self):
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except Exception:
                self.proc.kill()
        if self.profile:
            import shutil
            shutil.rmtree(self.profile, ignore_errors=True)


# --------------------------------------------------------------------------- #
# WebSocket (RFC 6455) client -- just the client side, text frames
# --------------------------------------------------------------------------- #

class _WS:
    def __init__(self, url, timeout=25):
        assert url.startswith("ws://"), "only ws:// (localhost) supported"
        host_port, _, path = url[len("ws://"):].partition("/")
        host, _, port = host_port.partition(":")
        self.timeout = timeout
        self.sock = socket.create_connection((host, int(port or 80)), timeout)
        self.sock.settimeout(timeout)
        key = b64encode(os.urandom(16)).decode()
        req = (
            "GET /%s HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\n"
            "Connection: Upgrade\r\nSec-WebSocket-Key: %s\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n" % (path, host_port, key)
        )
        self.sock.sendall(req.encode())
        resp = self._read_until(b"\r\n\r\n")
        if b" 101 " not in resp.split(b"\r\n", 1)[0]:
            raise ConnectionError("WebSocket upgrade failed: %r" % resp[:120])

    def _read_until(self, marker):
        buf = b""
        while marker not in buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("socket closed during handshake")
            buf += chunk
        return buf

    def _recv_exact(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("socket closed")
            buf += chunk
        return buf

    def send(self, text):
        payload = text.encode("utf-8")
        n = len(payload)
        header = bytearray([0x81])  # FIN + text opcode
        if n < 126:
            header.append(0x80 | n)
        elif n < 65536:
            header.append(0x80 | 126)
            header += n.to_bytes(2, "big")
        else:
            header.append(0x80 | 127)
            header += n.to_bytes(8, "big")
        mask = os.urandom(4)
        header += mask
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(bytes(header) + masked)

    def _recv_frame(self):
        b0 = self._recv_exact(1)[0]
        fin, opcode = b0 & 0x80, b0 & 0x0F
        b1 = self._recv_exact(1)[0]
        masked, length = b1 & 0x80, b1 & 0x7F
        if length == 126:
            length = int.from_bytes(self._recv_exact(2), "big")
        elif length == 127:
            length = int.from_bytes(self._recv_exact(8), "big")
        mask = self._recv_exact(4) if masked else b""
        data = self._recv_exact(length) if length else b""
        if masked:
            data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        return fin, opcode, data

    def recv(self):
        """Return one full text message (reassembling fragments, answering pings)."""
        chunks = []
        while True:
            fin, opcode, data = self._recv_frame()
            if opcode == 0x9:            # ping -> pong
                self._pong(data)
                continue
            if opcode == 0xA:            # pong
                continue
            if opcode == 0x8:            # close
                raise ConnectionError("WebSocket closed by browser")
            chunks.append(data)
            if fin:
                break
        return b"".join(chunks).decode("utf-8", "replace")

    def _pong(self, data):
        header = bytearray([0x8A, 0x80 | len(data)])
        mask = os.urandom(4)
        header += mask
        self.sock.sendall(bytes(header) +
                          bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def settimeout(self, t):
        self.sock.settimeout(t)

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass


# --------------------------------------------------------------------------- #
# CDP session
# --------------------------------------------------------------------------- #

class CDP:
    def __init__(self, ws_url, timeout=25):
        self.ws = _WS(ws_url, timeout)
        self.timeout = timeout
        self._id = 0
        self.events = []   # accumulated CDP events (console, network, ...)

    def send(self, method, params=None):
        self._id += 1
        mid = self._id
        self.ws.send(json.dumps({"id": mid, "method": method,
                                 "params": params or {}}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError("CDP %s: %s" % (method, msg["error"]))
                return msg.get("result", {})
            if "method" in msg:
                self.events.append(msg)

    def wait_event(self, method, timeout=15):
        deadline = time.time() + timeout
        self.ws.settimeout(0.5)
        try:
            while time.time() < deadline:
                try:
                    msg = json.loads(self.ws.recv())
                except socket.timeout:
                    continue
                if "method" in msg:
                    self.events.append(msg)
                    if msg["method"] == method:
                        return msg
        finally:
            self.ws.settimeout(self.timeout)
        return None

    def drain(self, seconds):
        """Passively collect events for a settle window (SPA hydration / XHR)."""
        deadline = time.time() + seconds
        self.ws.settimeout(0.3)
        try:
            while time.time() < deadline:
                try:
                    msg = json.loads(self.ws.recv())
                except socket.timeout:
                    continue
                if "method" in msg:
                    self.events.append(msg)
        finally:
            self.ws.settimeout(self.timeout)

    # -- high level ------------------------------------------------------- #
    def enable(self):
        for domain in ("Page", "Runtime", "Log", "Network"):
            self.send(domain + ".enable")

    def navigate(self, url, load_timeout=20):
        res = self.send("Page.navigate", {"url": url})
        if res.get("errorText"):
            raise RuntimeError("navigate failed: %s" % res["errorText"])
        self.wait_event("Page.loadEventFired", load_timeout)

    def eval(self, expression, await_promise=False):
        res = self.send("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True,
            "awaitPromise": await_promise,
        })
        if "exceptionDetails" in res:
            raise RuntimeError("eval error: %s" %
                               res["exceptionDetails"].get("text", "unknown"))
        return res.get("result", {}).get("value")

    def close(self):
        self.ws.close()
