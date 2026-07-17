export type Visibility = "public" | "restricted";

export interface AuthConfig {
  allow_registration: boolean;
}

export interface User {
  id: number;
  email: string;
  username: string;
  is_active: boolean;
  is_admin: boolean;
  storage_quota: number;
  created_at: string;
}

/** User plus current storage usage, as returned by the admin endpoints. */
export interface AdminUser extends User {
  storage_used: number;
}

export interface PackageFile {
  id: number;
  filename: string;
  content_type: string;
  size: number;
  created_at: string;
}

export interface Package {
  id: number;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
  files: PackageFile[];
}

export interface PackageStats {
  views: number;
  downloads: number;
  file_downloads: Record<number, number>;
}

export interface Share {
  id: number;
  package_id: number;
  token: string;
  visibility: Visibility;
  is_enabled: boolean;
  created_at: string;
  allowed_emails: string[];
}

export interface PublicFile {
  id: number;
  filename: string;
  content_type: string;
  size: number;
}

export interface PublicShare {
  token: string;
  package_name: string;
  package_description: string | null;
  visibility: Visibility;
  requires_email: boolean;
  files: PublicFile[];
  download_token?: string | null;
}

export interface AuditEvent {
  id: number;
  created_at: string;
  action: string;
  actor: string | null;
  target: string | null;
  package_id: number | null;
  request_id: string | null;
  client_ip: string | null;
  detail: Record<string, unknown> | null;
}

export interface AuditPage {
  items: AuditEvent[];
  total: number;
  limit: number;
  offset: number;
}

export interface UserPage {
  items: AdminUser[];
  total: number;
  limit: number;
  offset: number;
}

export interface AdminUserUpdate {
  username?: string;
  email?: string;
  is_active?: boolean;
  is_admin?: boolean;
  // Bytes; 0 = unlimited.
  storage_quota?: number;
}

export interface BulkQuotaResult {
  updated: number;
}
