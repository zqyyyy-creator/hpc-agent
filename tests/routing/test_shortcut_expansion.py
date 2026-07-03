from tests import _bootstrap  # noqa: F401

from modules.routing.router import expand_shortcut_command


def test_job_monitor_shortcuts_expand_to_tui_commands():
    assert expand_shortcut_command("/job monitor 11814753") == "监控 11814753"
    assert expand_shortcut_command("/job stop-monitor 11814753") == "取消监控 11814753"
    assert expand_shortcut_command("/job unmonitor 11814753") == "取消监控 11814753"


def test_resource_and_vasp_alias_shortcuts_expand():
    assert expand_shortcut_command("/resources") == "检查本机可用资源"
    assert expand_shortcut_command("/vasp jobs") == "列出 VASP 作业"
    assert (
        expand_shortcut_command("/vasp inputs Al_test --encut 400")
        == "帮我生成我的 VASP 作业 Al_test 的配置文件，参数 --encut 400"
    )
