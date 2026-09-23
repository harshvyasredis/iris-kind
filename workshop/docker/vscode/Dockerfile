FROM codercom/code-server:4.96.4

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-pip tar \
    && rm -rf /var/lib/apt/lists/* \
    && pip3 install --break-system-packages 'httpx>=0.28.1' 'pyyaml>=6.0.2'

COPY scripts/ram_mcp.py scripts/ram_api.py scripts/langcache_mcp.py scripts/cr_mcp.py \
    /opt/workshop-mcp/
ENV PYTHONPATH=/opt/workshop-mcp

USER coder
RUN code-server --install-extension continue.continue
