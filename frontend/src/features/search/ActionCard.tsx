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
  onActionSelect,
  onActionButtonRef,
  selectedActionKey,
}: {
  actions?: WorkspaceActionReadiness[];
  onActionSelect?: (actionKey: string) => void;
  onActionButtonRef?: (actionKey: string, element: HTMLButtonElement | null) => void;
  selectedActionKey?: string | null;
}) {
  return (
    <section className="panel panel-tight action-panel">
      <div className="action-grid" aria-label="Thao tác theo ngữ cảnh cơ sở">
        {actions.map((action) => (
          <button
            aria-label={action.label}
            aria-pressed={selectedActionKey === action.action_key}
            data-readiness-status={action.readiness_status}
            // This action opens a context-selection editor; "unavailable" may mean
            // that GxP has not yet been selected, or the selected context is\n            // occupied but another context may be free. The editor rechecks the
            // exact canonical context and never mutates on opening.
            disabled={action.readiness_status !== "available"
              && !(action.action_key === "create_initial_case" && (action.readiness_status === "unavailable" || action.readiness_status === "conflict"))}
            key={action.action_key}
            onClick={() => onActionSelect?.(action.action_key)}
            ref={(element) => onActionButtonRef?.(action.action_key, element)}
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
