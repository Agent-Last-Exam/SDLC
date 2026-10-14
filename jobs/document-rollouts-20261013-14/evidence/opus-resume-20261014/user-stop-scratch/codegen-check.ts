import { CodegenConfig } from "@graphql-codegen/cli";

const config: CodegenConfig = {
  schema: "/workspace/repos/saleor-dashboard/schema.graphql",
  documents: [
    "/workspace/repos/saleor-dashboard/src/**/queries.ts",
    "/workspace/repos/saleor-dashboard/src/**/mutations.ts",
    "/workspace/repos/saleor-dashboard/src/**/fragments/*.ts",
    "/workspace/repos/saleor-dashboard/src/searches/*.ts",
  ],
  generates: {
    "/workspace/scratch/gen/fragmentTypes.generated.ts": {
      plugins: ["fragment-matcher"],
      config: {
        minify: false,
        apolloClientVersion: 3,
      },
    },
    "/workspace/scratch/gen/typePolicies.generated.ts": {
      plugins: ["typescript-apollo-client-helpers"],
    },
    "/workspace/scratch/gen/types.generated.ts": {
      plugins: ["typescript", "typescript-operations"],
      config: {
        nonOptionalTypename: true,
        avoidOptionals: {
          field: true,
          inputValue: false,
          object: false,
          defaultValue: false,
        },
        namingConvention: {
          enumValues: "change-case-all#upperCase",
        },
        onlyOperationTypes: true,
      },
    },
    "/workspace/scratch/gen/hooks.generated.ts": {
      plugins: ["typescript-react-apollo"],
      config: {
        withHooks: true,
        apolloReactHooksImportFrom: "@dashboard/hooks/graphql",
      },
      preset: "import-types",
      presetConfig: {
        typesPath: "./types.generated",
      },
    },
  },
};

export default config;
