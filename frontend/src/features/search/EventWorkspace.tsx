import { useEffect, useState, type ReactNode } from "react";

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
  CaseWorkspace,
  ChangeRequestWorkspace,
  DocumentChecklistItem,
  FacilityHistoryItem,
  GxpCertificateDetail,
  InspectionOutcomeUpsertRequest,
  InspectionPlanUpsertRequest,
} from "../../types";
import { BusinessEligibilityDetailFields } from "./BusinessEligibilityDetailFields";
import { CaseApplicationWorkspace } from "./CaseApplicationWorkspace";
import { CaseInspectionWorkspace } from "./CaseInspectionWorkspace";
import { CaseRemediationWorkspace } from "./CaseRemediationWorkspace";
import { DetailValue } from "./DetailValue";
import { GxpCertificateDetailFields } from "./GxpCertificateDetailFields";

const CASE_EVENT_TABS = ["Hồ sơ", "Kiểm tra", "Khắc phục", "Xử lý", "Tài liệu", "Chứng nhận GxP", "Chứng nhận ĐĐK"] as const;
const CHANGE_REQUEST_EVENT_TABS = ["Đề nghị", "Chi tiết", "Xử lý", "Tài liệu"] as const;

const PROCESSING_EVENT_LABELS: Record<string, string> = {
  application_submitted: "Tiếp nhận hồ sơ",
  assessment_completed: "Thẩm định hoàn tất",
  plan_created: "Lập kế hoạch",
  decision_issued: "Ban hành quyết định",
  inspection_executed: "Thực hiện kiểm tra",
  outcome_recorded: "Ghi nhận kết quả",
  certificate_issued: "Cấp chứng nhận",
};

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
  onInspectionPlanSave: (payload: InspectionPlanUpsertRequest) => Promise<void>,
  onInspectionOutcomeSave: (payload: InspectionOutcomeUpsertRequest) => Promise<void>,
  selectedRemediationCycleId: string | null,
  onSelectedRemediationCycleChange: (cycleId: string | null) => void,
  onCreateCapaCycle: (payload: CapaCycleCreateRequest) => Promise<void>,
  onUpdateCapaCycle: (cycleId: string, payload: CapaCycleUpdateRequest) => Promise<void>,
  onSubmitCapaCycle: (cycleId: string, payload: CapaCycleSubmitRequest) => Promise<void>,
  onAssessCapaCycle: (cycleId: string, payload: CapaCycleAssessRequest) => Promise<void>,
) {
  if (activeTab === "Hồ sơ") {
    return <CaseApplicationWorkspace caseWorkspace={caseWorkspace} onSave={onCaseApplicationSave} />;
  }

  if (activeTab === "Kiểm tra") {
    return (
      <CaseInspectionWorkspace
        caseWorkspace={caseWorkspace}
        onInspectionOutcomeSave={onInspectionOutcomeSave}
        onInspectionPlanSave={onInspectionPlanSave}
      />
    );
  }

  if (activeTab === "Khắc phục") {
    return (
      <CaseRemediationWorkspace
        caseWorkspace={caseWorkspace}
        onAssessCycle={onAssessCapaCycle}
        onCreateCycle={onCreateCapaCycle}
        onSelectedCycleChange={onSelectedRemediationCycleChange}
        onSubmitCycle={onSubmitCapaCycle}
        onUpdateCycle={onUpdateCapaCycle}
        selectedCycleId={selectedRemediationCycleId}
      />
    );
  }

  if (activeTab === "Xử lý") {
    const processing = caseWorkspace.processing;
    const hasProcessingData = Boolean(
      processing.assessed_on ||
        processing.assessor_name ||
        processing.assessment_result ||
        processing.notes ||
        processing.events.length > 0,
    );
    if (!hasProcessingData) {
      return (
        <EmptyState
          title="Chưa có dữ liệu xử lý"
          description="Canonical model hiện chưa có đủ dữ liệu xử lý hành chính riêng cho hồ sơ này."
        />
      );
    }
    return (
      <div className="event-step-stack">
        <WorkspaceSection title="Kết luận xử lý">
          <div className="detail-grid compact-grid">
            <DetailValue label="Ngày xử lý" value={formatCompactDate(processing.assessed_on)} />
            <DetailValue label="Người xử lý" value={processing.assessor_name} />
            <DetailValue label="Kết luận" multiline value={processing.assessment_result} />
            <DetailValue label="Ghi chú" multiline value={processing.notes} />
          </div>
        </WorkspaceSection>
        <WorkspaceSection title="Các mốc xử lý hành chính">
          {processing.events.length > 0 ? (
            <div className="table-scroll table-scroll-history">
              <table className="dense-table event-milestone-table">
                <thead>
                  <tr>
                    <th>Mốc</th>
                    <th>Ngày</th>
                    <th>Nội dung</th>
                  </tr>
                </thead>
                <tbody>
                  {processing.events.map((event, index) => (
                    <tr key={`${event.event_type}:${event.occurred_at ?? "none"}:${index}`}>
                      <td>{PROCESSING_EVENT_LABELS[event.event_type] ?? event.event_type}</td>
                      <td>{formatCompactDate(event.occurred_at)}</td>
                      <td>{event.payload ?? "Chưa có"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState title="Chưa có mốc xử lý" description="Chưa có inspection event hành chính nào được canonicalize cho hồ sơ này." />
          )}
        </WorkspaceSection>
      </div>
    );
  }

  if (activeTab === "Chứng nhận GxP") {
    return <LinkedGxpCertificates items={caseWorkspace.linked_gxp_certificates} />;
  }

  if (activeTab === "Tài liệu") {
    return (
      <WorkspaceSection title="Checklist tài liệu hồ sơ">
        <DocumentChecklistSection
          emptyDescription="Canonical document owner hiện chưa có document row nào cho hồ sơ hoặc các vòng CAPA đang chọn."
          items={caseWorkspace.documents.items}
        />
      </WorkspaceSection>
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
  onInspectionPlanSave,
  onInspectionOutcomeSave,
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
  onInspectionPlanSave: (payload: InspectionPlanUpsertRequest) => Promise<void>;
  onInspectionOutcomeSave: (payload: InspectionOutcomeUpsertRequest) => Promise<void>;
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
        <div>
          <h3>{selectedHistory.reference_code ?? selectedHistory.event_type}</h3>
        </div>
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
            onInspectionPlanSave,
            onInspectionOutcomeSave,
            selectedRemediationCycleId,
            onSelectedRemediationCycleChange,
            onCreateCapaCycle,
            onUpdateCapaCycle,
            onSubmitCapaCycle,
            onAssessCapaCycle,
          )
        ) : (
          <EmptyState title="Chưa có workspace hồ sơ" description="Backend chưa trả dữ liệu workspace cho lựa chọn case hiện tại." />
        )}
      </div>
    </section>
  );
}
