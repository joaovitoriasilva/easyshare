import { api, setToken } from "./client";
import type {
  AdminUser,
  AdminUserUpdate,
  AuditPage,
  AuthConfig,
  BulkQuotaResult,
  DownloadToken,
  Package,
  PackageFile,
  PackagePage,
  PackageStats,
  PublicShare,
  ServiceSettings,
  Share,
  StorageUsage,
  User,
  UserPage,
  Visibility,
} from "./types";

export const authApi = {
  async config(): Promise<AuthConfig> {
    return api.request<AuthConfig>("/auth/config", { auth: false });
  },

  async register(email: string, username: string, password: string): Promise<User> {
    return api.request<User>("/auth/register", {
      method: "POST",
      body: { email, username, password },
      auth: false,
    });
  },

  async login(usernameOrEmail: string, password: string): Promise<User> {
    const form = new URLSearchParams();
    form.set("username", usernameOrEmail);
    form.set("password", password);
    const { access_token } = await api.request<{ access_token: string }>(
      "/auth/login",
      { method: "POST", form, auth: false },
    );
    setToken(access_token);
    return authApi.me();
  },

  async me(): Promise<User> {
    return api.request<User>("/auth/me", { skipAuthRedirect: true });
  },

  async usage(): Promise<StorageUsage> {
    return api.request<StorageUsage>("/auth/me/usage");
  },

  async changePassword(currentPassword: string, newPassword: string): Promise<void> {
    await api.request<void>("/auth/me/password", {
      method: "POST",
      body: { current_password: currentPassword, new_password: newPassword },
    });
  },
};

export const packagesApi = {
  list(params: { limit?: number; offset?: number; q?: string } = {}): Promise<PackagePage> {
    const query = new URLSearchParams();
    query.set("limit", String(params.limit ?? 50));
    query.set("offset", String(params.offset ?? 0));
    if (params.q && params.q.trim()) {
      query.set("q", params.q.trim());
    }
    return api.request<PackagePage>(`/packages?${query.toString()}`);
  },
  get(id: number): Promise<Package> {
    return api.request<Package>(`/packages/${id}`);
  },
  create(name: string, description: string | null): Promise<Package> {
    return api.request<Package>("/packages", {
      method: "POST",
      body: { name, description },
    });
  },
  update(
    id: number,
    payload: { name?: string; description?: string | null },
  ): Promise<Package> {
    return api.request<Package>(`/packages/${id}`, {
      method: "PATCH",
      body: payload,
    });
  },
  remove(id: number): Promise<void> {
    return api.request<void>(`/packages/${id}`, { method: "DELETE" });
  },
  uploadFile(
    id: number,
    file: File,
    onProgress?: (fraction: number) => void,
    signal?: AbortSignal,
  ): Promise<PackageFile> {
    return api.upload<PackageFile>(`/packages/${id}/files`, file, {
      onProgress,
      signal,
    });
  },
  removeFile(packageId: number, fileId: number): Promise<void> {
    return api.request<void>(`/packages/${packageId}/files/${fileId}`, {
      method: "DELETE",
    });
  },
  removeAllFiles(packageId: number, fileIds?: number[]): Promise<void> {
    const query = new URLSearchParams();
    if (fileIds) {
      for (const fileId of fileIds) {
        query.append("file_ids", String(fileId));
      }
    }
    const qs = query.toString();
    return api.request<void>(
      `/packages/${packageId}/files${qs ? `?${qs}` : ""}`,
      { method: "DELETE" },
    );
  },
  stats(id: number): Promise<PackageStats> {
    return api.request<PackageStats>(`/packages/${id}/stats`);
  },
  downloadToken(id: number): Promise<DownloadToken> {
    return api.request<DownloadToken>(`/packages/${id}/download-token`, {
      method: "POST",
    });
  },
  fileDownloadUrl(id: number, fileId: number, token: string): string {
    return `/api/packages/${id}/files/${fileId}/download?token=${encodeURIComponent(token)}`;
  },
  downloadAllUrl(id: number, token: string, fileIds?: number[]): string {
    const params = new URLSearchParams();
    params.set("token", token);
    if (fileIds) {
      for (const fileId of fileIds) {
        params.append("file_ids", String(fileId));
      }
    }
    return `/api/packages/${id}/download?${params.toString()}`;
  },
};

