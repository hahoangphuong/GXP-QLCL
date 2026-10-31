export class CaseFieldMutationRecoveryError extends Error {}

// Commands cannot substitute for an authoritative workspace readback.
export async function runCaseFieldMutation(write: () => Promise<unknown>, readback: () => Promise<unknown>) {
  try {
    await write();
  } catch (error) {
    const status = (error as { status?: number } | null)?.status;
    if (status === undefined || status >= 500) {
      throw new CaseFieldMutationRecoveryError("Chưa xác định kết quả lưu. Không gửi lại; sao chép bản nháp rồi tải lại hồ sơ để xác minh.", { cause: error });
    }
    throw error;
  }
  try {
    if (await readback() === null) throw new Error("Ngữ cảnh xác minh đã thay đổi.");
  } catch (error) {
    throw new CaseFieldMutationRecoveryError(`Máy chủ đã nhận thao tác nhưng không tải lại được workspace. Không gửi lại; sao chép bản nháp rồi tải lại hồ sơ để xác minh. ${error instanceof Error ? error.message : ""}`, { cause: error });
  }
}
