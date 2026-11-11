import { createContext } from "react";
import type { InspectionApprovalSubmissionCreateRequest, InspectionApprovalSubmissionCompleteRequest } from "../../types";

// Exact immutable request as accepted by the HTTP mutation owner. This is
// in-session evidence of what was sent, not proof of a committed submission.
export type ApprovalSubmittedCommand =
  | { kind: "create"; caseId: string; stage: "PCT" | "CT"; request: InspectionApprovalSubmissionCreateRequest }
  | { kind: "complete"; caseId: string; submissionId: string; request: InspectionApprovalSubmissionCompleteRequest };

export const ApprovalMutationContext = createContext<{
  pending: boolean;
  requiresReview: boolean;
  submitted?: ApprovalSubmittedCommand;
}>({ pending: false, requiresReview: false });

export class ApprovalMutationRecoveryError extends Error {}

// A successful command response is not canonical workspace confirmation.
export async function runApprovalMutation<T>(write: () => Promise<T>, readback: () => Promise<unknown>): Promise<T> {
  let response: T;
  try {
    response = await write();
  } catch (error) {
    const status = (error as { status?: number } | null)?.status;
    if (status === undefined || status >= 500) {
      throw new ApprovalMutationRecoveryError("Không xác định được kết quả ghi trình phê duyệt. Không gửi lại trước khi tải lại hồ sơ để xác minh.", { cause: error });
    }
    throw error;
  }
  try {
    if (await readback() === null) throw new Error("Ngữ cảnh xác minh đã thay đổi.");
  } catch (error) {
    throw new ApprovalMutationRecoveryError(`Máy chủ đã chấp nhận thao tác nhưng chưa xác minh được hồ sơ. ${error instanceof Error ? error.message : "Không tải được hồ sơ."}`, { cause: error });
  }
  return response;
}
