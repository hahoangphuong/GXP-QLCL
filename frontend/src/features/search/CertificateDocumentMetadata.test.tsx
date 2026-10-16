import "@testing-library/jest-dom/vitest";
import { act, render, renderHook, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  getBusinessEligibilityDocumentMetadata,
  getGxpCertificateDocumentMetadata,
} from "../../lib/api";
import type { DocumentOwnerMetadataInventory } from "../../types";
import { CertificateDocumentMetadata } from "./CertificateDocumentMetadata";
import { useCertificateDocumentMetadata } from "./useCertificateDocumentMetadata";

vi.mock("../../lib/api", () => ({
  getBusinessEligibilityDocumentMetadata: vi.fn(),
  getGxpCertificateDocumentMetadata: vi.fn(),
}));

const loadGxp = vi.mocked(getGxpCertificateDocumentMetadata);
const loadDdk = vi.mocked(getBusinessEligibilityDocumentMetadata);
const auth = { username: "fixture.reader", role: "reader" as const };

function inventory(kind: "gxp" | "ddk", id = kind === "gxp" ? "gxp-a" : "ddk-a"): DocumentOwnerMetadataInventory {
  return {
    owner_kind: kind === "gxp" ? "certificate" : "business_eligibility_certificate",
    owner_id: id,
    metadata_status: "registered_metadata_only_unverified",
    binary_verified: false,
    original_signed_document_verified: false,
    documents: [{
      document_id: `${id}-document`, family_code: "certificate", document_type_code: "signed-certificate",
      title: `Metadata ${id}`, registered_variant_count: 2, registered_version_count: 3,
      registered_current_version_count: 1,
    }],
  };
}

afterEach(() => vi.resetAllMocks());

