# 🎨 TradingAgents Frontend

A modern, high-fidelity investment decision-making dashboard built with **React**, **TypeScript**, **Tailwind CSS**, and **Vite**. It features a glassmorphic dark-themed layout, interactive charts, and real-time streaming of multi-agent execution steps and generated reports over WebSockets.

---

## 🚀 Key Features & Implementation Details

*   **Responsive Glassmorphic UI:** Styled with a premium, sleek dark mode theme using custom Tailwind utility classes, backdrop filters, and subtle hover animations.
*   **Real-Time WebSocket Streams:** Subscribes to backend multi-agent progress event channels to stream live node executions (e.g. tracking when the Bull/Bear Researchers start debating) and chunk-by-chunk markdown report generation.
*   **Dual-Language Localization (i18n):** Supports fully integrated translation toggling between **English** and **Turkish**, persisted locally via `localStorage` (located in [src/i18n/](src/i18n)).
*   **Interactive Financial Charts:** Renders candlestick price charts, technical analysis overlays (MACD, RSI, Moving Averages), and mock trading portfolio returns using **Recharts**.
*   **Developer Proxy Configuration:** Vite dev-server configures transparent reverse proxy routes (`/api`, `/auth`, `/ws`) to map API calls directly to the local FastAPI port (`8000`) without CORS headaches.

---

## 📁 Project Structure

The React source files live inside [src/](src):

```text
frontend/
├── public/                 # Static assets (favicons, fonts, fallback icons)
├── src/
│   ├── assets/             # Images, theme illustrations, and local SVGs
│   ├── components/         # Reusable structural layout elements
│   │   ├── Layout.tsx      # Sidebar navigation, header, language toggle, and auth wrapper
│   │   └── UpdateBanner.tsx# Alert panel notifying the user of available app updates
│   ├── contexts/           # React context providers (AuthContext, ThemeContext, SettingsContext)
│   ├── hooks/              # Custom hooks (WebSocket connectors, API queries, local storage states)
│   ├── i18n/               # Multi-language translation dictionaries (admin, alerts, chart, analysis, etc.)
│   ├── pages/              # Core page views
│   │   ├── Dashboard.tsx   # Portfolio snapshots, active watchlists, and market indicators
│   │   ├── Analysis.tsx    # Multi-agent graph run controls, WebSocket log streams, and report readers
│   │   ├── Chart.tsx       # Fullscreen technical charts with indicators
│   │   ├── MockTrading.tsx # Sandbox paper trading ledger (Buy/Sell, Limit orders, Cash history)
│   │   ├── Alerts.tsx      # Target price and signal change notifications manager
│   │   ├── Performance.tsx # Historical strategy return review charts
│   │   ├── ABTesting.tsx   # Compare performance of different LLM/agent models
│   │   ├── Admin.tsx       # System logs browser and user manager (Admin only)
│   │   └── Settings.tsx    # LLM API keys config, scheduler times, and system updates
│   ├── utils/              # Helper utilities (date formatters, local storage helper, etc.)
│   ├── App.tsx             # Route definitions, route guarding, and translation wrapper
│   └── main.tsx            # Entry point mounting App to the browser DOM
├── index.html              # Core HTML entry template
├── tailwind.config.js      # Custom theme color configurations
└── vite.config.ts          # Vite build config & proxy setups
```

---

## ⚙️ Setup & Local Running

Make sure you have Node.js 20+ installed.

1.  **Navigate to Frontend Directory:**
    ```bash
    cd frontend
    ```
2.  **Install Dependencies:**
    ```bash
    npm install
    ```
3.  **Start Dev Server:**
    ```bash
    npm run dev
    ```
    This launches the dev server on `http://localhost:5173`. Any requests to `/api` or `/ws` will be forwarded automatically to `http://localhost:8000` via the Vite proxy configuration.

---

## 🌐 Localization (i18n)

Translations are split into separate feature files under `src/i18n/` to ensure code maintainability (e.g. [analysis.ts](src/i18n/analysis.ts), [settings.ts](src/i18n/settings.ts)). 

A toggle component inside the main sidebar layout dynamically sets the active locale (`en` / `tr`), which updates the React context and forces a DOM-wide re-render of local dictionary terms.

---

## 📊 Client Production Building

To compile the project down to minified HTML/JS/CSS assets ready for distribution:

```bash
npm run build
```

This generates production assets in the `frontend/dist` directory. The FastAPI backend is configured to serve these files directly when running in production mode, removing the need for a secondary Nginx or Apache server setup.
