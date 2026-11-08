import { CaseFieldMutationRecoveryError } from "./caseFieldMutationRecovery";

/**
 * An accepted version write followed by an unreadable canonical Certificate,
 * an unknown transport result, or an HTTP 5xx must never be treated as an
 * ordinary rejected edit. The operator must reconcile the persisted version
 * before another write is permitted.
 */
function raiseGxpCertificateMutationFailure(error: unknown, mutationAccepted: boolean, message: string): never {
  const status = (error as { status?: number } | null)?.status;
  if (mutationAccepted || status === undefined || status >= 500) {
    throw new CaseFieldMutationRecoveryError(message, { cause: error });
  }
  throw error;
}

export function raiseGxpCertificateVersionWriteFailure(error: unknown, mutationAccepted: boolean): never {
  return raiseGxpCertificateMutationFailure(
    error, mutationAccepted,
    "Chưa thể xác minh kết quả cập nhật chứng nhận. Không gửi lại; giữ bản nháp và kiểm tra dữ liệu canonical.",
  );
}

export function raiseGxpCertificatePromotionFailure(error: unknown, mutationAccepted: boolean): never {
  return raiseGxpCertificateMutationFailure(
    error, mutationAccepted,
    "Chưa thể xác minh kết quả đặt chứng nhận hiện hành. Không gửi lại; tải lại Certificate canonical để đối chiếu.",
  );
}
