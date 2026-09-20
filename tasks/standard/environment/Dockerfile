# syntax=docker/dockerfile:1
# Self-contained Harbor environment image. Saleor source comes only from the
# pinned 3.22 commits; target inputs are dependency manifests under
# dependencies/target/.

FROM node:24-bookworm AS node-runtime
FROM valkey/valkey:8.1-bookworm AS valkey-runtime
FROM ghcr.io/astral-sh/uv:0.8 AS uv-runtime

FROM python:3.12-bookworm AS base-dependencies

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
        build-essential \
        ca-certificates \
        curl \
        gettext \
        git \
        libcurl4 \
        libffi8 \
        libgdk-pixbuf-2.0-0 \
        liblcms2-2 \
        libmagic1 \
        libopenjp2-7 \
        libpq-dev \
        libpq5 \
        libssl3 \
        libtiff6 \
        libwebp7 \
        media-types \
        nginx-light \
        postgresql-15 \
        postgresql-client-15 \
        postgresql-contrib-15 \
        shared-mime-info \
        xz-utils \
    && rm -rf /var/lib/apt/lists/*

ARG MAILPIT_VERSION=v1.31.1
RUN curl -fsSL -o /tmp/mailpit.tar.gz \
        "https://github.com/axllent/mailpit/releases/download/${MAILPIT_VERSION}/mailpit-linux-amd64.tar.gz" \
    && tar -xzf /tmp/mailpit.tar.gz -C /usr/local/bin mailpit \
    && rm /tmp/mailpit.tar.gz \
    && chmod +x /usr/local/bin/mailpit

ARG CORE_SHA=6cfb77430ddbc53f48dfd3462fbefaad4e8c3d45
ARG DASHBOARD_SHA=e934ff0abf5e643d2e8eab5cce609387fe0e37b6
ARG PLATFORM_SHA=8330f42e5673fe0c4fd4a445d6789bd257cc9265
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

FROM base-dependencies AS assembled

COPY build_metadata.json /opt/environment/build_metadata.json
COPY dependencies /opt/environment/dependencies
COPY runtime /opt/runtime
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
RUN NODE_OPTIONS=--max-old-space-size=4096 node_modules/.bin/vite build \
    && node_modules/.bin/playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/* /root/.cache/uv /root/.cache/pnpm /tmp/*

COPY runtime/nginx-dashboard.conf /etc/nginx/sites-available/default
RUN chmod +x /opt/runtime/*.sh \
    && mkdir -p /workspace/saleor/media /workspace/logs /logs/verifier \
    && git config --global --add safe.directory /workspace/saleor \
    && git config --global --add safe.directory /workspace/saleor-dashboard \
    && test "$(git -C /workspace/saleor rev-parse HEAD)" = "$CORE_SHA" \
    && test "$(git -C /workspace/saleor-dashboard rev-parse HEAD)" = "$DASHBOARD_SHA" \
    && test "$(git -C /workspace/saleor rev-list --all --count)" = 1 \
    && test "$(git -C /workspace/saleor-dashboard rev-list --all --count)" = 1 \
    && test -z "$(git -C /workspace/saleor status --porcelain)" \
    && test -z "$(git -C /workspace/saleor-dashboard status --porcelain)"

# Flatten the assembled filesystem so build-stage layers and package-manager
# caches are absent from the delivered image. The visible source is exactly
# the two shallow base checkouts above.
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
    SECRET_KEY=changeme \
    DEFAULT_CHANNEL_SLUG=default-channel \
    HTTP_IP_FILTER_ENABLED=True \
    HTTP_IP_FILTER_ALLOW_LOOPBACK_IPS=True \
    DASHBOARD_URL=http://127.0.0.1:9000/ \
    ALLOWED_HOSTS=localhost,127.0.0.1,api \
    BASE_URL=http://127.0.0.1:9000/ \
    MAILPITURL=http://127.0.0.1:8025 \
    E2E_USER_NAME=admin@example.com \
    E2E_USER_PASSWORD=admin \
    E2E_PERMISSIONS_USERS_PASSWORD=password

WORKDIR /workspace
EXPOSE 8000 9000 5432 6379 1025 8025
ENTRYPOINT []
