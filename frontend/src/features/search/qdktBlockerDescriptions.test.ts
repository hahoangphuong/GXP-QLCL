import { describe, expect, it } from "vitest";
import { describeQdKtBlocker } from "./qdktBlockerDescriptions";

describe("QĐKT blocker descriptions", () => {
  it("keeps the original backend blocker for troubleshooting", () => {
    const item = describeQdKtBlocker("QDKT_TYPED_RENDER_CONTRACT_MISSING");
    expect(item.code).toBe("QDKT_TYPED_RENDER_CONTRACT_MISSING");
    expect(item.title).toContain("DOCX");
    expect(item.next).toContain("#74");
  });

  it("does not guess unknown blocker semantics", () => {
    const item = describeQdKtBlocker("UNRECOGNIZED_SOURCE_GATE");
    expect(item.code).toBe("UNRECOGNIZED_SOURCE_GATE");
    expect(item.title).toContain("chưa được xác minh");
    expect(item.next).toContain("backend");
  });

  it("distinguishes site and decision provenance", () => {
    expect(describeQdKtBlocker("LEGACY_PROVINCE_MAPPING_UNPROVEN").title).toContain("tỉnh");
    expect(describeQdKtBlocker("SOURCE_DECISION_CARDINALITY_UNPROVEN").title).toContain("quyết định");
  });
});
