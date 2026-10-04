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
    // subtree (.agents/frontend.md §3). An inline `queryKey: ["…", …]` at a call
    // site is the drift this rule stops; tests may still spell keys out.
    files: ["src/**/*.{ts,tsx}"],
    ignores: [
      "src/lib/api/queryKeys.ts",
      "src/lib/api/queryKeys.capabilities.ts",
      "src/**/*.test.{ts,tsx}",
    ],
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
  {
    // Layering (.agents/frontend.md §2): pages -> components -> lib, never back up.
    // `lib` may not import components or pages. The one exception is `useToast`
    // (components/ui/toast): a UI primitive hook that the mutation hooks need.
    files: ["src/lib/**/*.{ts,tsx}"],
    ignores: ["src/**/*.test.{ts,tsx}"],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          patterns: [
            {
              regex: "^@/components/(?!ui/toast$)",
              message:
                "src/lib must not import from src/components — move the shared type or helper down into lib (only useToast from components/ui/toast is allowed).",
            },
            {
              // Relative paths into components (`../../components/...`).
              regex: "^\\.{1,2}/(.*/)?components/",
              message: "src/lib must not import from src/components.",
            },
            {
              regex: "^(@/pages/|\\.{1,2}/(.*/)?pages/)",
              message: "src/lib must not import from src/pages.",
            },
          ],
        },
      ],
    },
  },
  {
    // `components` may not import `pages`. Test files are exempt (a component
    // test may mount the page that hosts it); shared kits live under src/test/.
    files: ["src/components/**/*.{ts,tsx}"],
    ignores: ["src/**/*.test.{ts,tsx}"],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          patterns: [
            {
              regex: "^(@/pages/|\\.{1,2}/(.*/)?pages/)",
              message:
                "src/components must not import from src/pages — pages compose components, not the reverse.",
            },
          ],
        },
      ],
    },
  },
);
