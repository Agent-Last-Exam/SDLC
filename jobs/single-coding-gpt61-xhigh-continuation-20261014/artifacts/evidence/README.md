# 开发自测证据索引

日期：2026-10-14；阶段：sprint1/development；轮次：1。

本目录保存本轮选定最终验证结果，不是 QA 验收记录，不代表全仓或冻结测试全部通过。主报告为 [`../test-handoff.md`](../test-handoff.md)。`evidence-files.json` 记录归档文件的来源、长度和 SHA256；原始日志及临时验证脚本位于 `/workspace/scratch/`。

## 1. 证据与结果

| 文件 | 结果 / 用途 |
| --- | --- |
| `backend-handoff-regression.log` | 1377 passed，1 warning；主要后端选定回归 |
| `backend-content-entrypoints.log` | 391 passed，1 warning；页面、翻译、属性、分类、集合、商品类型的既有写入回归 |
| `backend-editorjs-compatibility.log` | 43 passed：EditorJS 合同 41 + 商品批量描述 2；已包含在 1377 中，不累计 |
| `backend-legacy-editorjs-final.log` | 9 failed，3 passed；未修改的旧 EditorJS 测试，具体差异见主报告 |
| `backend-handoff-ruff-check.log` / `backend-handoff-ruff-format-check.log` | 全部变更/新增 Python 文件：检查通过，88 文件格式通过 |
| `backend-handoff-system-check.log` | Django check：0 issues |
| `backend-handoff-migration-drift.log` | No changes detected |
| `backend-handoff-migration-check.log` | migrate --check 成功，无待执行迁移；该命令成功时无正文，仅环境警告 |
| `backend-empty-db-migrate-psycopg3.log` | 独立空库 1342 个迁移步骤全部 OK |
| `backend-empty-db-system-check-final.log` / `backend-empty-db-migration-check-final.log` | 空库初始化后系统检查、无待执行迁移检查通过 |
| `backend-historical-upgrade-rehearsal.log` / `migration-upgrade-result.json` | 独立合成旧库升级演练通过，选定历史事实前后摘要一致；非生产分布审计、资金账本迁移或发布回退演练 |
| `schema-export-handoff.log` | 实际 SDL 最后导出成功；正文导出在 scratch，不把环境警告混入 SDL |
| `schema-contract-audit.log` / `schema-target-diff.json` | 目标 SDL 的静态结构差异清单，不是验收通过结果 |
| `dashboard-types-final.log` | Playwright TS、src TS、2832 strict files 通过；并未运行 Playwright E2E |
| `dashboard-tests-final.log` | 12 suites、77 tests 通过 |
| `dashboard-codegen-verified.log` | 四个 codegen 输出目标成功 |
| `dashboard-messages-delivery.log` | 文案提取成功 |
| `dashboard-changed-lint-delivery.log` | 增量 ESLint：0 errors、28 warnings |
| `dashboard-eslint-summary.json` | 全量 ESLint：192 errors、2469 warnings；错误与变更文件交集为 0，未完成全量基线归因 |
| `dashboard-knip-delivery.log` | Knip 未通过：9 项 unused devDependencies 为 error，另有警告 |
| `dashboard-build-verified.log` | 隔离 Vite 生产模式 bundle 成功；排除上传、遥测/检查器及复制插件，不是标准发布包或部署 |
| `test-fixture-key-classification.json` | 两个固定私钥形状命中均为与基线相同的合成测试 fixture；不包含密钥正文，不可用于部署 |

完整 ESLint JSON 原件在 `/workspace/scratch/logs/dashboard-full-eslint.json`；归档的是包含全部 error 明细的摘要。中途失败的环境准备日志不作为通过证据，例如曾使用不存在的 psycopg2 的旧迁移脚本；当前空库结论只依据 psycopg3 修正后真实完成的日志及后续检查。

## 2. 后端复现

从 `/workspace/repos/saleor` 执行，先进入既有 virtualenv。下列 URL 仅是本地隔离数据库，无生产口令；不要指向真实业务库。重新复现需先准备本地 PostgreSQL、依赖和 scratch 设置；它们不包含在源码内容标识中。

