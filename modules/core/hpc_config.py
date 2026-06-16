import os
from pathlib import Path

from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parents[2] / ".env")

HOST = os.getenv("HPC_HOST")
USERNAME = os.getenv("HPC_USERNAME")
KEY_PATH = os.getenv("HPC_KEY_PATH")
REMOTE_WORKDIR = os.getenv("HPC_REMOTE_WORKDIR")

DEFAULT_PARTITION = os.getenv("HPC_DEFAULT_PARTITION", "")
VASP_PARTITION = os.getenv("HPC_VASP_PARTITION", DEFAULT_PARTITION)
VASP_LOCAL_JOBS_DIR = os.getenv(
    "HPC_LOCAL_VASP_JOBS_INPUT_DIR",
    os.getenv("HPC_LOCAL_VASP_JOBS_DIR", "~/vasp-jobs-input"),
)
VASP_LOCAL_OUTPUT_DIR = os.getenv("HPC_LOCAL_VASP_JOBS_OUTPUT_DIR", "~/vasp-jobs-output")


def derive_vasp_remote_dir(kind: str):
    explicit = os.getenv(f"HPC_VASP_REMOTE_{kind.upper()}_DIR")
    if explicit:
        return explicit

    legacy = os.getenv("HPC_VASP_REMOTE_WORKDIR")
    if legacy:
        return f"{legacy}-{kind}"

    if REMOTE_WORKDIR:
        return f"{str(Path(REMOTE_WORKDIR).parent)}/vasp-hpc-jobs-{kind}"

    return None


VASP_REMOTE_INPUT_DIR = derive_vasp_remote_dir("input")
VASP_REMOTE_OUTPUT_DIR = derive_vasp_remote_dir("output")
VASP_REMOTE_WORKDIR = VASP_REMOTE_OUTPUT_DIR
