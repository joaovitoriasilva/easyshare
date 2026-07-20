export type Visibility = "public" | "restricted";

export interface AuthConfig {
  allow_registration: boolean;
  max_file_size: number;
  // Whether restricted shares require an emailed one-time code. When false the
  // UI warns that allow-listed emails are accepted without verification.
  email_verification_enabled: boolean;
}

export interface StorageUsage {
  storage_used: number;
  storage_quota: number;
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
  last_downloaded_at: string | null;
}

export interface PackagePage {
  items: Package[];
  total: number;
  limit: number;
  offset: number;
}

export interface DownloadToken {
  token: string;
}

export interface Share {
  id: number;
  package_id: number;
  token: string;
  visibility: Visibility;
  is_enabled: boolean;
  created_at: string;
  // ISO timestamp, or null when the share never expires.
  expires_at: string | null;
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
  // True when /access emailed a one-time code that must be confirmed via
  // /verify before the files are revealed.
  verification_required?: boolean;
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
  // Configured audit-log retention in days; 0 means events are kept forever.
  retention_days: number;
}

/**
 * Non-sensitive runtime configuration shown on the admin settings view.
 * Secrets (the JWT signing key, connection credentials) are never included;
 * connection strings are reduced to their backend/scheme by the server.
 */
export interface ServiceSettings {
  app_name: string;
  environment: string;
  deployment_profile: string;
  allow_registration: boolean;
  algorithm: string;
  access_token_expire_minutes: number;
  share_access_token_expire_minutes: number;
  database_backend: string;
  db_pool_size: number;
  db_max_overflow: number;
  db_pool_timeout: number;
  storage_backend: string;
  obfuscate_storage_names: boolean;
  max_file_size: number;
  max_files_per_package: number;
  max_archive_size: number;
  max_concurrent_archive_builds: number;
  storage_quota_total: number;
  storage_quota_per_user: number;
  cors_origins: string[];
  rate_limit_enabled: boolean;
  rate_limit_backend: string;
  email_verification_enabled: boolean;
  log_level: string;
  log_format: string;
  audit_retention_days: number;
  audit_prune_interval_hours: number;
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
