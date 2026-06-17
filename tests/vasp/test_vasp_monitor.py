from tests import _bootstrap

from modules.vasp.vasp_monitor import diagnose_remote_vasp_job


def test_potcar_input_conversion_is_error():
    def fake_run_remote_command(command):
        output = "\n".join([
            "FILE\tOUTCAR\t452\t1780000000",
            "FILE\tOSZICAR\t0\t1780000000",
            "FILE\tvasprun.xml\t434\t1780000000",
            "__TAIL_OUTCAR__",
            "vasp.5.3.3 18Dez12",
            "forrtl: severe (64): input conversion error, unit 10, file ../POTCAR",
        ])
        return output, ""

    diagnosis = diagnose_remote_vasp_job(
        "/remote/vasp-hpc-jobs-output/si_static_test",
        run_remote_command=fake_run_remote_command,
    )

    assert diagnosis["is_vasp"]
    assert diagnosis["severity"] == "error"
    assert any(issue["id"] == "potcar_input_conversion" for issue in diagnosis["issues"])
    assert any("OUTCAR: 452 bytes" in item for item in diagnosis["evidence"])


def test_brmix_warning_is_warning():
    def fake_run_remote_command(command):
        output = "\n".join([
            "FILE\tOUTCAR\t40960\t1780000000",
            "FILE\tOSZICAR\t2048\t1780000000",
            "__TAIL_OUTCAR__",
            "BRMIX: very serious problems",
        ])
        return output, ""

    diagnosis = diagnose_remote_vasp_job(
        "/remote/vasp-hpc-jobs-output/relax",
        run_remote_command=fake_run_remote_command,
    )

    assert diagnosis["is_vasp"]
    assert diagnosis["severity"] == "warning"
    assert any(issue["id"] == "brmix" for issue in diagnosis["issues"])


def test_empty_oszicar_is_suppressed_for_running_job():
    def fake_run_remote_command(command):
        output = "\n".join([
            "FILE\tOUTCAR\t40960\t1780000000",
            "FILE\tOSZICAR\t0\t1780000000",
            "__TAIL_OUTCAR__",
            "vasp.6.2.1 running",
        ])
        return output, ""

    diagnosis = diagnose_remote_vasp_job(
        "/remote/vasp-hpc-jobs-output/running",
        run_remote_command=fake_run_remote_command,
        job_is_terminal=False,
    )

    assert diagnosis["is_vasp"]
    assert diagnosis["severity"] == "ok"
    assert not any(issue["id"] == "empty_oszicar" for issue in diagnosis["issues"])


def test_empty_oszicar_is_warning_for_terminal_job():
    def fake_run_remote_command(command):
        output = "\n".join([
            "FILE\tOUTCAR\t40960\t1780000000",
            "FILE\tOSZICAR\t0\t1780000000",
            "__TAIL_OUTCAR__",
            "vasp.6.2.1 finished without iterations",
        ])
        return output, ""

    diagnosis = diagnose_remote_vasp_job(
        "/remote/vasp-hpc-jobs-output/terminal",
        run_remote_command=fake_run_remote_command,
        job_is_terminal=True,
    )

    assert diagnosis["is_vasp"]
    assert diagnosis["severity"] == "warning"
    assert any(issue["id"] == "empty_oszicar" for issue in diagnosis["issues"])


def test_non_vasp_directory_stays_unknown():
    def fake_run_remote_command(command):
        return "FILE\ttrain.out\t1024\t1780000000\nall good\n", ""

    diagnosis = diagnose_remote_vasp_job(
        "/remote/hpc-agent-jobs/train",
        log_output="STDOUT:\ntraining loss 0.1",
        run_remote_command=fake_run_remote_command,
    )

    assert not diagnosis["is_vasp"]
    assert diagnosis["severity"] == "unknown"
