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