export const sharesApi = {
  get(packageId: number): Promise<Share> {
    return api.request<Share>(`/packages/${packageId}/share`);
  },
  enable(
    packageId: number,
    visibility: Visibility,
    allowedEmails: string[],
    expiresAt?: string | null,
  ): Promise<Share> {
    return api.request<Share>(`/packages/${packageId}/share`, {
      method: "POST",
      body: {
        visibility,
        allowed_emails: allowedEmails,
        expires_at: expiresAt ?? null,
      },
    });
  },
  update(
    packageId: number,
    payload: {
      visibility?: Visibility;
      is_enabled?: boolean;
      allowed_emails?: string[];
      expires_at?: string | null;
    },
  ): Promise<Share> {
    return api.request<Share>(`/packages/${packageId}/share`, {
      method: "PATCH",
      body: payload,
    });
  },
  disable(packageId: number): Promise<void> {
    return api.request<void>(`/packages/${packageId}/share`, { method: "DELETE" });
  },
};

export const publicApi = {
  view(token: string): Promise<PublicShare> {
    return api.request<PublicShare>(`/s/${token}`, { auth: false });
  },
  access(token: string, email: string): Promise<PublicShare> {
    return api.request<PublicShare>(`/s/${token}/access`, {
      method: "POST",
      body: { email },
      auth: false,
    });
  },
  verify(token: string, email: string, code: string): Promise<PublicShare> {
    return api.request<PublicShare>(`/s/${token}/verify`, {
      method: "POST",
      body: { email, code },
      auth: false,
    });
  },
  downloadUrl(token: string, fileIds: number[], accessToken: string | null): string {
    const params = new URLSearchParams();
    for (const id of fileIds) {
      params.append("file_ids", String(id));
    }
    if (accessToken) {
      params.set("access", accessToken);
    }
    const query = params.toString();
    return `/api/s/${token}/download${query ? `?${query}` : ""}`;
  },
  fileUrl(token: string, fileId: number, accessToken: string | null): string {
    const params = new URLSearchParams();
    if (accessToken) {
      params.set("access", accessToken);
    }
    const query = params.toString();
    return `/api/s/${token}/files/${fileId}/download${query ? `?${query}` : ""}`;
  },
};

export interface AuditQuery {
  limit?: number;
  offset?: number;
  action?: string;
  actor?: string;
  packageId?: number;
}

function auditQuery(params: AuditQuery): string {
  const q = new URLSearchParams();
  q.set("limit", String(params.limit ?? 50));
  q.set("offset", String(params.offset ?? 0));
  if (params.action) {
    q.set("action", params.action);
  }
  if (params.actor) {
    q.set("actor", params.actor);
  }
  if (params.packageId != null) {
    q.set("package_id", String(params.packageId));
  }
  return `?${q.toString()}`;
}

export const auditApi = {
  mine(params: AuditQuery = {}): Promise<AuditPage> {
    return api.request<AuditPage>(`/audit/mine${auditQuery(params)}`);
  },
  all(params: AuditQuery = {}): Promise<AuditPage> {
    return api.request<AuditPage>(`/audit${auditQuery(params)}`);
  },
};

export const adminApi = {
  listUsers(params: { limit?: number; offset?: number } = {}): Promise<UserPage> {
    const q = new URLSearchParams();
    q.set("limit", String(params.limit ?? 50));
    q.set("offset", String(params.offset ?? 0));
    return api.request<UserPage>(`/admin/users?${q.toString()}`);
  },
  updateUser(id: number, patch: AdminUserUpdate): Promise<AdminUser> {
    return api.request<AdminUser>(`/admin/users/${id}`, { method: "PATCH", body: patch });
  },
  setAllQuotas(storageQuota: number): Promise<BulkQuotaResult> {
    return api.request<BulkQuotaResult>("/admin/users/quota", {
      method: "PATCH",
      body: { storage_quota: storageQuota },
    });
  },
  deleteUser(id: number): Promise<void> {
    return api.request<void>(`/admin/users/${id}`, { method: "DELETE" });
  },
  settings(): Promise<ServiceSettings> {
    return api.request<ServiceSettings>("/admin/settings");
  },
  resetPassword(id: number, newPassword: string): Promise<void> {
    return api.request<void>(`/admin/users/${id}/password`, {
      method: "POST",
      body: { new_password: newPassword },
    });
  },
};
