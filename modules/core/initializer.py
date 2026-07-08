from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path

from modules.core.paths import PROJECT_ROOT, USER_CACHE_DIR, USER_CONFIG_DIR, USER_DATA_DIR, USER_ENV_PATH, USER_ERRORS_DIR, USER_JOBS_DIR


def _target_env_path() -> Path:
    explicit = os.getenv("HPC_AGENT_ENV_PATH")
    if explicit:
        return Path(explicit).expanduser().resolve()
    return USER_ENV_PATH


def initialize_user_environment(*, overwrite: bool = False) -> dict:
    config_dir = USER_CONFIG_DIR
    data_dir = USER_DATA_DIR
    cache_dir = USER_CACHE_DIR
    jobs_dir = USER_JOBS_DIR
    errors_dir = USER_ERRORS_DIR
    env_path = _target_env_path()
    template_path = PROJECT_ROOT / ".env.example"

    created_dirs: list[Path] = []
    for directory in [config_dir, data_dir, cache_dir, jobs_dir, errors_dir]:
        if not directory.exists():
            directory.mkdir(parents=True, exist_ok=True)
            created_dirs.append(directory)

    env_created = False
    env_overwritten = False
    if env_path.exists() and not overwrite:
        env_status = "exists"
    else:
        if not template_path.is_file():
            raise FileNotFoundError(f"Cannot find .env template: {template_path}")
        env_path.parent.mkdir(parents=True, exist_ok=True)
        env_overwritten = env_path.exists()
        shutil.copyfile(template_path, env_path)
        env_created = not env_overwritten
        env_status = "overwritten" if env_overwritten else "created"

    return {
        "config_dir": config_dir,
        "data_dir": data_dir,
        "cache_dir": cache_dir,
        "jobs_dir": jobs_dir,
        "errors_dir": errors_dir,
        "env_path": env_path,
        "template_path": template_path,
        "created_dirs": created_dirs,
        "env_status": env_status,
        "env_created": env_created,
        "env_overwritten": env_overwritten,
        "using_user_env": env_path == USER_ENV_PATH,
    }


def format_initialization_result(result: dict) -> str:
    lines = [
        "HPC Agent 初始化完成",
        "",
        f"配置目录: {result['config_dir']}",
        f"数据目录: {result['data_dir']}",
        f"缓存目录: {result['cache_dir']}",
        f"作业记录目录: {result['jobs_dir']}",
        f"错误案例目录: {result['errors_dir']}",
        "",
    ]

    env_status = result.get("env_status")
    if env_status == "created":
        lines.append(f"已创建配置文件: {result['env_path']}")
    elif env_status == "overwritten":
        lines.append(f"已覆盖配置文件: {result['env_path']}")
    else:
        lines.append(f"配置文件已存在，未覆盖: {result['env_path']}")

    if result.get("created_dirs"):
        lines.append("")
        lines.append("本次创建的目录:")
        for directory in result["created_dirs"]:
            lines.append(f"- {directory}")

    lines.extend([
        "",
        "下一步:",
        f"1. 编辑 {result['env_path']}，填写 PARATERA_* 和 HPC_* 配置。",
        "2. 运行 hpc-agent-check 检查安装和配置。",
        "3. 运行 hpc-agent 启动 TUI。",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize HPC Agent user configuration.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the existing .env file with the bundled .env.example template.",
    )
    args = parser.parse_args()

    result = initialize_user_environment(overwrite=args.force)
    print(format_initialization_result(result))


if __name__ == "__main__":
    main()
