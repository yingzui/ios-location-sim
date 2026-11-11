#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
iOS 定位模拟器 —— 电脑侧控制端

原理：借用苹果留给 Xcode 的开发者调试通道（DVT LocationSimulation），把模拟坐标
      注入 iOS 的定位子系统，全系统生效（你自己的 App、地图、天气都会跟着变）。
      iOS 17.4 及以上走免管理员权限的 userspace 隧道（CoreDeviceProxy），
      Windows 上不需要额外驱动、不需要管理员。

关键设计：保持一条常驻的 DVT 连接。命令行版 `simulate-location set` 靠阻塞来维持
      通道，进程一退定位就还原；这里改成在进程内长连接上反复调用 set()，
      切换坐标无空档。

用法：
    python server.py            # 默认 http://127.0.0.1:8765
    python server.py --port 9000
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import subprocess
import sys
import threading
import traceback
from collections import deque
from contextlib import AsyncExitStack
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765

ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

# 把常见异常翻译成能直接照做的中文提示
HINTS = {
    "ConnectionFailedToUsbmuxdError":
        "连不上 usbmuxd（苹果移动设备服务）。请安装官网版 iTunes "
        "https://www.apple.com/itunes/download/win64 ，不要用 Microsoft Store 版，"
        "然后用数据线连接 iPhone。",
    "NoDeviceConnectedError":
        "没有发现 iPhone。确认数据线支持传输（不是充电线）、手机已解锁并点了「信任此电脑」。",
    "UserspaceTunnelUnavailableError":
        "此系统版本无法建立免权限隧道（需要 iOS 17.4+）。请以管理员身份另开一个窗口运行 "
        "`python -m pymobiledevice3 remote tunneld` 并保持不关，然后重试。",
    "DeveloperModeIsNotEnabledError":
        "iPhone 未开启开发者模式。设置 → 隐私与安全性 → 开发者模式 → 打开（会重启）。"
        "若没有该选项，先执行 `python -m pymobiledevice3 amfi reveal-developer-mode`。",
    "DeveloperModeError":
        "开发者模式相关错误。确认开发者模式已开启并已重启设备。",
    "InvalidServiceError":
        "找不到开发者服务（DVT）。通常是开发者磁盘镜像没挂上：先点「挂载镜像」，"
        "并确认开发者模式已开启。",
    "DeveloperDiskImageNotFoundError":
        "没有可用的开发者磁盘镜像，请点「挂载镜像」（需要联网从 Apple 服务器下载）。",
    "DeviceHasPasscodeSetError":
        "设备设置了锁屏密码，某些操作会被拒绝。临时关闭密码后重试。",
    "NotPairedError":
        "设备未与本机配对。拔插数据线，在 iPhone 上点「信任此电脑」并输入锁屏密码。",
}


def explain(exc: BaseException) -> str:
    """把异常翻译成可读、可操作的中文提示。"""
    name = type(exc).__name__
    msg = str(exc).strip()
    hint = HINTS.get(name)
    if hint:
        return f"{hint}（{name}{': ' + msg if msg else ''}）"
    return msg or name



def cli(*args: str, timeout: int = 180) -> tuple[int, str]:
    """调用 pymobiledevice3 命令行（同一个解释器，避免环境错乱）。"""
    cmd = [sys.executable, "-m", "pymobiledevice3", *args]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return 124, f"命令超时（{timeout}s）：{' '.join(cmd)}"
    except FileNotFoundError:
        return 127, "找不到 Python 解释器"
    out = (p.stdout or "") + (p.stderr or "")
    return p.returncode, ANSI_RE.sub("", out).strip()


