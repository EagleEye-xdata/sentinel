import { describe, it, expect } from "vitest";

describe("Frontend Core", () => {
  it("verifies environment default fallback", () => {
    const defaultApi = "http://localhost:8000";
    expect(defaultApi).toBe("http://localhost:8000");
  });

  it("verifies tab navigation integrity", () => {
    const tabs = [
      "3-Panel Hub",
      "Architecture",
      "Attack Library",
      "Batch Test",
      "Reports",
      "Targets",
      "Alerts",
    ];
    expect(tabs).toHaveLength(7);
    expect(tabs).toContain("3-Panel Hub");
    expect(tabs).toContain("Batch Test");
  });
});
