"""
AI 小说家 — 桌面应用入口
=========================
双击启动 → 自动弹窗。支持多开（各自独立端口）。

用法:
    python desktop_app.py              # 桌面窗口模式
    python desktop_app.py --browser    # 浏览器模式
"""
import sys, os, threading, socket, time, urllib.request, urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uvicorn
from src.web.main import app


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def run_server(port: int):
    uvicorn.run(app, host='127.0.0.1', port=port, log_level='error')


def wait_for_server(port: int, timeout: float = 15.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = urllib.request.urlopen(f'http://127.0.0.1:{port}/api/config', timeout=1)
            if r.status == 200:
                return True
        except Exception:
            pass
        time.sleep(0.2)
    return False


def main():
    use_browser = '--browser' in sys.argv

    port = find_free_port()
    print(f"AI 小说家 v3.0  端口:{port}")

    # 后台启动
    threading.Thread(target=run_server, args=(port,), daemon=True).start()

    # 等待完全就绪
    print("  等待服务就绪...", end="", flush=True)
    if not wait_for_server(port):
        print(" 失败")
        sys.exit(1)
    print(" OK")

    url = f'http://127.0.0.1:{port}'

    # 验证首页和 JS 都能访问
    for path in ['/', '/api/novels']:
        try:
            r = urllib.request.urlopen(f'{url}{path}', timeout=2)
            assert r.status == 200, f"status={r.status}"
        except Exception as e:
            print(f"  验证失败 {path}: {e}")
            sys.exit(1)

    print(f"  打开窗口...")

    if use_browser:
        import webbrowser
        webbrowser.open(url)
        print(f"  浏览器: {url}")
        print("  按 Ctrl+C 退出")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        return

    # 桌面窗口
    try:
        import webview
        webview.create_window(
            title='AI 小说家',
            url=url,
            width=1400, height=900,
            min_size=(900, 600),
        )
        webview.start()
    except ImportError:
        print("  pywebview 未安装")
        import webbrowser
        webbrowser.open(url)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    except Exception as e:
        print(f"  窗口错误: {e}")
        print(f"  回退浏览器: {url}")
        import webbrowser
        webbrowser.open(url)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
