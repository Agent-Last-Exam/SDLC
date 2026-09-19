FROM node:22-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash ca-certificates curl git ripgrep jq python3 procps less \
    && rm -rf /var/lib/apt/lists/*
RUN npm install -g @openai/codex@0.154.0 @anthropic-ai/claude-code@2.1.274 \
    && npm cache clean --force \
    && codex --version && claude --version
COPY workspace/ /workspace/
RUN chown -R root:root /workspace && chmod -R a-w /workspace \
    && rm -rf /workspace/artifacts \
    && mkdir -p /logs/artifacts /logs/agent \
    && ln -s /logs/artifacts /workspace/artifacts
WORKDIR /workspace
CMD ["sleep", "infinity"]
