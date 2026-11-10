import { CaseFieldMutationRecoveryError } from "./caseFieldMutationRecovery";

/**
 * Classify an ambiguous write to a business-eligibility Certificate aggregate.
 * An accepted POST cannot be declared rejected merely because canonical GET
 * failed; an unknown transport/5xx result cannot be retried blindly.
 */
export function raiseBusinessEligibilityWriteFailure(
  error: unknown,
  mutationAccepted: boolean,
  operation: "version" | "promotion",
): never {
  const status = (error as { status?: number } | null)?.status;
  if (mutationAccepted || status === undefined || status >= 500) {
    const action = operation === "version" ? "cập nhật phiên bản" : "đặt hiện hành";
    throw new CaseFieldMutationRecoveryError(
      `Chưa thể xác minh kết quả ${action} GCN đủ điều kiện. Không gửi lại; đối chiếu bản ghi canonical trước khi thao tác tiếp.`,
      { cause: error },
    );
  }
  throw error;
}
