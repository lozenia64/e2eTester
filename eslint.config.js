import tseslint from "@typescript-eslint/eslint-plugin";
import tsparser from "@typescript-eslint/parser";

export default [
  // ignores 만 있는 별도 객체 — ESLint flat config 에서 이것이 "global ignores"로
  // 취급되어 해당 파일을 전 과정(파싱 포함)에서 제외한다.
  // files 와 같은 객체에 ignores 를 두면 "이 객체의 규칙만 스킵"이라는 뜻이 되어,
  // 매칭되는 다른 객체가 없는 경우 파서 지정 없이 기본 파싱을 시도하다 TS 구문에서
  // 파싱 에러가 난다(status.generated.ts 로 실측 확인).
  { ignores: ["app/web/frontend/**/*.generated.ts"] },
  {
    files: ["app/web/frontend/**/*.ts"],
    languageOptions: { parser: tsparser, ecmaVersion: 2022, sourceType: "module" },
    plugins: { "@typescript-eslint": tseslint },
    rules: {
      "@typescript-eslint/no-unused-vars": "error",
      "@typescript-eslint/no-explicit-any": "error",
      eqeqeq: "error",
      "no-console": ["error", { allow: ["warn", "error"] }],
    },
  },
];
