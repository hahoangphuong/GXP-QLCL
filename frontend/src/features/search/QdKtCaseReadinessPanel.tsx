import { useEffect, useState } from "react";
import { describeQdKtBlocker } from "./qdktBlockerDescriptions";
import { getCaseQdKtCurrentTeam, getCaseQdKtReadiness, type QdKtCurrentTeam, type QdKtReadiness } from "../../lib/api";
import type { StubAuthState } from "../../types";

type View = { status: "loading" } | { status: "ready"; readiness: QdKtReadiness; team: QdKtCurrentTeam | null; teamError: string | null } | { status: "error"; message: string };

function QdKtCaseReadinessContent({
  caseId, auth, useStubAuth, bearerToken, accessGeneration, retryGeneration, onRetry,
}: {
  caseId: string;
  auth: StubAuthState;
  useStubAuth: boolean;
  bearerToken: string | null;
  accessGeneration: number;
  retryGeneration: number;
  onRetry: () => void;
}) {
  const [view, setView] = useState<View>({ status: "loading" });
  useEffect(() => {
    const controller = new AbortController();
    setView({ status: "loading" });
    getCaseQdKtReadiness(caseId, auth, useStubAuth, bearerToken, controller.signal, "DRAFT_QDKT")
      .then(async readiness => {
        if (controller.signal.aborted) return;
        // Fail closed: a read-only panel must not imply that creating a QĐKT is allowed.
        if (readiness.case_id !== caseId || readiness.family_code !== "INSPECTION_QD_KT"
            || readiness.ready_to_render !== false || readiness.decision_source_id !== null
            || !Array.isArray(readiness.blocked_reasons)) {
          throw new Error("Dữ liệu readiness QĐKT không hợp lệ hoặc sai hồ sơ.");
        }
        let team: QdKtCurrentTeam | null = null;
        let teamError: string | null = null;
        try {
          const result = await getCaseQdKtCurrentTeam(caseId, auth, useStubAuth, bearerToken, controller.signal);
          if (result.case_id !== caseId || result.source_kind !== "CURRENT_CASE_TEAM"
              || result.draft_snapshot_available !== false || result.issued_team_confirmed !== false) {
            throw new Error("Nguồn đoàn kiểm tra không đúng ngữ cảnh.");
          }
          team = result;
        } catch (error) {
          if (controller.signal.aborted) return;
          teamError = error instanceof Error ? error.message : "Chưa đọc được đoàn kiểm tra hiện tại.";
        }
        if (!controller.signal.aborted) setView({ status: "ready", readiness, team, teamError });
      })
      .catch(error => {
        if (!controller.signal.aborted) setView({
          status: "error",
          message: error instanceof Error ? error.message : "Không đọc được trạng thái QĐKT.",
        });
      });
    return () => controller.abort();
  }, [caseId, auth, useStubAuth, bearerToken, accessGeneration, retryGeneration]);

  return (
    <section aria-label="Trạng thái dự thảo QĐKT" className="facility-detail-section">
      <h3>Quyết định kiểm tra (QĐKT)</h3>
      <p>Chưa cho phép tạo dự thảo QĐKT từ hồ sơ này. Việc ghi nhận QĐKT đã phê duyệt là bước nghiệp vụ riêng.</p>
      {view.status === "loading" ? <p role="status">Đang kiểm tra điều kiện QĐKT…</p> : null}
      {view.status === "error" ? (
        <div>
          <p role="alert">{view.message}</p>
          <button type="button" className="secondary" onClick={onRetry}>Thử kiểm tra lại QĐKT</button>
        </div>
      ) : null}
      {view.status === "ready" ? (
        <>
          <p>Trạng thái tạo dự thảo: Chưa sẵn sàng.</p>
          <p>Lý do từ backend:</p>
          {view.readiness.blocked_reasons.length
            ? <ul>{view.readiness.blocked_reasons.map(reason => {
                const blocker = describeQdKtBlocker(reason);
                return <li key={reason}><strong>{blocker.title}</strong> {blocker.next} <code>{blocker.code}</code></li>;
              })}</ul>
            : <p>Chưa có đủ bằng chứng cho phép tạo tài liệu.</p>}
          {view.readiness.decision_source_id ? <p>Nguồn quyết định: <code>{view.readiness.decision_source_id}</code></p> : null}
          {view.readiness.registered_site_id ? <p>Cơ sở đăng ký: <code>{view.readiness.registered_site_id}</code></p> : null}
          <p>Đây là kiểm tra điều kiện chuẩn bị dự thảo; không phải QĐKT đã ban hành.</p>
          {view.team ? (
            <>
              <p>Đoàn hiện tại của Case (revision {view.team.team_revision}) — <strong>chưa phải đoàn trong dự thảo hoặc đoàn đã ban hành</strong>.</p>
              <ol>{[...view.team.members].sort((a, b) => a.sort_order - b.sort_order).map(member =>
                <li key={member.member_id}>{member.display_name} — {member.role_code}</li>)}</ol>
            </>
          ) : <p role="status">Đoàn hiện tại: {view.teamError ?? "Chưa có dữ liệu."}</p>}
        </>
      ) : null}
    </section>
  );
}

export function QdKtCaseReadinessPanel(props: {
  caseId: string;
  auth: StubAuthState;
  useStubAuth: boolean;
  bearerToken: string | null;
  accessGeneration: number;
}) {
  const [expanded, setExpanded] = useState(false);
  const [retryGeneration, setRetryGeneration] = useState(0);
  return (
    <div className="qdkt-readiness-disclosure">
      <button
        type="button"
        className="secondary"
        aria-expanded={expanded}
        onClick={() => setExpanded(value => !value)}
      >
        {expanded ? "Ẩn trạng thái QĐKT" : "Xem trạng thái QĐKT"}
      </button>
      {expanded ? (
        <QdKtCaseReadinessContent
          {...props}
          retryGeneration={retryGeneration}
          onRetry={() => setRetryGeneration(value => value + 1)}
        />
      ) : null}
    </div>
  );
}
