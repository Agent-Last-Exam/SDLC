# syntax=docker/dockerfile:1@sha256:ecfaec9ed6d810b56388c508f4121597bfbba70d41a6dfeee4d8cad5f295fc32
# Self-contained Harbor environment image. Saleor source comes only from the
# pinned 3.22 commits. The env patches turn those checkouts into the clean
# base + E agent baseline; no target application checkout enters the image.

FROM node@sha256:6dac556d980b7f0e5498d08f08cee0ca67798b4ad6c23964a9214920e67758d0 AS node-runtime
FROM valkey/valkey@sha256:fea8b3e67b15729d4bb70589eb03367bab9ad1ee89c876f54327fc7c6e618571 AS valkey-runtime
FROM ghcr.io/astral-sh/uv@sha256:1d31be550ff927957472b2a491dc3de1ea9b5c2d319a9cea5b6a48021e2990a6 AS uv-runtime

FROM python@sha256:581429e3df12d76e6af4be5ab7d0e7fc2013eb57dc23d2de691411c8efdbb970 AS base-dependencies

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_SYSTEM_PYTHON=1 \
    UV_PROJECT_ENVIRONMENT=/usr/local \
    UV_COMPILE_BYTECODE=1 \
    CI=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

COPY --from=node-runtime /usr/local /usr/local
COPY --from=valkey-runtime /usr/local/bin/valkey-server /usr/local/bin/valkey-server
COPY --from=valkey-runtime /usr/local/bin/valkey-cli /usr/local/bin/valkey-cli
COPY --from=uv-runtime /uv /uvx /usr/local/bin/

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential=12.9 \
        ca-certificates=20250419~deb12u1 \
        curl=7.88.1-10+deb12u15 \
        fonts-freefont-ttf=20120503-10 \
        fonts-ipafont-gothic=00303-23 \
        fonts-liberation=1:1.07.4-11 \
        fonts-noto-color-emoji=2.042-0+deb12u1 \
        fonts-tlwg-loma-otf=1:0.7.3-1 \
        fonts-unifont=1:15.0.01-2 \
        fonts-wqy-zenhei=0.9.45-8 \
        gettext=0.21-12 \
        git=1:2.39.5-0+deb12u3 \
        libasound2=1.2.8-1+b1 \
        libatk-bridge2.0-0=2.46.0-5 \
        libatk1.0-0=2.46.0-5 \
        libatspi2.0-0=2.46.0-5 \
        libcairo2=1.16.0-7 \
        libcups2=2.4.2-3+deb12u9 \
        libcurl4=7.88.1-10+deb12u15 \
        libdbus-1-3=1.14.10-1~deb12u1 \
        libdrm2=2.4.114-1+b1 \
        libffi8=3.4.4-1 \
        libfontconfig1=2.14.1-4 \
        libfreetype6=2.12.1+dfsg-5+deb12u4 \
        libgbm1=22.3.6-1+deb12u2 \
        libgdk-pixbuf-2.0-0=2.42.10+dfsg-1+deb12u4 \
        libglib2.0-0=2.74.6-2+deb12u9 \
        liblcms2-2=2.14-2+deb12u1 \
        libmagic1=1:5.44-3 \
        libnspr4=2:4.35-1 \
        libnss3=2:3.87.1-1+deb12u4 \
        libopenjp2-7=2.5.0-2+deb12u3 \
        libpango-1.0-0=1.50.12+ds-1 \
        libpq-dev=15.19-0+deb12u1 \
        libpq5=15.19-0+deb12u1 \
        libssl3=3.0.20-1~deb12u2 \
        libtiff6=4.5.0-6+deb12u4 \
        libwebp7=1.2.4-0.2+deb12u1 \
        media-types=10.0.0 \
        nginx-light=1.22.1-9+deb12u10 \
        postgresql-15=15.19-0+deb12u1 \
        postgresql-client-15=15.19-0+deb12u1 \
        shared-mime-info=2.2-1 \
        libx11-6=2:1.8.4-2+deb12u2 \
        libxcb1=1.15-1 \
        libxcomposite1=1:0.4.5-1 \
        libxdamage1=1:1.1.6-1 \
        libxext6=2:1.3.4-1+b1 \
        libxfixes3=1:6.0.0-2 \
        libxkbcommon0=1.5.0-1 \
        libxrandr2=2:1.5.2-2+b1 \
        xfonts-scalable=1:1.0.3-1.3 \
        xvfb=2:21.1.7-3+deb12u13 \
        xz-utils=5.4.1-1+deb12u2 \
    && pg_dropcluster --stop 15 main \
    && rm -rf /var/lib/apt/lists/*

ARG MAILPIT_VERSION=v1.31.1
ARG MAILPIT_SHA256=87d2652abd7c17dc99029147ff62ac671afdf7fd76630f7faf5b14125211c709
RUN curl -fsSL -o /tmp/mailpit.tar.gz \
        "https://github.com/axllent/mailpit/releases/download/${MAILPIT_VERSION}/mailpit-linux-amd64.tar.gz" \
    && echo "${MAILPIT_SHA256}  /tmp/mailpit.tar.gz" | sha256sum --check - \
    && tar -xzf /tmp/mailpit.tar.gz -C /usr/local/bin mailpit \
    && rm /tmp/mailpit.tar.gz \
    && chmod +x /usr/local/bin/mailpit

ARG CORE_SHA=6cfb77430ddbc53f48dfd3462fbefaad4e8c3d45
ARG DASHBOARD_SHA=e934ff0abf5e643d2e8eab5cce609387fe0e37b6
ARG PLATFORM_SHA=8330f42e5673fe0c4fd4a445d6789bd257cc9265
ARG CORE_BASELINE_SHA=c864e66b8e537d30732ddba62d3a4c47e49e4a3e
ARG DASHBOARD_BASELINE_SHA=aebb2401b5079fbbb8c60150289d1896c108feca
RUN git init -q /workspace/saleor \
    && git -C /workspace/saleor remote add origin https://github.com/saleor/saleor.git \
    && git -C /workspace/saleor fetch --depth=1 origin "$CORE_SHA" \
    && git -C /workspace/saleor checkout --detach FETCH_HEAD \
    && git init -q /workspace/saleor-dashboard \
    && git -C /workspace/saleor-dashboard remote add origin https://github.com/saleor/saleor-dashboard.git \
    && git -C /workspace/saleor-dashboard fetch --depth=1 origin "$DASHBOARD_SHA" \
    && git -C /workspace/saleor-dashboard checkout --detach FETCH_HEAD \
    && git init -q /tmp/saleor-platform \
    && git -C /tmp/saleor-platform remote add origin https://github.com/saleor/saleor-platform.git \
    && git -C /tmp/saleor-platform fetch --depth=1 origin "$PLATFORM_SHA" \
    && git -C /tmp/saleor-platform checkout --detach FETCH_HEAD \
    && cp /tmp/saleor-platform/replica_user.sql /workspace/replica_user.sql \
    && rm -rf /tmp/saleor-platform

# Install the complete base dependency set first. This stage is retained as
# the source of base-only Node packages when target dependencies are installed.
WORKDIR /workspace/saleor
RUN uv sync --locked --all-groups --no-install-project

WORKDIR /workspace/saleor-dashboard
RUN npm ci

# E is applied only after the original base dependencies are captured above.
# The resulting deterministic commit is the immutable diff base for the agent.
COPY harbor/saleor-3.23/env/saleor.env.patch /opt/environment/env-patches/saleor.env.patch
COPY harbor/saleor-3.23/env/saleor-dashboard.env.patch /opt/environment/env-patches/saleor-dashboard.env.patch
RUN git -C /workspace/saleor apply --index --whitespace=nowarn /opt/environment/env-patches/saleor.env.patch \
    && GIT_AUTHOR_NAME=SDLCBench GIT_AUTHOR_EMAIL=sdlcbench@localhost GIT_AUTHOR_DATE=2000-01-01T00:00:00Z \
       GIT_COMMITTER_NAME=SDLCBench GIT_COMMITTER_EMAIL=sdlcbench@localhost GIT_COMMITTER_DATE=2000-01-01T00:00:00Z \
       git -C /workspace/saleor commit -q -m "Apply Saleor 3.23 environment patch" \
    && git -C /workspace/saleor update-ref refs/sdlcbench/agent-baseline HEAD \
    && git -C /workspace/saleor-dashboard apply --index --whitespace=nowarn /opt/environment/env-patches/saleor-dashboard.env.patch \
    && GIT_AUTHOR_NAME=SDLCBench GIT_AUTHOR_EMAIL=sdlcbench@localhost GIT_AUTHOR_DATE=2000-01-01T00:00:00Z \
       GIT_COMMITTER_NAME=SDLCBench GIT_COMMITTER_EMAIL=sdlcbench@localhost GIT_COMMITTER_DATE=2000-01-01T00:00:00Z \
       git -C /workspace/saleor-dashboard commit -q -m "Apply Saleor 3.23 environment patch" \
    && git -C /workspace/saleor-dashboard update-ref refs/sdlcbench/agent-baseline HEAD \
    && test "$(git -C /workspace/saleor rev-parse HEAD)" = "$CORE_BASELINE_SHA" \
    && test "$(git -C /workspace/saleor-dashboard rev-parse HEAD)" = "$DASHBOARD_BASELINE_SHA" \
    && rm -rf /opt/environment/env-patches

FROM base-dependencies AS assembled

COPY images/saleor-3.23/base/dependencies /opt/environment/dependencies
COPY images/saleor-3.23/base/runtime /opt/runtime
RUN cd /opt/environment/dependencies && sha256sum --check SHA256SUMS

# Upgrade shared Python packages to target-locked versions without removing
# packages used only by base. No target application source is present.
WORKDIR /opt/environment/dependencies/target/saleor
RUN uv export --locked --all-groups --no-emit-project \
        --format requirements-txt --output-file /tmp/target-requirements.txt \
    && uv pip install --system --requirements /tmp/target-requirements.txt \
    && rm /tmp/target-requirements.txt

# Install the target dashboard dependency tree from packaged manifests, then
# add base-only top-level packages from the base dependency stage.
RUN rm -f /usr/local/bin/yarn /usr/local/bin/yarnpkg \
    && corepack enable \
    && corepack prepare pnpm@10.28.1 --activate
WORKDIR /opt/environment/dependencies/target/saleor-dashboard
RUN pnpm install --frozen-lockfile
RUN rm -rf /workspace/saleor-dashboard/node_modules \
    && mv /opt/environment/dependencies/target/saleor-dashboard/node_modules \
        /workspace/saleor-dashboard/node_modules
RUN --mount=from=base-dependencies,source=/workspace/saleor-dashboard/node_modules,target=/opt/base-node-modules,ro \
    python3 /opt/runtime/merge_dependencies.py

# Validate both base source trees using the union dependency environment.
WORKDIR /workspace/saleor
RUN SECRET_KEY=dummy STATIC_URL=/static/ python3 manage.py collectstatic --no-input

WORKDIR /workspace/saleor-dashboard
ENV API_URL=http://localhost:8000/graphql/ \
    APP_MOUNT_URI=/ \
    STATIC_URL=/ \
    SKIP_SOURCEMAPS=true \
    LOCALE_CODE=EN
RUN --network=none NODE_OPTIONS=--max-old-space-size=4096 node_modules/.bin/vite build
RUN node_modules/.bin/playwright install chromium \
    && rm -rf /var/lib/apt/lists/* /root/.cache/uv /root/.cache/pnpm /tmp/*

COPY images/saleor-3.23/base/runtime/nginx-dashboard.conf /etc/nginx/sites-available/default
RUN chmod +x /opt/runtime/*.sh \
    && mkdir -p /workspace/saleor/media /workspace/logs /logs/verifier \
    && git config --global --add safe.directory /workspace/saleor \
    && git config --global --add safe.directory /workspace/saleor-dashboard \
    && test "$(git -C /workspace/saleor rev-parse HEAD)" = "$CORE_BASELINE_SHA" \
    && test "$(git -C /workspace/saleor-dashboard rev-parse HEAD)" = "$DASHBOARD_BASELINE_SHA" \
    && test "$(git -C /workspace/saleor rev-parse refs/sdlcbench/agent-baseline)" = "$CORE_BASELINE_SHA" \
    && test "$(git -C /workspace/saleor-dashboard rev-parse refs/sdlcbench/agent-baseline)" = "$DASHBOARD_BASELINE_SHA" \
    && test "$(git -C /workspace/saleor rev-list --all --count)" = 2 \
    && test "$(git -C /workspace/saleor-dashboard rev-list --all --count)" = 2 \
    && test -z "$(git -C /workspace/saleor status --porcelain)" \
    && test -z "$(git -C /workspace/saleor-dashboard status --porcelain)"

# Flatten the assembled filesystem so build-stage layers and package-manager
# caches are absent from the delivered image. The visible source is exactly
# the two deterministic base + E checkouts above.
FROM scratch
COPY --from=assembled / /

ENV PATH=/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin \
    LANG=C.UTF-8 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_SYSTEM_PYTHON=1 \
    UV_PROJECT_ENVIRONMENT=/usr/local \
    UV_COMPILE_BYTECODE=1 \
    PYTHONPATH="" \
    SALEOR_APPEXTENSION_COMPAT=0 \
    TEST_SUITE=base \
    CI=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    API_URL=http://localhost:8000/graphql/ \
    APP_MOUNT_URI=/ \
    STATIC_URL=/static/ \
    SKIP_SOURCEMAPS=true \
    LOCALE_CODE=EN \
    DATABASE_URL=postgres://saleor:saleor@127.0.0.1:5432/saleor \
    DATABASE_URL_REPLICA=postgres://saleor_read_only:saleor@127.0.0.1:5432/saleor \
    CACHE_URL=redis://127.0.0.1:6379/0 \
    CELERY_BROKER_URL=redis://127.0.0.1:6379/1 \
    EMAIL_URL=smtp://127.0.0.1:1025 \
    DEFAULT_FROM_EMAIL=noreply@example.com \
    DEFAULT_CHANNEL_SLUG=default-channel \
    HTTP_IP_FILTER_ENABLED=True \
    HTTP_IP_FILTER_ALLOW_LOOPBACK_IPS=True \
    DASHBOARD_URL=http://127.0.0.1:9000/ \
    ALLOWED_HOSTS=localhost,127.0.0.1,api \
    BASE_URL=http://127.0.0.1:9000/ \
    MAILPITURL=http://127.0.0.1:8025 \
    E2E_USER_NAME=admin@example.com

WORKDIR /workspace
EXPOSE 8000 9000 5432 6379 1025 8025
ENTRYPOINT []
