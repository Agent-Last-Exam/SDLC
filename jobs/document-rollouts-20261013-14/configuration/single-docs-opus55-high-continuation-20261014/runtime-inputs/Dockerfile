FROM sdlcbench/saleor-3.23-env:build-0a5d5bc656cb

# Keep the benchmark's preinstalled application dependencies, and add only the
# tools required by the workflow Agent. Network is needed while building this
# thin overlay and for model API calls, not for fetching target application code.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ripgrep jq procps less \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g @anthropic-ai/claude-code@2.1.273 \
    && npm cache clean --force \
    && claude --version

# Relocate the image's repositories to the workspace layout the runtime owns, and
# keep the original paths as links so the image's own test runtime still resolves.
RUN mkdir -p /workspace/repos \
    && test "$(git -C /workspace/saleor rev-parse HEAD)" = "c864e66b8e537d30732ddba62d3a4c47e49e4a3e" && mv /workspace/saleor /workspace/repos/saleor \
    && test "$(git -C /workspace/saleor-dashboard rev-parse HEAD)" = "aebb2401b5079fbbb8c60150289d1896c108feca" && mv /workspace/saleor-dashboard /workspace/repos/saleor-dashboard \
    && ln -s /workspace/repos/saleor /workspace/saleor \
    && ln -s /workspace/repos/saleor-dashboard /workspace/saleor-dashboard

COPY workspace/ /workspace/
RUN chown -R root:root /workspace \
    && chmod -R a-w /workspace \
    && rm -rf /workspace/artifacts \
    && mkdir -p /logs/artifacts /logs/agent \
    && ln -s /logs/artifacts /workspace/artifacts

WORKDIR /workspace
ENTRYPOINT []
CMD ["sleep", "infinity"]
