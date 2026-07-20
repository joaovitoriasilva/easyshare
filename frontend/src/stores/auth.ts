import { defineStore } from "pinia";
import { ref } from "vue";
import { authApi } from "@/api";
import { getToken, setToken } from "@/api/client";
import type { User } from "@/api/types";

export const useAuthStore = defineStore("auth", () => {
  const user = ref<User | null>(null);
  const initialized = ref(false);
  const allowRegistration = ref(true);
  const maxFileSize = ref(100 * 1024 * 1024);
  const emailVerificationEnabled = ref(false);

  async function init(): Promise<void> {
    if (initialized.value) {
      return;
    }
    if (getToken()) {
      try {
        user.value = await authApi.me();
      } catch {
        setToken(null);
        user.value = null;
      }
    }
    try {
      const config = await authApi.config();
      allowRegistration.value = config.allow_registration;
      maxFileSize.value = config.max_file_size;
      emailVerificationEnabled.value = config.email_verification_enabled;
    } catch {
      allowRegistration.value = true;
    }
    initialized.value = true;
  }

  async function login(usernameOrEmail: string, password: string): Promise<void> {
    user.value = await authApi.login(usernameOrEmail, password);
  }

  async function register(
    email: string,
    username: string,
    password: string,
  ): Promise<void> {
    await authApi.register(email, username, password);
    await login(username, password);
  }

  function logout(): void {
    setToken(null);
    user.value = null;
  }

  return { user, initialized, allowRegistration, maxFileSize, emailVerificationEnabled, init, login, register, logout };
});
