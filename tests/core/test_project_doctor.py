from tests import _bootstrap  # noqa: F401

from modules.core.project_doctor import format_project_doctor, run_project_doctor


def test_project_doctor_collects_core_sections():
    def fake_run_remote_command(command):
        return "\n".join([
            "DIR\t/remote/work\tyes\tyes",
            "DIR\t/remote/vasp-input\tyes\tyes",
            "DIR\t/remote/vasp-output\tyes\tyes",
        ]), ""

    result = run_project_doctor(
        documents=["cluster info", "slurm pending"],
        sources=["cluster_info.txt#chunk0", "slurm_pending.txt#chunk0"],
        run_remote_command=fake_run_remote_command,
    )
    text = format_project_doctor(result)

    assert "project_paths" in result["sections"]
    assert "env_summary" in result["sections"]
    assert "entrypoint" in result["sections"]
    assert "hpc_environment" in result["sections"]
    assert "rag_documents" in result["sections"]
    assert "skill_registry" in result["sections"]
    assert "local_resources" in result["sections"]
    assert "HPC Agent 总体体检" in text
    assert ".env 关键变量" in text
    assert "包入口" in text
    assert "RAG 文档" in text
    assert "Skills Registry" in text


if __name__ == "__main__":
    test_project_doctor_collects_core_sections()
    print("All project doctor checks passed.")
