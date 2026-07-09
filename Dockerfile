ARG PYTHON_VERSION=3.12

FROM python:${PYTHON_VERSION}-slim

ARG HPC_AGENT_VERSION=0.2.3

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HPC_AGENT_CONFIG_DIR=/config \
    HPC_AGENT_DATA_DIR=/data \
    HPC_AGENT_CACHE_DIR=/cache

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        openssh-client \
    && rm -rf /var/lib/apt/lists/*

COPY dist/hpc_agent-${HPC_AGENT_VERSION}-py3-none-any.whl /tmp/

RUN pip install --no-cache-dir /tmp/hpc_agent-${HPC_AGENT_VERSION}-py3-none-any.whl \
    && rm -f /tmp/hpc_agent-${HPC_AGENT_VERSION}-py3-none-any.whl \
    && mkdir -p /config /data /cache /workspace /ssh /vasp-input /vasp-output

WORKDIR /workspace

ENTRYPOINT ["hpc-agent"]
