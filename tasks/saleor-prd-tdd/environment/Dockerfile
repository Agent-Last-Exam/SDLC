FROM node:22-bookworm-slim AS node
FROM python:3.12-slim-bookworm
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
    && ln -s ../lib/node_modules/corepack/dist/corepack.js /usr/local/bin/corepack
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash ca-certificates curl git ripgrep jq procps less \
    build-essential pkg-config libpq-dev postgresql postgresql-contrib redis-server \
    libmagic1 libcairo2 libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 \
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
