import { defineConfig } from 'orval'

// Typed TanStack Query hooks generated from the backend's OpenAPI document.
// Regenerate with `npm run generate:api` after any API change; openapi.json
// itself comes from backend/scripts/export-openapi.py.
export default defineConfig({
  tradingagents: {
    input: {
      target: './openapi.json',
    },
    output: {
      mode: 'tags-split',
      target: './src/api/generated',
      schemas: './src/api/generated/model',
      client: 'react-query',
      httpClient: 'axios',
      clean: true,
      prettier: false,
      override: {
        // Route every request through the app's configured axios instance so
        // the auth header and 401-refresh interceptors still apply, and so
        // hooks yield the response body rather than a wrapped AxiosResponse.
        mutator: {
          path: './src/api/mutator.ts',
          name: 'customInstance',
        },
        query: {
          signal: true,
        },
      },
    },
  },
})
