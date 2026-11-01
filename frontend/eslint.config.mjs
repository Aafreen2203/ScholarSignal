import { defineConfig, globalIgnores } from "eslint/config";
import tseslint from "typescript-eslint";
import nextPlugin from "@next/eslint-plugin-next";

export default defineConfig([
  ...tseslint.configs.recommended,
  {
    plugins: { "@next/next": nextPlugin },
    rules: {
      "@next/next/no-html-link-for-pages": "error",
      "@next/next/no-img-element": "warn",
    },
  },
  globalIgnores([".next/**", "node_modules/**"]),
]);

