import { expect, it } from "vitest";
import { escapeHtml } from "./html";

it("HTML 특수문자 다섯 개를 모두 이스케이프한다", () => {
  expect(escapeHtml(`<a href="x" title='y'>&</a>`)).toBe("&lt;a href=&quot;x&quot; title=&#39;y&#39;&gt;&amp;&lt;/a&gt;");
});
