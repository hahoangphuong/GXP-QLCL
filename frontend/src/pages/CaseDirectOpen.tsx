import { useEffect, useMemo, useState } from "react";
import { Link, Navigate, useLocation, useParams, useSearchParams } from "react-router-dom";
import type { ApiAccess } from "../App";
import { getCaseWorkspace } from "../lib/api";
import type { CaseWorkspace } from "../types";
import { caseWorkflowQueue, type CaseWorkflowQueue } from "../features/search/caseNavigation";
import { resolveDocumentWorkspace } from "../features/documents/documentNavigation";
import { caseReportReturn } from "../features/reports/caseReportUrl";

type Resolved = { owner: object; location: string | null; error: string | null };

function caseSearchLocation(caseId: string, workspace: CaseWorkspace, queue: CaseWorkflowQueue | null, documentKey: string | null, sourceCertificate: { id: string; siteId: string } | null): string {
  const summary = workspace.case_summary;
  const present = (value: unknown): value is string => typeof value === "string" && value.length > 0 && value === value.trim();
  if (!summary || summary.id !== caseId || !present(summary.site_id) || !present(summary.gxp_type)) {
    throw new Error("Hồ sơ trả về không khớp định danh hoặc thiếu ngữ cảnh.");
  }
  if (sourceCertificate) {
    // The URL is only a navigation hint. A Case must independently confirm
    // the exact linked Certificate and Site before becoming a workspace target.
    const linked = workspace.linked_gxp_certificates;
    if (summary.site_id !== sourceCertificate.siteId || !Array.isArray(linked)
      || !linked.some(item => item.certificate_id === sourceCertificate.id
        && item.site_id === sourceCertificate.siteId
        && item.case_id === caseId && item.certificate_type === summary.gxp_type)) {
      throw new Error("Case không khớp chứng nhận và Site canonical được liên kết.");
    }
  }
  const line = summary.production_line_id;
  const code = summary.production_line_code;
  if ((line !== null && !present(line)) || (code !== null && !present(code))
    || (summary.production_line_identity_state === "canonical" && !present(line))
    || (summary.production_line_identity_state === "legacy_unlinked" && (line !== null || !present(code)))
    || (summary.production_line_identity_state === "facility_wide" && (line !== null || code !== null))
    || !["canonical", "legacy_unlinked", "facility_wide"].includes(summary.production_line_identity_state)) {
    throw new Error("Ngữ cảnh dây chuyền của hồ sơ không nhất quán.");
  }
  const params = new URLSearchParams({
    site_id: summary.site_id,
    gxp_type: summary.gxp_type,
    context_gxp: summary.gxp_type,
    history_id: caseId,
  });
  if (summary.production_line_id) params.set("production_line_id", summary.production_line_id);
  if (summary.production_line_code) params.set("line_code", summary.production_line_code);
  const documentTarget = documentKey ? resolveDocumentWorkspace(workspace, caseId, documentKey) : null;
  if (documentTarget) {
    params.set("document_key", documentTarget.checklist_key);
    params.set("document_id", documentTarget.document_id ?? "");
    params.set("document_parent_scope", documentTarget.parent_scope);
    params.set("document_parent_id", documentTarget.parent_id);
  }
  if (queue) params.set("return_queue", queue);
  // A verified Certificate-origin navigation opens its Case at the relevant
  // Certificate tab, without treating that hint as a mutation/readiness grant.
  if (sourceCertificate && !documentKey) params.set("event_tab", "Chứng nhận GxP");
  if (queue && !documentKey && !sourceCertificate) {
    // The Case state comes from the authorized workspace, never the queue projection.
    if (["planned", "decision_issued", "inspection_in_progress"].includes(summary.state)) {
      params.set("event_tab", "Kiểm tra");
    } else if (summary.state === "awaiting_certificate_decision"
      && workspace.certificate_issue_readiness?.action_key === "issue_certificate"
      && workspace.certificate_issue_readiness.available === true
      && workspace.certificate_issue_readiness.certificate_type === summary.gxp_type
      && Array.isArray(workspace.inspection?.approval_actions)
      && Array.isArray(workspace.remediation?.actions)
      && Array.isArray(workspace.transition_actions)
      && !workspace.inspection.approval_actions.some(action => action.available)
      && !workspace.remediation.actions.some(action => action.available)
      && !workspace.transition_actions.some(action => action.available)) {
      // Only suggest this tab when the backend says issue is available and
      // no other known workflow action competes. The tab still owns all writes.
      params.set("event_tab", "Chứng nhận GxP");
    }
  }
  return "/search?" + params;
}

