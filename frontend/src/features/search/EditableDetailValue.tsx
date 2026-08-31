import type { ReactNode } from "react";

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

function EditIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 16 16">
      <path
        d="M11.9 1.6a1.5 1.5 0 0 1 2.1 0l.4.4a1.5 1.5 0 0 1 0 2.1l-8.8 8.8-3.2.6.6-3.2zM10.8 2.7 4.1 9.4l-.3 1.5 1.5-.3L12 3.9zM2 13.5h12v1H2z"
        fill="currentColor"
      />
    </svg>
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
  if (!isEditing) {
    return (
      <div className={multiline ? "summary-span editable-detail-value" : "editable-detail-value"}>
        <div className="editable-detail-header">
          <DetailValue label={label} multiline={multiline} value={value} />
          {onEdit ? (
            <IconButton ariaLabel={editButtonLabel} onClick={onEdit} title={editButtonLabel}>
              <EditIcon />
            </IconButton>
          ) : null}
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
