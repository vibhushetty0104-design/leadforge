# @leadforge/web

Next.js (App Router) frontend for LEADFORGE. See the [root README](../../README.md) for setup.

```bash
npm run dev -w @leadforge/web        # from the repository root
npm run lint -w @leadforge/web
npm run typecheck -w @leadforge/web
npm run build -w @leadforge/web
```

Layout:

- `src/app` — routes. `(app)/` holds authenticated pages that share the shell; `login/` and `auth/` are public.
- `src/app/actions.ts` — server actions (mutations). They call the API with the user's token.
- `src/lib` — env access, Supabase clients, the server-only API client and viewer/session resolution.
- `src/components/ui` — shadcn/ui-style primitives built on Radix; `data/` and `layout/` compose them.

All API calls happen on the server, so access tokens are never exposed to client-side JavaScript beyond
Supabase's own session cookie, and the browser never talks to the API directly.
