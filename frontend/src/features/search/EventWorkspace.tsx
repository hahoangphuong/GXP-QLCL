import { useEffect, useMemo, useState, type ReactNode } from "react";

import { EmptyState } from "../../components/EmptyState";
import { StatusBadge } from "../../components/StatusBadge";
import { formatCompactDate, formatStatusLabel } from "../../lib/presentation";
import type {
  BusinessEligibilityDetail,
  CapaCycleAssessRequest,
  CapaCycleCreateRequest,
  CapaCycleSubmitRequest,
  CapaCycleUpdateRequest,
  CaseApplicationUpsertRequest,
  CaseAssessmentUpsertRequest,
  CaseWorkspace,
  ChangeRequestWorkspace,
  ContextualDocumentAction,
  DocumentChecklistItem,
  DocumentDetail,
  FacilityHistoryItem,
  GxpCertificateDetail,
  InspectionOutcomeUpsertRequest,
  InspectionPlanUpsertRequest,
  EvaluationScopeUpsertRequest,
} from "../../types";
import { BusinessEligibilityDetailFields } from "./BusinessEligibilityDetailFields";
import { CaseApplicationWorkspace } from "./CaseApplicationWorkspace";
import { CaseInspectionWorkspace } from "./CaseInspectionWorkspace";
import { CaseProcessingWorkspace } from "./CaseProcessingWorkspace";
import { CaseRemediationWorkspace } from "./CaseRemediationWorkspace";
import { DetailValue } from "./DetailValue";
import { GxpCertificateDetailFields } from "./GxpCertificateDetailFields";

const CASE_EVENT_TABS = ["Hồ sơ", "Kiểm tra", "Khắc phục", "Xử lý", "Chứng nhận GxP", "Chứng nhận ĐĐK"] as const;
const CHANGE_REQUEST_EVENT_TABS = ["Đề nghị", "Chi tiết", "Xử lý", "Tài liệu"] as const;

const DOCUMENT_STATUS_LABELS: Record<string, string> = {
  available: "Đã có tài liệu",
  missing: "Chưa có tài liệu",
};

const DOCUMENT_PARENT_SCOPE_LABELS: Record<string, string> = {
  case: "Hồ sơ",
  capa_cycle: "CAPA",
  change_request: "Thay đổi",
};

function WorkspaceSection({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="workspace-section">
      <h4>{title}</h4>
      {children}
    </section>
  );
}

