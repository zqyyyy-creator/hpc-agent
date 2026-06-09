import paramiko

HOST = "ssh.cn-zhongwei-1.paracloud.com"
USERNAME = "a0s000582@BSCC-A"
KEY_PATH = "/home/lenovo/.ssh/id_ed25519"


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