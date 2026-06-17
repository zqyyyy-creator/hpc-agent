import shlex

import paramiko

from modules.core.hpc_config import HOST, KEY_PATH, USERNAME


def get_ssh_client():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    key = paramiko.Ed25519Key.from_private_key_file(KEY_PATH)
    client.connect(
        hostname=HOST,
        username=USERNAME,
        pkey=key,
    )

    return client


def run_remote_command(command):
    client = get_ssh_client()

    stdin, stdout, stderr = client.exec_command(command)
    output = stdout.read().decode()
    error = stderr.read().decode()

    client.close()

    return output, error


def create_remote_dir(client, remote_dir: str):
    command = f"mkdir -p {shlex.quote(remote_dir)}"
    stdin, stdout, stderr = client.exec_command(command)

    return stdout.read().decode(), stderr.read().decode()