class Session:
    """持有与 iPhone 的长连接，并把它暴露给 HTTP 层（线程安全）。"""

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever,
                                        name="pmd-loop", daemon=True)
        self._thread.start()
        self._lock = threading.RLock()
        self._stack: AsyncExitStack | None = None
        self._ls = None
        self._udid: str | None = None
        self._current: dict | None = None
        self._error: str | None = None
        self._busy: str | None = None
        self._log: deque[str] = deque(maxlen=300)

    # ---------- 基础工具 ----------

    def log(self, msg: object) -> None:
        text = str(msg).rstrip()
        if not text:
            return
        self._log.append(text)
        try:
            print(text, flush=True)
        except Exception:
            pass

    def logs(self, since: int = 0) -> dict:
        items = list(self._log)
        return {"total": len(items), "lines": items[since:]}

    def status(self) -> dict:
        with self._lock:
            return {
                "connected": self._ls is not None,
                "udid": self._udid,
                "simulating": self._current is not None,
                "current": self._current,
                "busy": self._busy,
                "error": self._error,
            }

    def _run(self, coro, timeout: float = 300):
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout=timeout)

    def _spawn(self, coro, label: str, timeout: float = 300) -> None:
        """把长耗时操作丢到后台跑，HTTP 立即返回，前端轮询日志。"""
        def worker() -> None:
            try:
                self._run(coro, timeout)
            except Exception as exc:  # noqa: BLE001
                detail = explain(exc)
                with self._lock:
                    self._error = detail
                self.log(f"[错误] {detail}")
                if type(exc).__name__ not in HINTS:      # 已知问题不刷堆栈，避免淹没提示
                    for line in traceback.format_exc().splitlines()[-4:]:
                        self.log(f"    {line}")
            finally:
                with self._lock:
                    self._busy = None

        with self._lock:
            if self._busy:
                raise RuntimeError(f"已有任务在执行：{self._busy}")
            self._busy = label
            self._error = None
        threading.Thread(target=worker, daemon=True, name=label).start()

    # ---------- 设备会话 ----------

    async def _connect(self, udid: str | None) -> None:
        # 延迟导入，这样没装依赖时前端也能拿到可读的错误信息
        from pymobiledevice3.remote.userspace_tunnel import UserspaceRsdTunnel
        from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider
        from pymobiledevice3.services.dvt.instruments.location_simulation import LocationSimulation

        await self._disconnect()

        self.log("① 建立 userspace 隧道（免管理员权限）…")
        stack = AsyncExitStack()
        try:
            rsd = await stack.enter_async_context(UserspaceRsdTunnel(serial=udid))
            dev = getattr(rsd, "udid", udid) or "unknown"
            self.log(f"   隧道就绪：{dev}")

            self.log("② 连接 DVT 开发者服务…")
            dvt = await stack.enter_async_context(DvtProvider(rsd))

            self.log("③ 打开 LocationSimulation 通道…")
            ls = await stack.enter_async_context(LocationSimulation(dvt))
        except BaseException:
            await stack.aclose()
            raise

        with self._lock:
            self._stack, self._ls, self._udid = stack, ls, dev
        self.log("✓ 已连接。现在可以在地图上点选坐标下发。")

    async def _disconnect(self) -> None:
        with self._lock:
            stack = self._stack
            self._stack = None
            self._ls = None
            self._current = None
        if stack is not None:
            try:
                await stack.aclose()
                self.log("已断开与设备的连接。")
            except Exception as exc:  # noqa: BLE001
                self.log(f"关闭连接时出错（通常无害）：{exc!r}")

    async def _set_location(self, lat: float, lon: float) -> None:
        with self._lock:
            ls = self._ls
        if ls is None:
            raise RuntimeError("尚未连接设备，请先点「连接设备」")
        await ls.set(lat, lon)
        with self._lock:
            self._current = {"lat": round(lat, 6), "lon": round(lon, 6)}
        self.log(f"→ 已下发定位 WGS-84 ({lat:.6f}, {lon:.6f})")

    async def _clear_location(self) -> None:
        with self._lock:
            ls = self._ls
        if ls is None:
            raise RuntimeError("尚未连接设备")
        await ls.clear()
        with self._lock:
            self._current = None
        self.log("→ 已停止模拟，恢复真实 GPS。")

    # ---------- 对外接口 ----------

    def connect(self, udid: str | None = None) -> None:
        self._spawn(self._connect(udid), "connect")

    def disconnect(self) -> None:
        self._spawn(self._disconnect(), "disconnect", timeout=60)

    def set_location(self, lat: float, lon: float) -> None:
        self._run(self._set_location(lat, lon), timeout=60)

    def clear_location(self) -> None:
        self._run(self._clear_location(), timeout=60)

    def scan(self) -> str:
        rc, out = cli("usbmux", "list", timeout=60)
        return out or f"（无输出，返回码 {rc}）"

    def prepare(self) -> str:
        """挂载开发者磁盘镜像。iOS 17+ 上部分开发者服务需要它。"""
        self._spawn(self._prepare_async(), "prepare")

    async def _prepare_async(self) -> None:
        self.log("正在挂载开发者磁盘镜像（首次会从 Apple 服务器下载，可能较慢）…")
        rc, out = await asyncio.to_thread(cli, "mounter", "auto-mount", timeout=600)
        for line in (out or "").splitlines():
            self.log(f"   {line}")
        self.log("✓ 镜像挂载流程结束。" if rc == 0 else f"✗ 挂载返回码 {rc}（若后续连接正常可忽略）")


