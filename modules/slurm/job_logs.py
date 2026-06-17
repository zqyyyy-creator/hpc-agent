import shlex

from modules.core.hpc_config import REMOTE_WORKDIR
from modules.slurm.remote import run_remote_command


def read_slurm_file_from_remote_dir(job_id, remote_workdir, extension, title):
    remote_dir = shlex.quote(remote_workdir)
    safe_job_id = shlex.quote(str(job_id))
    command = (
        f"cd {remote_dir} && "
        "{ "
        "echo 'Remote job directory:'; pwd; "
        "echo ''; echo 'Files:'; ls -1; "
        f"echo ''; echo '{title}:'; "
        f"if ls *_{safe_job_id}.{extension} >/dev/null 2>&1; then cat *_{safe_job_id}.{extension}; "
        f"elif ls *.{extension} >/dev/null 2>&1; then cat *.{extension}; "
        f"else echo 'No {title} file found yet.'; fi; "
        "}"
    )

    output, error = run_remote_command(command)

    return {
        "job_id": job_id,
        "output": output,
        "error": error,
    }


def read_job_output(job_id):
    from modules.slurm.job_registry import get_job

    job = get_job(job_id)

    if job and job.get("type") == "vasp" and job.get("remote_workdir"):
        remote_dir = shlex.quote(job["remote_workdir"])
        command = (
            f"cd {remote_dir} && "
            "{ "
            "echo 'Remote VASP directory:'; pwd; "
            "echo ''; echo 'Files:'; ls -1; "
            "echo ''; echo 'vasp.out:'; "
            "if [ -f vasp.out ]; then cat vasp.out; "
            f"elif ls *_{job_id}.out >/dev/null 2>&1; then cat *_{job_id}.out; "
            "elif ls *.out >/dev/null 2>&1; then cat *.out; "
            "else echo 'No VASP stdout file found yet.'; fi; "
            "}"
        )

        output, error = run_remote_command(command)

        return {
            "job_id": job_id,
            "output": output,
            "error": error,
        }

    if job and job.get("remote_workdir"):
        return read_slurm_file_from_remote_dir(
            job_id,
            job["remote_workdir"],
            "out",
            "stdout",
        )

    command = (
        f"cd {REMOTE_WORKDIR} && "
        f"cat hpc_agent_job_{job_id}.out 2>/dev/null || "
        f"cat agent_{job_id}.out"
    )

    output, error = run_remote_command(command)

    return {
        "job_id": job_id,
        "output": output,
        "error": error,
    }


def read_job_error(job_id):
    from modules.slurm.job_registry import get_job

    job = get_job(job_id)

    if job and job.get("type") == "vasp" and job.get("remote_workdir"):
        remote_dir = shlex.quote(job["remote_workdir"])
        command = (
            f"cd {remote_dir} && "
            "{ "
            "echo 'Remote VASP directory:'; pwd; "
            "echo ''; echo 'Files:'; ls -1; "
            "echo ''; echo 'Slurm/VASP stderr:'; "
            f"if ls *_{job_id}.err >/dev/null 2>&1; then cat *_{job_id}.err; "
            "elif ls *.err >/dev/null 2>&1; then cat *.err; "
            "else echo 'No VASP stderr file found yet.'; fi; "
            "}"
        )

        output, error = run_remote_command(command)

        return {
            "job_id": job_id,
            "output": output,
            "error": error,
        }

    if job and job.get("remote_workdir"):
        return read_slurm_file_from_remote_dir(
            job_id,
            job["remote_workdir"],
            "err",
            "stderr",
        )

    command = (
        f"cd {REMOTE_WORKDIR} && "
        f"cat hpc_agent_job_{job_id}.err 2>/dev/null || "
        f"cat agent_{job_id}.err"
    )

    output, error = run_remote_command(command)

    return {
        "job_id": job_id,
        "output": output,
        "error": error,
    }
