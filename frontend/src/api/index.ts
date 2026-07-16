import { api, setToken } from "./client";
import type {
  AdminUserUpdate,
  AuditPage,
  AuthConfig,
  Package,
  PublicShare,
  Share,
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
    return api.request<User>("/auth/me");
  },
};

export const packagesApi = {
  async list(): Promise<Package[]> {
    // The API paginates; fetch successive pages until a short (final) page so
    // the dashboard shows every package without an unbounded query.
    const pageSize = 100;
    const all: Package[] = [];
    for (let offset = 0; ; offset += pageSize) {
      const page = await api.request<Package[]>(
        `/packages?limit=${pageSize}&offset=${offset}`,
      );
      all.push(...page);
      if (page.length < pageSize) {
        break;
      }
    }
    return all;
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
  uploadFile(id: number, file: File): Promise<void> {
    const form = new FormData();
    form.append("file", file);
    return api.request<void>(`/packages/${id}/files`, { method: "POST", form });
  },
  removeFile(packageId: number, fileId: number): Promise<void> {
    return api.request<void>(`/packages/${packageId}/files/${fileId}`, {
      method: "DELETE",
    });
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
  ): Promise<Share> {
    return api.request<Share>(`/packages/${packageId}/share`, {
      method: "POST",
      body: { visibility, allowed_emails: allowedEmails },
    });
  },
  update(
    packageId: number,
    payload: {
      visibility?: Visibility;
      is_enabled?: boolean;
      allowed_emails?: string[];
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
  },  access(token: string, email: string): Promise<PublicShare> {
    return api.request<PublicShare>(`/s/${token}/access`, {
      method: "POST",
      body: { email },
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
  updateUser(id: number, patch: AdminUserUpdate): Promise<User> {
    return api.request<User>(`/admin/users/${id}`, { method: "PATCH", body: patch });
  },
  deleteUser(id: number): Promise<void> {
    return api.request<void>(`/admin/users/${id}`, { method: "DELETE" });
  },
};
