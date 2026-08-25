const ACTION_LABELS: Record<string, string> = {
  "user.register": "Account created",
  "login.success": "Signed in",
  "login.failure": "Sign-in failed",
  "login.locked": "Account locked",
  "login.blocked": "Inactive account sign-in blocked",
  "share.enable": "Sharing enabled",
  "share.update": "Sharing settings updated",
  "share.disable": "Sharing disabled",
  "share.download": "Shared files downloaded",
};

const DETAIL_LABELS: Record<string, string> = {
  archive: "Archive",
  file_id: "File",
  file_ids: "Files",
  filename: "Filename",
  is_admin: "Administrator",
  visibility: "Visibility",
};

export function formatAuditAction(action: string): string {
  const known = ACTION_LABELS[action];
  if (known) {
    return known;
  }
  const words = action.replace(/[._-]+/g, " ").trim();
  return words ? `${words[0]?.toUpperCase()}${words.slice(1)}` : "Unknown event";
}

export function formatAuditActor(actor: string | null): string {
  if (!actor) {
    return "Anonymous";
  }
  const user = /^user:(\d+)$/.exec(actor);
  return user ? `User #${user[1]}` : actor;
}

export function formatAuditTarget(target: string | null): string {
  if (!target) {
    return "None";
  }
  const reference = /^(package|share|user):(.+)$/.exec(target);
  if (!reference) {
    return target;
  }
  const label = `${reference[1]?.[0]?.toUpperCase()}${reference[1]?.slice(1)}`;
  const separator = reference[1] === "share" ? " " : " #";
  return `${label}${separator}${reference[2]}`;
}

function formatDetailValue(value: unknown): string {
  if (typeof value === "boolean") {
    return value ? "Yes" : "No";
  }
  if (Array.isArray(value)) {
    return value.join(", ");
  }
  if (value === null || value === undefined) {
    return "None";
  }
  return String(value);
}

export function formatAuditDetail(detail: Record<string, unknown> | null): string {
  if (!detail || Object.keys(detail).length === 0) {
    return "";
  }
  return Object.entries(detail)
    .map(([key, value]) => {
      const label = DETAIL_LABELS[key] ?? formatAuditAction(key);
      return `${label}: ${formatDetailValue(value)}`;
    })
    .join(" · ");
}