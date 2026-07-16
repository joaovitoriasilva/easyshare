export type Visibility = "public" | "restricted";

export interface User {
  id: number;
  email: string;
  username: string;
  is_active: boolean;
  created_at: string;
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
}
