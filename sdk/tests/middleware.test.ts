import { describe, it, expect, beforeEach } from "vitest";
import { PrivPortalMiddleware } from "../src/middleware.js";

const TEST_DATA = {
  identities: [
    { key: "identity.student.name", value: "张三", project_id: null },
    {
      key: "identity.student.email",
      value: "zhangsan@example.com",
      project_id: null,
    },
    { key: "identity.teacher.name", value: "李老师", project_id: null },
    { key: "identity.student.fullname", value: "张三丰", project_id: null },
  ],
  secrets: [{ key: "secret.openai.default.api_key", project_id: null }],
  version: "1",
};

describe("PrivPortalMiddleware", () => {
  let mw: PrivPortalMiddleware;

  beforeEach(() => {
    mw = new PrivPortalMiddleware();
    mw.loadFromObject(TEST_DATA);
  });

  describe("sanitize", () => {
    it("replaces known values with placeholders", () => {
      const result = mw.sanitize("你好，我是张三");
      expect(result).not.toContain("张三");
      expect(result).toContain("[[identity.student.name]]");
    });

    it("replaces multiple values", () => {
      const result = mw.sanitize("张三的邮箱是zhangsan@example.com");
      expect(result).not.toContain("张三");
      expect(result).not.toContain("zhangsan@example.com");
      expect(result).toContain("[[identity.student.name]]");
      expect(result).toContain("[[identity.student.email]]");
    });

    it("passes through unknown text", () => {
      expect(mw.sanitize("今天天气不错")).toBe("今天天气不错");
    });

    it("longer values match first", () => {
      const result = mw.sanitize("张三丰是太极拳的创始人");
      expect(result).toContain("[[identity.student.fullname]]");
      expect(result).not.toContain("张三丰");
    });

    it("returns empty string unchanged", () => {
      expect(mw.sanitize("")).toBe("");
    });

    it("returns text unchanged when not loaded", () => {
      const fresh = new PrivPortalMiddleware();
      expect(fresh.sanitize("张三")).toBe("张三");
    });
  });

  describe("resolve", () => {
    it("replaces placeholders with values", () => {
      expect(mw.resolve("[[identity.student.name]]你好")).toBe("张三你好");
    });

    it("resolves multiple placeholders", () => {
      const text =
        "[[identity.student.name]]的邮箱是[[identity.student.email]]";
      expect(mw.resolve(text)).toBe("张三的邮箱是zhangsan@example.com");
    });

    it("passes through unknown placeholders", () => {
      expect(mw.resolve("[[identity.unknown.field]]保持原样")).toBe(
        "[[identity.unknown.field]]保持原样"
      );
    });

    it("passes through text without placeholders", () => {
      expect(mw.resolve("普通文本")).toBe("普通文本");
    });
  });

  describe("roundtrip", () => {
    it("sanitize then resolve recovers original", () => {
      const original = "你好，我是张三，邮箱是zhangsan@example.com";
      const sanitized = mw.sanitize(original);
      expect(sanitized).not.toContain("张三");
      expect(sanitized).not.toContain("zhangsan@example.com");
      const resolved = mw.resolve(sanitized);
      expect(resolved).toBe(original);
    });

    it("handles mixed identities", () => {
      const original = "学生张三和老师李老师在讨论";
      const resolved = mw.resolve(mw.sanitize(original));
      expect(resolved).toBe(original);
    });
  });

  describe("detectLeaks", () => {
    it("finds known values in text", () => {
      const leaks = mw.detectLeaks("AI 回复了: 你好张三");
      expect(leaks.length).toBeGreaterThanOrEqual(1);
      expect(leaks.some((l) => l.value === "张三")).toBe(true);
    });

    it("returns empty for clean text", () => {
      expect(mw.detectLeaks("一切正常，没有隐私信息")).toEqual([]);
    });

    it("includes correct position", () => {
      const text = "hello张三world";
      const leaks = mw.detectLeaks(text);
      expect(leaks[0].position).toBe(5);
    });
  });

  describe("metadata", () => {
    it("reports counts", () => {
      expect(mw.identityCount).toBe(4);
      expect(mw.secretCount).toBe(1);
    });

    it("reports loaded state", () => {
      expect(mw.isLoaded).toBe(true);
      expect(new PrivPortalMiddleware().isLoaded).toBe(false);
    });

    it("toString includes key info", () => {
      const s = mw.toString();
      expect(s).toContain("loaded=true");
      expect(s).toContain("identities=4");
    });
  });

  describe("constructor options", () => {
    it("accepts string URL", () => {
      const m = new PrivPortalMiddleware("http://localhost:9999");
      expect(m.toString()).toContain("localhost:9999");
    });

    it("accepts options object", () => {
      const m = new PrivPortalMiddleware({
        baseUrl: "http://localhost:9999",
        projectId: "proj-1",
      });
      expect(m.toString()).toContain("localhost:9999");
    });

    it("defaults to localhost:12790", () => {
      const m = new PrivPortalMiddleware();
      expect(m.toString()).toContain("127.0.0.1:12790");
    });
  });
});