describe("certificate document metadata presentation", () => {
  it("presents registered metadata as unverified and exposes no content or storage action", () => {
    render(<CertificateDocumentMetadata state={{ status: "ready", data: inventory("gxp") }} />);
    expect(screen.getByRole("region", { name: "Tài liệu đã đăng ký" })).toHaveTextContent("Metadata gxp-a");
    expect(screen.getByText(/chưa xác minh tệp nhị phân hoặc bản gốc có chữ ký/i)).toBeInTheDocument();
    expect(screen.getByRole("table")).toHaveTextContent("2");
    expect(screen.getByRole("table")).toHaveTextContent("3");
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(document.body).not.toHaveTextContent(/filename|NAS|checksum|\\\\/i);
  });

  it("states that an empty registry does not prove the original is absent", () => {
    render(<CertificateDocumentMetadata state={{ status: "ready", data: {
      ...inventory("ddk"), metadata_status: "no_registered_document_metadata", documents: [],
    } }} />);
    expect(screen.getByRole("status")).toHaveTextContent("không xác nhận tài liệu gốc có hay không");
  });

  it.each([401, 403, 404, 409, 503, null])("maps HTTP %s without retry controls", httpStatus => {
    render(<CertificateDocumentMetadata state={{ status: "error", httpStatus }} />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    if (httpStatus === 409) expect(screen.getByRole("alert")).toHaveTextContent("chủ sở hữu");
  });
});

describe("access-bound certificate document metadata ownership", () => {
  it("uses independent GxP and ĐĐK endpoints for the exact canonical owner", async () => {
    loadGxp.mockResolvedValue(inventory("gxp"));
    loadDdk.mockResolvedValue(inventory("ddk"));
    const { result, rerender } = renderHook(({ kind, id, context }) =>
      useCertificateDocumentMetadata(kind, context, id, auth, false, "token"), {
        initialProps: { kind: "gxp" as "gxp" | "ddk", id: "gxp-a", context: "site-a/access-1" },
      });
    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(loadGxp).toHaveBeenCalledWith("gxp-a", auth, false, "token", expect.any(AbortSignal));
    rerender({ kind: "ddk", id: "ddk-a", context: "site-a/access-1" });
    expect(result.current.status).toBe("loading");
    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(loadDdk).toHaveBeenCalledWith("ddk-a", auth, false, "token", expect.any(AbortSignal));
  });

  it("aborts A, hides it immediately in B, and rejects reversed late success and errors", async () => {
    let resolveA!: (value: DocumentOwnerMetadataInventory) => void;
    loadGxp.mockImplementationOnce(() => new Promise(resolve => { resolveA = resolve; }))
      .mockResolvedValueOnce(inventory("gxp", "gxp-b"));
    const { result, rerender } = renderHook(({ id, context }) =>
      useCertificateDocumentMetadata("gxp", context, id, auth, false, "token"), {
        initialProps: { id: "gxp-a", context: "site-a/access-1" },
      });
    const oldSignal = loadGxp.mock.calls[0][4]!;
    rerender({ id: "gxp-b", context: "site-a/access-1" });
    expect(result.current.status).toBe("loading");
    expect(oldSignal.aborted).toBe(true);
    await waitFor(() => expect(result.current).toEqual({ status: "ready", data: inventory("gxp", "gxp-b") }));
    await act(async () => resolveA(inventory("gxp", "gxp-a")));
    expect(result.current).toEqual({ status: "ready", data: inventory("gxp", "gxp-b") });
  });

  it("owns an A → B → A return by operation generation rather than the repeated UUID", async () => {
    let resolveOldA!: (value: DocumentOwnerMetadataInventory) => void;
    loadGxp.mockImplementationOnce(() => new Promise(resolve => { resolveOldA = resolve; }))
      .mockResolvedValueOnce(inventory("gxp", "gxp-b"))
      .mockResolvedValueOnce({ ...inventory("gxp", "gxp-a"), documents: [{ ...inventory("gxp", "gxp-a").documents[0], title: "New A" }] });
    const { result, rerender } = renderHook(({ id }) =>
      useCertificateDocumentMetadata("gxp", "site/access", id, auth, false, null), { initialProps: { id: "gxp-a" } });
    rerender({ id: "gxp-b" });
    rerender({ id: "gxp-a" });
    await waitFor(() => expect(result.current.status === "ready" && result.current.data.documents[0].title).toBe("New A"));
    await act(async () => resolveOldA(inventory("gxp", "gxp-a")));
    expect(result.current.status === "ready" && result.current.data.documents[0].title).toBe("New A");
  });

  it.each([403, 404, 409])("ignores late A HTTP %s after B is current", async httpStatus => {
    let rejectA!: (reason: Error) => void;
    loadDdk.mockImplementationOnce(() => new Promise((_, reject) => { rejectA = reject; }))
      .mockResolvedValueOnce(inventory("ddk", "ddk-b"));
    const { result, rerender } = renderHook(({ id }) =>
      useCertificateDocumentMetadata("ddk", "site/access", id, auth, false, null), { initialProps: { id: "ddk-a" } });
    rerender({ id: "ddk-b" });
    await waitFor(() => expect(result.current).toEqual({ status: "ready", data: inventory("ddk", "ddk-b") }));
    await act(async () => rejectA(Object.assign(new Error("old owner"), { status: httpStatus })));
    expect(result.current).toEqual({ status: "ready", data: inventory("ddk", "ddk-b") });
  });

  it("invalidates the old owner on site, principal and access-generation changes without focus duplicates", async () => {
    loadGxp.mockResolvedValue(inventory("gxp"));
    const { result, rerender } = renderHook(({ context, token, focus }) => {
      void focus;
      return useCertificateDocumentMetadata("gxp", context, "gxp-a", auth, false, token);
    }, { initialProps: { context: "site-a/access-1" as string | null, token: "session-a" as string | null, focus: 0 } });
    await waitFor(() => expect(result.current.status).toBe("ready"));
    rerender({ context: "site-a/access-1", token: "session-a", focus: 1 });
    expect(loadGxp).toHaveBeenCalledTimes(1);
    rerender({ context: "site-b/access-2", token: "session-b", focus: 1 });
    expect(result.current.status).toBe("loading");
    await waitFor(() => expect(loadGxp).toHaveBeenCalledTimes(2));
    rerender({ context: null, token: null, focus: 1 });
    expect(result.current).toEqual({ status: "idle" });
  });

  it.each([401, 403, 404, 409])("keeps HTTP %s local and performs no blind retry", async httpStatus => {
    loadDdk.mockRejectedValue(Object.assign(new Error("unavailable"), { status: httpStatus }));
    const { result } = renderHook(() => useCertificateDocumentMetadata("ddk", "site/access", "ddk-a", auth, false, null));
    await waitFor(() => expect(result.current).toEqual({ status: "error", httpStatus }));
    expect(loadDdk).toHaveBeenCalledTimes(1);
  });

  it("fails closed on mismatched owner, forbidden verification claims and malformed counts", async () => {
    loadGxp
      .mockResolvedValueOnce({ ...inventory("gxp", "other") })
      .mockResolvedValueOnce({ ...inventory("gxp"), binary_verified: true } as unknown as DocumentOwnerMetadataInventory)
      .mockResolvedValueOnce({ ...inventory("gxp"), documents: [{ ...inventory("gxp").documents[0], registered_version_count: -1 }] });
    const { result, rerender } = renderHook(({ context }) =>
      useCertificateDocumentMetadata("gxp", context, "gxp-a", auth, false, null), { initialProps: { context: "one" } });
    await waitFor(() => expect(result.current.status).toBe("error"));
    rerender({ context: "two" }); await waitFor(() => expect(loadGxp).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(result.current.status).toBe("error"));
    rerender({ context: "three" }); await waitFor(() => expect(loadGxp).toHaveBeenCalledTimes(3));
    await waitFor(() => expect(result.current.status).toBe("error"));
  });
});
