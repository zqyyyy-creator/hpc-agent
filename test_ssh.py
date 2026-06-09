import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

key = paramiko.Ed25519Key.from_private_key_file(
    "/home/lenovo/.ssh/id_ed25519"
)

client.connect(
    hostname="ssh.cn-zhongwei-1.paracloud.com",
    username="a0s000582@BSCC-A",
    pkey=key,
)

stdin, stdout, stderr = client.exec_command("hostname && pwd && squeue -u a0s000582")

print("STDOUT:")
print(stdout.read().decode())

print("STDERR:")
print(stderr.read().decode())

client.close()
