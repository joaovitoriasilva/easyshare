# EasyShare Frontend

Single-page app built with **Vue 3**, **TypeScript**, **Vite**, **Tailwind CSS**
and **shadcn-vue** style components on top of **Reka UI**.

## Features

- Register / login flows backed by JWT stored in `localStorage`.
- Dashboard to create and browse packages.
- Package view to upload/download/delete files and manage sharing
  (public or email-restricted, with a copyable share link).
- Public share view where recipients can unlock restricted shares by email
  and download all files or a selected subset as a zip.

## Getting started

```bash
cd frontend
npm install
npm run dev        # starts Vite on http://localhost:5173
```

The dev server proxies `/api` to the backend on `http://localhost:8000`.

## Crash reporting (optional)

Crash reporting via [GlitchTip](https://glitchtip.com/) (Sentry-compatible) is
wired up in `src/main.ts` but only activates when a DSN is provided at build
time through the `VITE_GLITCHTIP_DSN` environment variable:

```bash
VITE_GLITCHTIP_DSN="https://<key>@your-glitchtip-host/<project>" npm run build
```

When building the single Docker image, pass it as a build argument instead — the
`Dockerfile` forwards it to the frontend build stage. It is a build-time value,
so it cannot be supplied at container run time (the entrypoint runs after the
SPA is already compiled):

```bash
docker build --build-arg VITE_GLITCHTIP_DSN="https://<key>@your-glitchtip-host/<project>" .
```

Vite inlines `import.meta.env.VITE_GLITCHTIP_DSN` at build time, so when it is
unset the `@sentry/vue` SDK is tree-shaken out of the bundle entirely (zero
runtime cost). When set, the SDK is initialised after the app's own error
handler and captures component errors (including component name and props).

For the browser to actually reach GlitchTip, the backend must also allow its
origin in the `Content-Security-Policy`; set `EASYSHARE_CSP_REPORT_URI_FRONTEND` on the
backend to the matching GlitchTip security-report endpoint (see the root
`README.md`).

## Quality gates

```bash
npm run type-check   # vue-tsc
npm run lint         # eslint
npm run test         # vitest
npm run build        # type-check + production build
```

## Structure

```
src/
  api/          typed REST client and endpoint helpers
  components/ui shadcn-vue style UI primitives (Button, Input, Card, ...)
  lib/          utilities (cn, formatBytes)
  router/       vue-router routes and auth guards
  stores/       Pinia stores (auth)
  views/        page components
  test/         vitest suites
```