```bash
set -euo pipefail
. /workspace/scratch/venv/bin/activate
export PYTHONPATH=/workspace/scratch:/workspace/repos/saleor
export PYTHONDONTWRITEBYTECODE=1
export DATABASE_URL=postgres://stage1231@127.0.0.1:55432/saleor_development
export DATABASE_URL_REPLICA="$DATABASE_URL"
export DJANGO_SETTINGS_MODULE=stage_test_settings
export PYTEST_ADDOPTS=--ds=stage_test_settings
export TMPDIR=/workspace/scratch
export RUFF_CACHE_DIR=/workspace/scratch/ruff

python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate --check

python -m pytest -n0 --reuse-db --record-mode=none \
  --basetemp=/workspace/scratch/pytest-tmp-handoff-regression \
  -o cache_dir=/workspace/scratch/pytest-cache \
  saleor/core/utils/tests/test_editorjs_contract.py \
  saleor/graphql/channel/tests/mutations/test_sprint1_settings.py \
  saleor/graphql/account/tests/mutations/authentication \
  saleor/graphql/account/tests/mutations/staff/test_staff_delete.py \
  saleor/graphql/meta/tests \
  saleor/app/tests/test_extension_contract.py \
  saleor/graphql/app/tests/queries \
  saleor/plugins/openid_connect/tests \
  saleor/graphql/core/tests/test_scalars.py \
  saleor/graphql/core/tests/test_input_contract.py \
  saleor/graphql/checkout/tests/mutations/test_checkout_shipping_refresh.py \
  saleor/plugins/webhook/tests/test_fresh_shipping.py \
  saleor/plugins/webhook/tests/test_list_shipping_methods_for_checkout.py \
  saleor/plugins/webhook/tests/test_shipping_exclude_cache.py \
  saleor/graphql/product/tests/test_bulk_description_contract.py \
  saleor/graphql/shop/tests/mutations/test_shop_settings_update.py \
  saleor/graphql/order/tests/queries/test_shipping_snapshot_contract.py \
  saleor/checkout/tests/test_shipping_snapshot_contract.py \
  saleor/checkout/tests/test_checkout_complete.py \
  saleor/checkout/tests/test_order_from_checkout.py
```

第二组选定内容入口回归（391）使用 `/workspace/scratch/verify-content-entrypoints.sh`，其 pytest 路径如下，与主要回归不重复：

```bash
python -m pytest -n0 --reuse-db --record-mode=none \
  --basetemp=/workspace/scratch/pytest-tmp-content-entrypoints \
  -o cache_dir=/workspace/scratch/pytest-cache \
  saleor/graphql/page/tests/mutations/test_page_create.py \
  saleor/graphql/page/tests/mutations/test_page_update.py \
  saleor/graphql/page/tests/deprecated/test_page_create.py \
  saleor/graphql/page/tests/deprecated/test_page_update.py \
  saleor/graphql/translations/tests/test_translations.py \
  saleor/graphql/translations/tests/deprecated/test_translations.py \
  saleor/graphql/product/tests/mutations/test_category_create.py \
  saleor/graphql/product/tests/mutations/test_category_update.py \
  saleor/graphql/product/tests/mutations/test_collection_create.py \
  saleor/graphql/product/tests/mutations/test_collection_update.py \
  saleor/graphql/product/tests/mutations/test_product_type_create.py \
  saleor/graphql/product/tests/mutations/test_product_type_update.py \
  saleor/graphql/attribute/tests/mutations/test_attribute_create.py \
  saleor/graphql/attribute/tests/mutations/test_attribute_update.py
```

旧 EditorJS 回归须独立执行并保留失败退出码，不能接成功输出掩盖失败：

```bash
python -m pytest -n0 --reuse-db --record-mode=none \
  --basetemp=/workspace/scratch/pytest-tmp-legacy-editorjs \
  -o cache_dir=/workspace/scratch/pytest-cache \
  saleor/core/utils/tests/test_editorjs.py
```

`stage_test_settings.py` 继承 `saleor.tests.settings`，只将 MEDIA_ROOT、PRIVATE_MEDIA_ROOT、EMAIL_FILE_PATH 放到 scratch，并使用 LocMemCache。数据库依赖 psycopg 3，不是 psycopg2。临时 SECRET_KEY 警告仅限隔离测试；部署必须提供稳定密钥及轮换策略，不可复用测试私钥。

