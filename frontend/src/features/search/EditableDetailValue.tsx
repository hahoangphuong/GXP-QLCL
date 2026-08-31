import type { KeyboardEvent, ReactNode } from "react";

import { DetailValue } from "./DetailValue";

function IconButton({
  ariaLabel,
  children,
  className,
  disabled = false,
  onClick,
  title,
  type = "button",
}: {
  ariaLabel: string;
  children: ReactNode;
  className?: string;
  disabled?: boolean;
  onClick?: () => void;
  title: string;
  type?: "button" | "submit";
}) {
  return (
    <button
      aria-label={ariaLabel}
      className={className ? `icon-button ${className}` : "icon-button"}
      disabled={disabled}
      onClick={onClick}
      title={title}
      type={type}
    >
      {children}
    </button>
  );
}

function SaveIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 16 16">
      <path d="M6.5 11.3 3.2 8l-.9.9 4.2 4.2 7.2-7.2-.9-.9z" fill="currentColor" />
    </svg>
  );
}

function CancelIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 16 16">
      <path
        d="m4.1 3.4 3.9 3.9 3.9-3.9.7.7L8.7 8l3.9 3.9-.7.7L8 8.7l-3.9 3.9-.7-.7L7.3 8 3.4 4.1z"
        fill="currentColor"
      />
    </svg>
  );
}

export function EditableDetailValue({
  editButtonLabel,
  error,
  isEditing,
  label,
  multiline = false,
  onCancel,
  onEdit,
  onSave,
  pending = false,
  saveDisabled = false,
  value,
  children,
}: {
  editButtonLabel: string;
  error?: string | null;
  isEditing: boolean;
  label: string;
  multiline?: boolean;
  onCancel: () => void;
  onEdit: (() => void) | null;
  onSave: () => void;
  pending?: boolean;
  saveDisabled?: boolean;
  value: ReactNode;
  children: ReactNode;
}) {
  function handleReadOnlyKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (!onEdit) {
      return;
    }
    if (event.key !== "Enter" && event.key !== "F2") {
      return;
    }
    event.preventDefault();
    onEdit();
  }

  if (!isEditing) {
    return (
      <div className={multiline ? "summary-span editable-detail-value" : "editable-detail-value"}>
        <div
          aria-label={editButtonLabel}
          className={onEdit ? "editable-detail-header editable-detail-header-activator" : "editable-detail-header"}
          onDoubleClick={onEdit ?? undefined}
          onKeyDown={handleReadOnlyKeyDown}
          role={onEdit ? "button" : undefined}
          tabIndex={onEdit ? 0 : undefined}
          title={onEdit ? `${label}: nhấp đúp, Enter hoặc F2 để sửa` : undefined}
        >
          <DetailValue label={label} multiline={multiline} value={value} />
        </div>
      </div>
    );
  }

  return (
    <div className={multiline ? "summary-span editable-detail-value" : "editable-detail-value"}>
      <span className="editable-detail-label">{label}</span>
      <div className="editable-detail-editor">
        <div className="editable-detail-input">{children}</div>
        <div className="editable-detail-actions">
          <IconButton
            ariaLabel={`Lưu ${label}`}
            className="icon-button-primary"
            disabled={pending || saveDisabled}
            onClick={onSave}
            title={`Lưu ${label}`}
          >
            <SaveIcon />
          </IconButton>
          <IconButton
            ariaLabel={`Hủy sửa ${label}`}
            disabled={pending}
            onClick={onCancel}
            title={`Hủy sửa ${label}`}
          >
            <CancelIcon />
          </IconButton>
        </div>
      </div>
      {error ? (
        <p className="field-error" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
