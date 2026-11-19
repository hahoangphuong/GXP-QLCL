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

const CREATE_ACTION_KEYS = new Set([
  "create_company",
  "create_site",
  "create_production_line",
  "create_initial_case",
]);

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
  const createActions = actions.filter((action) => CREATE_ACTION_KEYS.has(action.action_key));
  const contextualActions = actions.filter((action) => !CREATE_ACTION_KEYS.has(action.action_key));

  const actionButton = (action: WorkspaceActionReadiness) => (
    <button
      aria-label={action.label}
      aria-pressed={selectedActionKey === action.action_key}
      data-readiness-status={action.readiness_status}
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
  );

  return (
    <section className="panel panel-tight action-panel action-toolbar">
      <span className="action-toolbar-heading">Thao tác</span>
      <div className="action-group" aria-label="Tạo mới">
        <span className="action-group-label">Tạo mới</span>
        <div className="action-grid">{createActions.map(actionButton)}</div>
      </div>
      {contextualActions.length > 0 ? (
        <div className="action-group" aria-label="Theo ngữ cảnh cơ sở">
          <span className="action-group-label">Theo ngữ cảnh</span>
          <div className="action-grid">{contextualActions.map(actionButton)}</div>
        </div>
      ) : null}
    </section>
  );
}
