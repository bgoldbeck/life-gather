# Cloudflare test site

Worker and Cloudflare Container setup for a private LifeGather test site. Setup,
costs, limits and removal: [docs/CLOUDFLARE_TEST_SITE.md](../../docs/CLOUDFLARE_TEST_SITE.md).

```
npm install
npm run check      # TypeScript and unit tests
npm run dry-run    # bundle the Worker without Docker or a Cloudflare account
```

The Python app never imports anything from here; self-hosting does not use it.
