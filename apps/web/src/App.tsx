const billpayApiUrl = import.meta.env.VITE_BILLPAY_API_URL ?? "http://127.0.0.1:8501";
const mockProviderApiUrl =
  import.meta.env.VITE_MOCK_PROVIDER_API_URL ?? "http://127.0.0.1:8502";

export function App() {
  return (
    <main className="shell">
      <div className="simulation-banner">
        Simulation only. Enter fictional test data. Never enter a real bank account or routing
        number.
      </div>

      <section className="intro">
        <p className="eyebrow">Milestone 5</p>
        <h1>ACH Bill Pay Simulator</h1>
        <p>
          Local-only simulated ACH-like bill-pay system with provider transfers, webhooks, two-leg
          orchestration, and an internal double-entry ledger. Reconciliation and browser workflows
          are intentionally deferred.
        </p>
      </section>

      <section className="service-grid" aria-label="Local services">
        <article>
          <h2>Bill-pay API</h2>
          <p>Health endpoint</p>
          <a href={`${billpayApiUrl}/healthz`}>{billpayApiUrl}/healthz</a>
        </article>
        <article>
          <h2>Simulated provider API</h2>
          <p>Health endpoint</p>
          <a href={`${mockProviderApiUrl}/healthz`}>{mockProviderApiUrl}/healthz</a>
        </article>
        <article>
          <h2>Web UI</h2>
          <p>Vite development server</p>
          <span>http://127.0.0.1:3500</span>
        </article>
      </section>
    </main>
  );
}
