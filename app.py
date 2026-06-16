import traceback


def main():
    try:
        from textual_cli import run_textual_cli

        run_textual_cli()
    except Exception:
        print("\n启动 Textual TUI 模式失败，完整错误如下：")
        traceback.print_exc()


if __name__ == "__main__":
    main()
