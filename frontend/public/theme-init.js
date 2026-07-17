// Applies the persisted (or system) theme before the app mounts to avoid a
// flash of the wrong theme. Kept as an external file (not inline) so it
// satisfies the `script-src 'self'` Content-Security-Policy without needing
// 'unsafe-inline' or a build-specific hash. Must stay in sync with the theme
// store's storage key and resolution logic (src/stores/theme.ts).
(function () {
  try {
    var stored = window.localStorage.getItem("easyshare-theme");
    var isDark =
      stored === "dark" ||
      (stored !== "light" &&
        window.matchMedia("(prefers-color-scheme: dark)").matches);
    document.documentElement.classList.toggle("dark", isDark);
  } catch (e) {
    /* ignore */
  }
})();