/** Resolve a Case UUID from the backend before handing it to the editing workspace. */
export function CaseDirectOpen({ access }: { access: ApiAccess }) {
  const { caseId } = useParams();
  const location = useLocation();
  const [params] = useSearchParams();
  const queue = caseWorkflowQueue(params.get("return_queue"));
  const returnHint = caseReportReturn(location.state);
  const reportReturn = returnHint?.startsWith("/workflow?") && new URLSearchParams(returnHint.slice("/workflow?".length)).get("queue") !== queue ? null : returnHint;
  const documentKey = params.get("document_key");
  const sourceCertificateId = params.get("source_certificate_id");
  const sourceSiteId = params.get("source_site_id");
  const hasSourceHint = params.has("source_certificate_id") || params.has("source_site_id");
  const validSourceHint = !hasSourceHint || (params.getAll("source_certificate_id").length === 1
    && params.getAll("source_site_id").length === 1 && Boolean(sourceCertificateId?.trim())
    && Boolean(sourceSiteId?.trim()) && sourceCertificateId === sourceCertificateId?.trim()
    && sourceSiteId === sourceSiteId?.trim());
  const sourceCertificate = validSourceHint && sourceCertificateId && sourceSiteId
    ? { id: sourceCertificateId, siteId: sourceSiteId } : null;
  const { auth, bearerToken, useStubAuth, canLoadSecureApi, accessGeneration } = access;
  const owner = useMemo(() => ({}), [caseId, queue, documentKey, sourceCertificateId, sourceSiteId, validSourceHint, auth, bearerToken, useStubAuth, canLoadSecureApi, accessGeneration]);
  const [result, setResult] = useState<Resolved | null>(null);
  const current = result?.owner === owner ? result : null;

  useEffect(() => {
    if (!canLoadSecureApi || !caseId || !validSourceHint) return;
    let live = true;
    void (async () => {
      try {
        const workspace = await getCaseWorkspace(caseId, auth, useStubAuth, bearerToken);
        if (!live) return;
        const location = caseSearchLocation(caseId, workspace, queue, documentKey, sourceCertificate);
        setResult({ owner, location, error: null });
      } catch (error) {
        if (live) setResult({ owner, location: null, error: error instanceof Error ? error.message : "Không mở được hồ sơ." });
      }
    })();
    return () => { live = false; };
  }, [owner, caseId, queue, documentKey, sourceCertificateId, sourceSiteId, validSourceHint, auth, bearerToken, useStubAuth, canLoadSecureApi]);

  if (!canLoadSecureApi) return <section className="page-section"><h2>Cần đăng nhập</h2><p>Đăng nhập để mở hồ sơ được phân quyền.</p></section>;
  if (!caseId) return <p>Thiếu Case UUID.</p>;
  if (!validSourceHint) return <p role="alert">Tham số Certificate/Site liên kết không hợp lệ.</p>;
  if (current?.location) return <Navigate to={current.location} replace state={reportReturn ? { caseReportReturn: reportReturn, caseReportCaseId: caseId } : undefined} />;
  return <section className="page-section">
    <h2>Định vị hồ sơ</h2>
    {current?.error ? <p role="alert">{current.error}</p> : <p role="status">Đang xác minh Case UUID và ngữ cảnh cơ sở...</p>}
    <Link className="text-link" to={queue ? `/workflow?queue=${queue}` : "/workflow"}>Quay lại Bàn công việc</Link>
  </section>;
}