# ---------------------------------------------------------------- HTTP 层

class Handler(BaseHTTPRequestHandler):
    server_version = "iOSLocationSim/1.0"
    session: Session

    def log_message(self, *args) -> None:  # 静音默认访问日志
        pass

    # ---------- 响应工具 ----------

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, obj: object, code: int = 200) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:
            return {}

    def _guard(self, fn) -> None:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            detail = explain(exc)
            self.session.log(f"[错误] {detail}")
            self._json({"ok": False, "error": detail}, 500)

    # ---------- 路由 ----------

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._send(204, b"", "text/plain")

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            html = (ROOT / "index.html").read_bytes()
            self._send(200, html, "text/html; charset=utf-8")
            return
        if path == "/api/status":
            self._json(self.session.status())
            return
        if path == "/api/log":
            try:
                since = int(self.path.split("since=", 1)[1])
            except Exception:
                since = 0
            self._json(self.session.logs(since))
            return
        self._json({"ok": False, "error": "not found"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        body = self._body()
        s = self.session

        if path == "/api/scan":
            return self._guard(lambda: self._json({"ok": True, "output": s.scan()}))

        if path == "/api/prepare":
            return self._guard(lambda: (s.prepare(), self._json({"ok": True}))[1])

        if path == "/api/connect":
            return self._guard(
                lambda: (s.connect(body.get("udid") or None), self._json({"ok": True}))[1]
            )

        if path == "/api/disconnect":
            return self._guard(lambda: (s.disconnect(), self._json({"ok": True}))[1])

        if path == "/api/location":
            def run() -> None:
                lat, lon = float(body["lat"]), float(body["lon"])
                if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    raise ValueError("坐标超出合法范围")
                s.set_location(lat, lon)
                self._json({"ok": True, "current": s.status()["current"]})
            return self._guard(run)

        if path == "/api/clear":
            return self._guard(lambda: (s.clear_location(), self._json({"ok": True}))[1])

        self._json({"ok": False, "error": "not found"}, 404)


def main() -> int:
    ap = argparse.ArgumentParser(description="iOS 定位模拟器 —— 电脑侧控制端")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:
        pass

    session = Session()
    Handler.session = session

    rc, ver = cli("version", timeout=60)
    session.log(f"pymobiledevice3: {ver.splitlines()[0] if ver else '未检测到'}"
                if rc == 0 else "⚠ 未检测到 pymobiledevice3，请先执行：python -m pip install -U pymobiledevice3")

    # 启动自检：usbmuxd（苹果移动设备服务）就绪情况 —— 这是最常见的翻车点
    if rc == 0:
        rc_u, _ = cli("usbmux", "list", timeout=45)
        if rc_u != 0:
            session.log("⚠ 未检测到 Apple 移动设备服务（usbmuxd），现在连接设备一定会失败。")
            session.log("   请先安装官网版 iTunes：https://www.apple.com/itunes/download/win64")
            session.log("   注意：不要用 Microsoft Store 的「Apple 设备」，它会导致设备发现失效。")
            session.log("   装好后重新运行本程序，再用数据线连接 iPhone。")
        else:
            session.log("✓ Apple 移动设备服务已就绪。下一步：检测设备 → 挂载镜像 → 连接设备。")

    try:
        httpd = ThreadingHTTPServer((DEFAULT_HOST, args.port), Handler)
    except OSError as exc:
        print()
        print(f"[×] 无法在 {DEFAULT_HOST}:{args.port} 启动：{exc}")
        print(f"    端口被占用了，通常是有另一个控制端还在后台运行。")
        print(f"    处理办法一：结束占用进程  netstat -ano | findstr :{args.port}")
        print(f"    处理办法二：换个端口  python server.py --port 8766")
        return 1

    print("=" * 62)
    print("  iOS 定位模拟器已启动")
    print(f"  界面地址：http://127.0.0.1:{args.port}/")
    print("  前置条件：iPhone 已开启「开发者模式」并用数据线连接本机")
    print("  按 Ctrl+C 退出")
    print("=" * 62)
    sys.stdout.flush()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n正在退出…")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