空库验证在 `saleor_sprint1_empty` 完成，不需要为提测重复创建或覆盖。历史升级脚本为 `/workspace/scratch/rehearse-upgrade.py`：从该隔离模板创建新库，将所涉及 app 回退到本次变更前 schema，注入合成历史样本，再升级到当前迁移；目标库 `saleor_sprint1_upgrade_rehearsal` 已存在时脚本拒绝覆盖。需要再次演练时应另用新的隔离库名，不能对部署库执行回退。完整事实范围和限制见 `migration-upgrade-result.json`。

## 3. Dashboard 复现

在 `/workspace/repos/saleor-dashboard` 使用既有本地依赖：

```bash
export npm_config_cache=/workspace/scratch/npm
export COREPACK_HOME=/workspace/scratch/corepack
export TMPDIR=/workspace/scratch
export NODE_COMPILE_CACHE=/workspace/scratch/node-compile-cache
export JITI_CACHE_DIR=/workspace/scratch/jiti

npm run check-types
npm run test:quiet -- --runInBand --cacheDirectory=/workspace/scratch/jest \
  src/auth/views/Login.test.tsx \
  src/auth/views/NewPassword.test.tsx \
  src/auth/views/ResetPassword.test.tsx \
  src/hooks/useForm/configurationEditing.test.tsx \
  src/hooks/useHandleFormSubmit.test.ts \
  src/auth/components/LoginPage/LoginPage.test.tsx \
  src/auth/components/PasswordPolicyGate.test.tsx \
  src/channels/completionSettings.test.ts \
  src/channels/views/ChannelDetails/useChannelWarehousesReorder.test.ts \
  src/utils/configurationMutation.test.ts \
  src/components/Datagrid/hooks/useRowAnchor.test.tsx \
  src/components/Datagrid/hooks/useRowAnchorHandler.test.ts
```

已执行 `npm run generate`、`npm run extract-messages`；这两项会生成源码文件，复现后应检查 diff。全量 ESLint 和 `npm run knip` 本轮未通过，不应把它们与其他命令串联后只报告最后一个成功退出码；应独立记录退出状态。不要因 Sentry 未授权警告添加真实 token 或启动上传。

隔离 bundle 使用 `/workspace/scratch/dashboard-build.mjs`，基于仓库实际 Vite 配置，剔除 `sentry-*`、`copy-og-image`、`copy-noop-sw`、`code-inspector-plugin`；缓存与输出目录均在 scratch。以本地 API_URL、APP_MOUNT_URI=/、SKIP_SOURCEMAPS=true、Node heap 8192 MiB 执行。产物为 `/workspace/scratch/dashboard-build`，不代表标准发布构建或部署完成。

## 4. 版本、安全与验收限制

- 仓库 source manifest、working-tree status、tracked diff stat、`snapshot-audit.json` 位于上级目录。source SHA256 是 tracked + nonignored untracked 文件的内容标识，不是运行器快照 hash；ignored 依赖、缓存、构建产物不参与。
- 最终实际导出、Core checked-in SDL、Dashboard SDL 的 SHA256 均为 `440e9e87f24dc0f7cb053a287a92d74db730dea2e6e437e3ae777f8050ad58aa`。这只是前后端当前接口一致，不是目标 SDL 已实现。
- SDL 差异采用 GraphQL AST 静态比较：名称、kind、字段类型、参数/默认值、是否 deprecated、枚举值；忽略描述和声明顺序，不验证 resolver、全部 directive 语义或弃用说明正文。缺失 type 不展开重复计算其字段。
- 快照检查为有限文件名/正则和外部符号链接检查。两个测试 key 命中已与 HEAD 基线逐块比较，结果相同；没有将私钥正文、隔离的 `.jwt_key.pem` 或 provider 响应录制复制到本目录。不能据此声称完成全部凭据/安全审计。
- 两组后端通过数分别为 1377 与 391，不叠加中途重跑、43 子集等重复测试。旧 EditorJS 9 项失败单列。所有这些都是开发自测，不是冻结 TC001—TC260 的逐条执行记录。
- 未执行 E2E、全仓测试、真实 OIDC/PSP/Webhook 联调、生产数据审计或部署。完整发布阻断项以主报告为准。
