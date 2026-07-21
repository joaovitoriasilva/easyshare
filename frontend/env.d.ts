/// <reference types="vite/client" />

interface ImportMetaEnv {
  /**
   * GlitchTip (Sentry-compatible) DSN used to initialise crash reporting in the
   * SPA. When empty/undefined the Sentry SDK is not initialised. Baked in at
   * build time, so changing it requires rebuilding the frontend.
   */
  readonly VITE_GLITCHTIP_DSN?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

declare module "*.vue" {
  import type { DefineComponent } from "vue";
  const component: DefineComponent<Record<string, unknown>, Record<string, unknown>, unknown>;
  export default component;
}
