import subprocess
import sys
import traceback


def start_terminal():
    try:
        from main import main as terminal_main
        terminal_main()

    except Exception:
        print("\n启动 Terminal CLI 模式失败，完整错误如下：")
        traceback.print_exc()


def start_textual():
    try:
        from textual_cli import run_textual_cli
        run_textual_cli()

    except Exception:
        print("\n启动 Textual TUI 模式失败，完整错误如下：")
        traceback.print_exc()


def start_web():
    print("\n正在启动 Web 版 HPC Agent...")
    print("打开浏览器访问：http://127.0.0.1:8000")
    print("按 Ctrl+C 退出 Web 服务\n")

    try:
        subprocess.run([
            sys.executable,
            "-m",
            "uvicorn",
            "web_app:app",
            "--reload"
        ])

    except KeyboardInterrupt:
        print("\n已退出 Web 服务。")

    except Exception:
        print("\n启动 Web 模式失败，完整错误如下：")
        traceback.print_exc()


def main():
    print("=" * 60)
    print("HPC Agent 启动模式选择")
    print("=" * 60)
    print("1. Textual TUI 控制台模式")
    print("2. Terminal CLI 对话模式")
    print("3. Web 网页对话模式")
    print("输入 quit 退出")
    print("=" * 60)

    while True:
        choice = input("\n请选择模式 1/2/3: ").strip().lower()

        if choice == "1":
            start_textual()
            break

        elif choice == "2":
            start_terminal()
            break

        elif choice == "3":
            start_web()
            break

        elif choice == "quit":
            print("已退出 HPC Agent。")
            break

        else:
            print("无效选择，请输入 1、2、3 或 quit。")


if __name__ == "__main__":
    main()
