import js from "@eslint/js";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "node_modules"] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
    },
  },
  {
    // Query keys come from one module so a prefix invalidation can reach every
    // subtree (agents/frontend.md §3). An inline `queryKey: ["…", …]` at a call
    // site is the drift this rule stops; tests may still spell keys out.
    files: ["src/**/*.{ts,tsx}"],
    ignores: ["src/lib/api/queryKeys.ts", "src/**/*.test.{ts,tsx}"],
    rules: {
      "no-restricted-syntax": [
        "error",
        {
          selector: 'Property[key.name="queryKey"] > ArrayExpression > Literal:first-child',
          message:
            "Inline query keys are not allowed — import a key builder from src/lib/api/queryKeys.ts.",
        },
      ],
    },
  },
);
