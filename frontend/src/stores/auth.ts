import { defineStore } from "pinia";
import { ref } from "vue";
import { authApi } from "@/api";
import { getToken, setToken } from "@/api/client";
import type { User } from "@/api/types";

export const useAuthStore = defineStore("auth", () => {
  const user = ref<User | null>(null);
  const initialized = ref(false);

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

  return { user, initialized, init, login, register, logout };
});
