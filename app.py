import subprocess
import sys


def start_terminal():
    from main import main
    main()


def start_web():
    print("\n正在启动 Web 版 HPC Agent...")
    print("打开浏览器访问：http://127.0.0.1:8000")
    print("按 Ctrl+C 退出 Web 服务\n")

    subprocess.run([
        sys.executable,
        "-m",
        "uvicorn",
        "web_app:app",
        "--reload"
    ])


def main():
    print("=" * 60)
    print("HPC Agent 启动模式选择")
    print("=" * 60)
    print("1. Terminal CLI 对话模式")
    print("2. Web 网页对话模式")
    print("输入 quit 退出")
    print("=" * 60)

    while True:
        choice = input("\n请选择模式 1/2: ").strip().lower()

        if choice == "1":
            start_terminal()
            break

        elif choice == "2":
            start_web()
            break

        elif choice == "quit":
            print("已退出 HPC Agent。")
            break

        else:
            print("无效选择，请输入 1、2 或 quit。")


if __name__ == "__main__":
    main()