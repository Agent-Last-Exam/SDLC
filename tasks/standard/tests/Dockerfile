FROM sdlcbench/saleor-3.23-base:standard-a-20260920
COPY . /tests/
COPY seed_e2e_fixtures.py /opt/runtime/seed_e2e_fixtures.py
ENV TEST_SUITE=target
RUN python3 /tests/apply_patches.py test --workspace /workspace --package / --manifest /tests/patch_manifest.json \
    && chmod +x /tests/test.sh
ENTRYPOINT []