function DocumentChecklistSection({
  items,
  emptyDescription,
}: {
  items: DocumentChecklistItem[];
  emptyDescription: string;
}) {
  if (items.length === 0) {
    return <EmptyState title="Chưa có checklist tài liệu" description={emptyDescription} />;
  }

  return (
    <div className="table-scroll table-scroll-history">
      <table className="dense-table event-document-table">
        <thead>
          <tr>
            <th>Loại tài liệu</th>
            <th>Phạm vi</th>
            <th>Trạng thái</th>
            <th>Tệp hiện có</th>
            <th>Ngày</th>
            <th>Định dạng</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.checklist_key}>
              <td title={item.family_code ?? ""}>
                <div className="cell-stack">
                  <strong>{item.label}</strong>
                  {item.title ? <span>{item.title}</span> : null}
                </div>
              </td>
              <td>{DOCUMENT_PARENT_SCOPE_LABELS[item.parent_scope] ?? item.parent_scope}</td>
              <td>{DOCUMENT_STATUS_LABELS[item.status] ?? item.status}</td>
              <td title={item.original_filename ?? ""}>{item.original_filename ?? "Chưa có"}</td>
              <td>{formatCompactDate(item.issued_on)}</td>
              <td>{item.available_variant_types.length > 0 ? item.available_variant_types.join(", ") : "Chưa có"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ContextualDocumentSection({
  items,
  onOpenDocument,
  onLoadDocumentDetail,
}: {
  items: ContextualDocumentAction[];
  onOpenDocument: (item: ContextualDocumentAction) => Promise<void>;
  onLoadDocumentDetail: (documentId: string) => Promise<DocumentDetail>;
}) {
  const [selectedDocumentId, setSelectedDocumentId] = useState<string | null>(null);
  const [detail, setDetail] = useState<DocumentDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingMessage, setLoadingMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [detailMode, setDetailMode] = useState<"open" | "history">("open");

  const currentItem = useMemo(
    () => items.find((item) => item.document_id === selectedDocumentId) ?? null,
    [items, selectedDocumentId],
  );

  useEffect(() => {
    if (!currentItem) {
      setDetail(null);
      setLoading(false);
      setLoadingMessage(null);
      setError(null);
    }
  }, [currentItem]);

  async function handleLoadHistory(item: ContextualDocumentAction) {
    if (!item.document_id) {
      return;
    }
    setSelectedDocumentId(item.document_id);
    setDetailMode("history");
    setDetail(null);
    setLoading(true);
    setLoadingMessage("Đang tải lịch sử tài liệu...");
    setError(null);
    try {
      const payload = await onLoadDocumentDetail(item.document_id);
      setDetail(payload);
    } catch (nextError) {
      setDetail(null);
      setError(nextError instanceof Error ? nextError.message : "Không mở được chi tiết tài liệu.");
    } finally {
      setLoading(false);
      setLoadingMessage(null);
    }
  }

  async function handleOpen(item: ContextualDocumentAction) {
    if (!item.document_id) {
      return;
    }
    setSelectedDocumentId(item.document_id);
    setLoading(true);
    setLoadingMessage("Đang mở tài liệu...");
    setError(null);
    try {
      await onOpenDocument(item);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Không mở được tài liệu.");
    } finally {
      setLoading(false);
      setLoadingMessage(null);
    }
  }

  if (items.length === 0) {
    return null;
  }

  return (
    <WorkspaceSection title="Tài liệu liên quan">
      <div className="contextual-document-list">
        {items.map((item) => (
          <div className="contextual-document-row" key={item.checklist_key}>
            <div className="contextual-document-main">
              <strong>{item.label}</strong>
              <span>{item.original_filename ?? DOCUMENT_STATUS_LABELS[item.status] ?? item.status}</span>
            </div>
            <div className="contextual-document-actions">
              <span className={`document-status-pill document-status-${item.status}`}>{DOCUMENT_STATUS_LABELS[item.status] ?? item.status}</span>
              {item.actions.map((action) => (
                <button
                  aria-label={`${action.label} ${item.label}`}
                  disabled={!action.available}
                  key={action.action_key}
                  onClick={() => {
                    if (action.action_key === "open") {
                      void handleOpen(item);
                    }
                    if (action.action_key === "history") {
                      void handleLoadHistory(item);
                    }
                  }}
                  title={action.disabled_reason ?? `${action.label} ${item.label}`}
                  type="button"
                >
                  {action.label}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
      {loading && loadingMessage ? <p className="workspace-note">{loadingMessage}</p> : null}
      {error ? (
        <p className="form-error" role="alert">
          {error}
        </p>
      ) : null}
      {detail ? (
        <div className="document-detail-shell">
          <div className="detail-grid compact-grid">
            <DetailValue label="Tài liệu" value={currentItem?.label ?? detail.title ?? detail.family_code} />
            <DetailValue label="Tiêu đề" value={detail.title} />
            <DetailValue label="Loại" value={detail.family_code} />
            <DetailValue label="Chế độ" value={detailMode === "history" ? "Lịch sử tài liệu" : "Chi tiết tài liệu"} />
          </div>
          <div className="table-scroll table-scroll-history">
            <table className="dense-table event-document-table">
              <thead>
                <tr>
                  <th>Biến thể</th>
                  <th>Ngôn ngữ</th>
                  <th>Phiên bản hiện có</th>
                </tr>
              </thead>
              <tbody>
                {detail.variants.map((variant) => (
                  <tr key={variant.id}>
                    <td>{variant.variant_type}</td>
                    <td>{variant.language_code}</td>
                    <td>
                      {variant.versions.length > 0
                        ? variant.versions
                            .map((version) => `${version.original_filename ?? `v${version.version_no}`}${version.is_current ? " (hiện hành)" : ""}`)
                            .join(", ")
                        : "Chưa có"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </WorkspaceSection>
  );
}

function LinkedGxpCertificates({
  items,
}: {
  items: GxpCertificateDetail[];
}) {
  const [selectedCertificateId, setSelectedCertificateId] = useState<string | null>(items[0]?.certificate_id ?? null);

  useEffect(() => {
    setSelectedCertificateId((current) =>
      current && items.some((item) => item.certificate_id === current) ? current : items[0]?.certificate_id ?? null,
    );
  }, [items]);

  const selectedCertificate = items.find((item) => item.certificate_id === selectedCertificateId) ?? items[0] ?? null;

  if (items.length === 0) {
    return (
      <EmptyState
        title="Chưa có chứng nhận GxP liên kết"
        description="Đợt kiểm tra đang chọn chưa có certificate record canonical liên kết trực tiếp theo case."
      />
    );
  }

  return (
    <div className="certificate-workspace-split event-linked-certificate-workspace">
      <section className="panel panel-tight certificate-list-panel">
        <div className="panel-header">
          <h3>Chứng nhận GxP liên kết</h3>
          <span className="panel-meta">{items.length} giấy</span>
        </div>
        <div className="table-scroll table-scroll-history">
          <table className="dense-table certificate-history-table">
            <thead>
              <tr>
                <th className="col-gxp">GxP</th>
                <th className="col-line">Dây chuyền</th>
                <th className="col-cert-number">Số GCN</th>
                <th className="col-date">Ngày cấp</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr
                  aria-selected={selectedCertificateId === item.certificate_id}
                  className={selectedCertificateId === item.certificate_id ? "selected" : ""}
                  key={item.certificate_id}
                  onClick={() => setSelectedCertificateId(item.certificate_id)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      setSelectedCertificateId(item.certificate_id);
                    }
                  }}
                  tabIndex={0}
                >
                  <td>{item.certificate_type}</td>
                  <td>{item.line_code ?? "Cơ sở"}</td>
                  <td title={item.certificate_number ?? ""}>
                    <div className="cell-stack">
                      <strong>{item.certificate_number ?? "Chưa có"}</strong>
                      {item.latest_flag ? <span>Hiện hành</span> : null}
                    </div>
                  </td>
                  <td>{formatCompactDate(item.issue_date)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel panel-tight certificate-detail-panel">
        {selectedCertificate ? <GxpCertificateDetailFields detail={selectedCertificate} /> : null}
      </section>
    </div>
  );
}

function LinkedBusinessEligibilityCertificates({
  items,
}: {
  items: BusinessEligibilityDetail[];
}) {
  const [selectedCertificateId, setSelectedCertificateId] = useState<string | null>(
    items[0]?.business_eligibility_certificate_id ?? null,
  );

  useEffect(() => {
    setSelectedCertificateId((current) =>
      current && items.some((item) => item.business_eligibility_certificate_id === current)
        ? current
        : items[0]?.business_eligibility_certificate_id ?? null,
    );
  }, [items]);

  const selectedCertificate =
    items.find((item) => item.business_eligibility_certificate_id === selectedCertificateId) ?? items[0] ?? null;

  if (items.length === 0) {
    return (
      <EmptyState
        title="Chưa có chứng nhận ĐĐK liên kết"
        description="Không tìm thấy liên kết canonical từ certificate của đợt kiểm tra này sang giấy chứng nhận đủ điều kiện."
      />
    );
  }

  return (
    <div className="certificate-workspace-split event-linked-certificate-workspace">
      <section className="panel panel-tight certificate-list-panel">
        <div className="panel-header">
          <h3>Chứng nhận ĐĐK liên kết</h3>
          <span className="panel-meta">{items.length} giấy</span>
        </div>
        <div className="table-scroll table-scroll-history">
          <table className="dense-table eligibility-history-table">
            <thead>
              <tr>
                <th className="col-cert-number">Số GCN</th>
                <th className="col-date">Ngày cấp</th>
                <th className="col-sequence">Lần</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr
                  aria-selected={selectedCertificateId === item.business_eligibility_certificate_id}
                  className={selectedCertificateId === item.business_eligibility_certificate_id ? "selected" : ""}
                  key={item.business_eligibility_certificate_id}
                  onClick={() => setSelectedCertificateId(item.business_eligibility_certificate_id)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      setSelectedCertificateId(item.business_eligibility_certificate_id);
                    }
                  }}
                  tabIndex={0}
                >
                  <td title={item.certificate_number ?? ""}>
                    <div className="cell-stack">
                      <strong>{item.certificate_number ?? "Chưa có"}</strong>
                      {item.latest_flag ? <span>Hiện hành</span> : null}
                    </div>
                  </td>
                  <td>{formatCompactDate(item.issued_on)}</td>
                  <td>{item.issuance_sequence_text ? `Lần ${item.issuance_sequence_text}` : "Chưa có"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel panel-tight certificate-detail-panel">
        {selectedCertificate ? <BusinessEligibilityDetailFields detail={selectedCertificate} /> : null}
      </section>
    </div>
  );
}

function renderCaseStepContent(
  activeTab: string,
  caseWorkspace: CaseWorkspace,
  onCaseApplicationSave: (payload: CaseApplicationUpsertRequest) => Promise<void>,
  onCaseAssessmentSave: (payload: CaseAssessmentUpsertRequest) => Promise<void>,
  onInspectionPlanSave: (payload: InspectionPlanUpsertRequest) => Promise<void>,
  onInspectionOutcomeSave: (payload: InspectionOutcomeUpsertRequest) => Promise<void>,
  onEvaluationScopeSave: (payload: EvaluationScopeUpsertRequest) => Promise<void>,
  selectedRemediationCycleId: string | null,
  onSelectedRemediationCycleChange: (cycleId: string | null) => void,
  onCreateCapaCycle: (payload: CapaCycleCreateRequest) => Promise<void>,
  onUpdateCapaCycle: (cycleId: string, payload: CapaCycleUpdateRequest) => Promise<void>,
  onSubmitCapaCycle: (cycleId: string, payload: CapaCycleSubmitRequest) => Promise<void>,
  onAssessCapaCycle: (cycleId: string, payload: CapaCycleAssessRequest) => Promise<void>,
  onOpenDocument: (caseId: string, item: ContextualDocumentAction) => Promise<void>,
  onLoadDocumentDetail: (documentId: string) => Promise<DocumentDetail>,
) {
  const documentItems = caseWorkspace.contextual_document_actions.filter((item) => {
    if (item.workflow_step !== activeTab) {
      return false;
    }
    if (item.parent_scope === "capa_cycle") {
      return item.parent_id === selectedRemediationCycleId;
    }
    return item.parent_scope === "case";
  });

  if (activeTab === "Hồ sơ") {
    return (
      <div className="event-step-stack">
        <CaseApplicationWorkspace caseWorkspace={caseWorkspace} onSave={onCaseApplicationSave} />
        <ContextualDocumentSection
          items={documentItems}
          onLoadDocumentDetail={onLoadDocumentDetail}
          onOpenDocument={(item) => onOpenDocument(caseWorkspace.case_summary.id, item)}
        />
      </div>
    );
  }

  if (activeTab === "Kiểm tra") {
    return (
      <div className="event-step-stack">
        <CaseInspectionWorkspace
          caseWorkspace={caseWorkspace}
          onInspectionOutcomeSave={onInspectionOutcomeSave}
          onInspectionPlanSave={onInspectionPlanSave}
          onEvaluationScopeSave={onEvaluationScopeSave}
        />
        <ContextualDocumentSection
          items={documentItems}
          onLoadDocumentDetail={onLoadDocumentDetail}
          onOpenDocument={(item) => onOpenDocument(caseWorkspace.case_summary.id, item)}
        />
      </div>
    );
  }

  if (activeTab === "Khắc phục") {
    return (
      <div className="event-step-stack">
        <CaseRemediationWorkspace
          caseWorkspace={caseWorkspace}
          onAssessCycle={onAssessCapaCycle}
          onCreateCycle={onCreateCapaCycle}
          onSelectedCycleChange={onSelectedRemediationCycleChange}
          onSubmitCycle={onSubmitCapaCycle}
          onUpdateCycle={onUpdateCapaCycle}
          selectedCycleId={selectedRemediationCycleId}
        />
        <ContextualDocumentSection
          items={documentItems}
          onLoadDocumentDetail={onLoadDocumentDetail}
          onOpenDocument={(item) => onOpenDocument(caseWorkspace.case_summary.id, item)}
        />
      </div>
    );
  }

  if (activeTab === "Xử lý") {
    return (
      <div className="event-step-stack">
        <CaseProcessingWorkspace caseWorkspace={caseWorkspace} onSave={onCaseAssessmentSave} />
        <ContextualDocumentSection
          items={documentItems}
          onLoadDocumentDetail={onLoadDocumentDetail}
          onOpenDocument={(item) => onOpenDocument(caseWorkspace.case_summary.id, item)}
        />
      </div>
    );
  }

  if (activeTab === "Chứng nhận GxP") {
    return (
      <div className="event-step-stack">
        <LinkedGxpCertificates items={caseWorkspace.linked_gxp_certificates} />
        <ContextualDocumentSection
          items={documentItems}
          onLoadDocumentDetail={onLoadDocumentDetail}
          onOpenDocument={(item) => onOpenDocument(caseWorkspace.case_summary.id, item)}
        />
      </div>
    );
  }

  return <LinkedBusinessEligibilityCertificates items={caseWorkspace.linked_business_eligibility_certificates} />;
}

function renderChangeRequestStepContent(activeTab: string, changeRequestWorkspace: ChangeRequestWorkspace) {
  if (activeTab === "Đề nghị") {
    return (
      <div className="event-step-stack">
        <WorkspaceSection title="Thông tin đề nghị thay đổi">
          <div className="detail-grid compact-grid">
            <DetailValue label="Mã thay đổi" value={changeRequestWorkspace.legacy_change_request_id ? `TD-${changeRequestWorkspace.legacy_change_request_id}` : null} />
            <DetailValue label="Phạm vi" value={changeRequestWorkspace.scope_label} />
            <DetailValue label="Ngày đề nghị" value={formatCompactDate(changeRequestWorkspace.submitted_on)} />
            <DetailValue label="Đơn vị/người đề nghị" value={changeRequestWorkspace.requester_name} />
            <DetailValue label="Trạng thái" value={formatStatusLabel(changeRequestWorkspace.state)} />
            <DetailValue label="Mô tả" multiline value={changeRequestWorkspace.description} />
          </div>
        </WorkspaceSection>
      </div>
    );
  }

  if (activeTab === "Chi tiết") {
    if (changeRequestWorkspace.details.length === 0) {
      return (
        <EmptyState
          title="Chưa có chi tiết thay đổi"
          description="Legacy db.Tdoi2 hiện không có dòng chi tiết canonical cho yêu cầu thay đổi này."
        />
      );
    }
    return (
      <div className="event-step-stack">
        <WorkspaceSection title="Danh mục chi tiết thay đổi">
          <div className="table-scroll table-scroll-history">
            <table className="dense-table change-request-detail-table">
              <thead>
                <tr>
                  <th>Phân loại</th>
                  <th>Trạng thái chấp nhận</th>
                  <th>Thông tin cũ</th>
                  <th>Thông tin mới</th>
                </tr>
              </thead>
              <tbody>
                {changeRequestWorkspace.details.map((item) => (
                  <tr key={item.change_detail_id}>
                    <td>{item.classification_label ?? "Chưa có"}</td>
                    <td>{item.approval_status ?? "Chưa có"}</td>
                    <td>{item.old_value ?? "Chưa có"}</td>
                    <td>{item.new_value ?? "Chưa có"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </WorkspaceSection>
      </div>
    );
  }

  if (activeTab === "Xử lý") {
    return (
      <div className="event-step-stack">
        <WorkspaceSection title="Kết quả xử lý thay đổi">
          <div className="detail-grid compact-grid">
            <DetailValue label="Ngày xử lý" value={formatCompactDate(changeRequestWorkspace.handled_on)} />
            <DetailValue label="Người xử lý" value={changeRequestWorkspace.handled_by_name} />
            <DetailValue label="Kết quả" multiline value={changeRequestWorkspace.result_label} />
            <DetailValue label="Hiệu lực" value={formatCompactDate(changeRequestWorkspace.effective_on)} />
            <DetailValue label="Tham chiếu phê duyệt" value={changeRequestWorkspace.approval_reference} />
          </div>
        </WorkspaceSection>
      </div>
    );
  }

  return (
    <WorkspaceSection title="Checklist tài liệu thay đổi">
      <DocumentChecklistSection
        emptyDescription="Canonical document owner hiện chưa có document row hoặc family checklist nào được gắn cho yêu cầu thay đổi này."
        items={changeRequestWorkspace.documents.items}
      />
    </WorkspaceSection>
  );
}

export function EventWorkspace({
  selectedHistory,
  caseWorkspace,
  caseWorkspaceLoading,
  caseWorkspaceError,
  changeRequestWorkspace,
  changeRequestWorkspaceLoading,
  changeRequestWorkspaceError,
  activeTab,
  onTabChange,
  onCaseApplicationSave,
  onCaseAssessmentSave,
  onInspectionPlanSave,
  onInspectionOutcomeSave,
  onEvaluationScopeSave,
  onOpenDocument,
  onLoadDocumentDetail,
  selectedRemediationCycleId,
  onSelectedRemediationCycleChange,
  onCreateCapaCycle,
  onUpdateCapaCycle,
  onSubmitCapaCycle,
  onAssessCapaCycle,
}: {
  selectedHistory: FacilityHistoryItem | null;
  caseWorkspace: CaseWorkspace | null;
  caseWorkspaceLoading: boolean;
  caseWorkspaceError: string | null;
  changeRequestWorkspace: ChangeRequestWorkspace | null;
  changeRequestWorkspaceLoading: boolean;
  changeRequestWorkspaceError: string | null;
  activeTab: string;
  onTabChange: (tab: string) => void;
  onCaseApplicationSave: (payload: CaseApplicationUpsertRequest) => Promise<void>;
  onCaseAssessmentSave: (payload: CaseAssessmentUpsertRequest) => Promise<void>;
  onInspectionPlanSave: (payload: InspectionPlanUpsertRequest) => Promise<void>;
  onInspectionOutcomeSave: (payload: InspectionOutcomeUpsertRequest) => Promise<void>;
  onEvaluationScopeSave: (payload: EvaluationScopeUpsertRequest) => Promise<void>;
  onOpenDocument: (caseId: string, item: ContextualDocumentAction) => Promise<void>;
  onLoadDocumentDetail: (documentId: string) => Promise<DocumentDetail>;
  selectedRemediationCycleId: string | null;
  onSelectedRemediationCycleChange: (cycleId: string | null) => void;
  onCreateCapaCycle: (payload: CapaCycleCreateRequest) => Promise<void>;
  onUpdateCapaCycle: (cycleId: string, payload: CapaCycleUpdateRequest) => Promise<void>;
  onSubmitCapaCycle: (cycleId: string, payload: CapaCycleSubmitRequest) => Promise<void>;
  onAssessCapaCycle: (cycleId: string, payload: CapaCycleAssessRequest) => Promise<void>;
}) {
  if (!selectedHistory) {
    return (
      <EmptyState
        title="Chưa chọn sự kiện"
        description="Chọn một dòng lịch sử để xem vùng detail nghiệp vụ bên dưới."
      />
    );
  }

  const tabs = selectedHistory.source_type === "change_request" ? CHANGE_REQUEST_EVENT_TABS : CASE_EVENT_TABS;
  const effectiveActiveTab = tabs.some((tab) => tab === activeTab) ? activeTab : tabs[0];

  return (
    <section className="event-workspace">
      <div className="panel-header">
        <StatusBadge value={selectedHistory.state} />
      </div>
      <nav aria-label="Quy trình xử lý sự kiện" className="workflow-stepper">
        <ol className="workflow-step-list">
          {tabs.map((tab, index) => (
            <li key={tab}>
              <button
                aria-label={tab}
                aria-current={effectiveActiveTab === tab ? "step" : undefined}
                className={effectiveActiveTab === tab ? "workflow-step active" : "workflow-step"}
                onClick={() => onTabChange(tab)}
                type="button"
              >
                <span className="workflow-step-index">{index + 1}</span>
                <span>{tab}</span>
              </button>
            </li>
          ))}
        </ol>
      </nav>
      <div className="workspace-body event-workspace-body">
        {selectedHistory.source_type === "change_request" ? (
          changeRequestWorkspaceLoading ? (
            <EmptyState title="Đang tải workspace thay đổi" description="Đang lấy dữ liệu đọc theo yêu cầu thay đổi đã chọn từ authenticated API." />
          ) : changeRequestWorkspaceError ? (
            <EmptyState
              title="Không tải được workspace thay đổi"
              description={changeRequestWorkspaceError}
            />
          ) : changeRequestWorkspace ? (
            renderChangeRequestStepContent(effectiveActiveTab, changeRequestWorkspace)
          ) : (
            <EmptyState title="Chưa có workspace thay đổi" description="Backend chưa trả dữ liệu workspace cho lựa chọn thay đổi hiện tại." />
          )
        ) : caseWorkspaceLoading ? (
          <EmptyState title="Đang tải workspace hồ sơ" description="Đang lấy dữ liệu đọc theo case đã chọn từ authenticated API." />
        ) : caseWorkspaceError ? (
          <EmptyState
            title="Không tải được workspace hồ sơ"
            description={caseWorkspaceError}
          />
        ) : caseWorkspace ? (
          renderCaseStepContent(
            effectiveActiveTab,
            caseWorkspace,
            onCaseApplicationSave,
            onCaseAssessmentSave,
            onInspectionPlanSave,
            onInspectionOutcomeSave,
            onEvaluationScopeSave,
            selectedRemediationCycleId,
            onSelectedRemediationCycleChange,
            onCreateCapaCycle,
            onUpdateCapaCycle,
            onSubmitCapaCycle,
            onAssessCapaCycle,
            onOpenDocument,
            onLoadDocumentDetail,
          )
        ) : (
          <EmptyState title="Chưa có workspace hồ sơ" description="Backend chưa trả dữ liệu workspace cho lựa chọn case hiện tại." />
        )}
      </div>
    </section>
  );
}
