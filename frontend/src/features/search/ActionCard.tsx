import type { WorkspaceActionReadiness } from "../../types";

const FALLBACK_ACTIONS: WorkspaceActionReadiness[] = [
  {
    action_key: "create_company",
    label: "Công ty mới",
    readiness_status: "loading",
    detail: "Đang chờ ngữ cảnh và contract từ backend.",
    required_permissions: [],
  },
  {
    action_key: "create_site",
    label: "Cơ sở mới",
    readiness_status: "loading",
    detail: "Đang chờ ngữ cảnh và contract từ backend.",
    required_permissions: [],
  },
  {
    action_key: "create_production_line",
    label: "Dây chuyền mới",
    readiness_status: "loading",
    detail: "Đang chờ ngữ cảnh và contract từ backend.",
    required_permissions: [],
  },
  {
    action_key: "create_inspection_case",
    label: "Hồ sơ kiểm tra",
    readiness_status: "loading",
    detail: "Đang chờ ngữ cảnh và contract từ backend.",
    required_permissions: [],
  },
  {
    action_key: "create_reassessment_case",
    label: "Tái đánh giá",
    readiness_status: "loading",
    detail: "Đang chờ ngữ cảnh và contract từ backend.",
    required_permissions: [],
  },
  {
    action_key: "create_change_request",
    label: "Thay đổi",
    readiness_status: "loading",
    detail: "Đang chờ ngữ cảnh và contract từ backend.",
    required_permissions: [],
  },
];

export function ActionCard({
  actions = FALLBACK_ACTIONS,
}: {
  actions?: WorkspaceActionReadiness[];
}) {
  return (
    <section className="panel panel-tight action-panel">
      <div className="action-grid" aria-label="Thao tác theo ngữ cảnh cơ sở">
        {actions.map((action) => (
          <button
            aria-label={action.label}
            data-readiness-status={action.readiness_status}
            disabled
            key={action.action_key}
            title={action.detail}
            type="button"
          >
            {action.label}
          </button>
        ))}
      </div>
    </section>
  );
}
