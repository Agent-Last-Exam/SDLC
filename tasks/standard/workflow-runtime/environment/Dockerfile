FROM sdlcbench/saleor-3.23-base:standard-a-20260920

# Keep the benchmark's preinstalled application dependencies, and add only the
# tools required by the workflow Agent. Network is needed while building this
# thin overlay and for model API calls, not for fetching target application code.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ripgrep jq procps less \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g @openai/codex@0.154.0 \
    && npm cache clean --force \
    && codex --version

COPY workspace/ /workspace/
RUN chown -R root:root /workspace \
    && chmod -R a-w /workspace \
    && rm -rf /workspace/artifacts \
    && mkdir -p /logs/artifacts /logs/agent \
    && ln -s /logs/artifacts /workspace/artifacts

WORKDIR /workspace
ENTRYPOINT []
CMD ["sleep", "infinity"]
