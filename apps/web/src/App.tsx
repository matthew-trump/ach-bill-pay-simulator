import { useCallback, useEffect, useMemo, useState } from "react";

const billpayApiUrl = import.meta.env.VITE_BILLPAY_API_URL ?? "http://127.0.0.1:8501";
const mockProviderApiUrl =
  import.meta.env.VITE_MOCK_PROVIDER_API_URL ?? "http://127.0.0.1:8502";
const providerAuthHeader =
  import.meta.env.VITE_MOCK_PROVIDER_API_KEY ?? "dev_mock_provider_key_do_not_use_for_real_systems";

type Tab =
  | "dashboard"
  | "accounts"
  | "billers"
  | "bills"
  | "pay"
  | "detail"
  | "sandbox"
  | "operations";

type User = {
  id: string;
  email: string;
  name: string;
  status: string;
};

type BankAccount = {
  id: string;
  user_id: string;
  bank_name: string;
  account_type: string;
  last4: string;
  verification_status: string;
};

type Biller = {
  id: string;
  name: string;
  status: string;
};

type BillerAccount = {
  id: string;
  biller_id: string;
  customer_reference: string;
  display_mask: string;
  nickname: string;
};

type Bill = {
  id: string;
  biller_account_id: string;
  amount: string;
  due_date: string;
  description: string;
  status: string;
};

type PaymentLeg = {
  id: string;
  leg_type: string;
  provider_transfer_id: string;
  status: string;
  return_code: string | null;
};

type LedgerEntry = {
  id: string;
  ledger_account_id: string;
  debit_cents: number;
  credit_cents: number;
};

type LedgerTransaction = {
  id: string;
  transaction_type: string;
  description: string;
  source_id: string;
  entries: LedgerEntry[];
};

type PaymentOrder = {
  id: string;
  user_id: string;
  bill_id: string;
  funding_account_id: string;
  amount: string;
  status: string;
  idempotency_key: string;
  legs: PaymentLeg[];
  ledger_transactions: LedgerTransaction[];
};

type ProviderInboxEvent = {
  id: string;
  provider_event_id: string;
  event_type: string;
  payment_leg_id: string | null;
  processed: boolean;
  processing_error: string | null;
};

type LedgerAccountBalance = {
  id: string;
  name: string;
  account_type: string;
  normal_balance: string;
  debit_cents: number;
  credit_cents: number;
  balance_cents: number;
};

type LedgerInvariant = {
  balanced: boolean;
  unbalanced_transaction_ids: string[];
};

type Overview = {
  users: User[];
  bank_accounts: BankAccount[];
  billers: Biller[];
  biller_accounts: BillerAccount[];
  bills: Bill[];
  payment_orders: PaymentOrder[];
};

type ProviderEvent = {
  id: string;
  type: string;
  transfer_id: string;
  payload: Record<string, unknown>;
};

const emptyOverview: Overview = {
  users: [],
  bank_accounts: [],
  billers: [],
  biller_accounts: [],
  bills: [],
  payment_orders: [],
};

const tabLabels: Record<Tab, string> = {
  dashboard: "Dashboard",
  accounts: "Bank accounts",
  billers: "Billers",
  bills: "Bills",
  pay: "Pay bill",
  detail: "Payment detail",
  sandbox: "Sandbox",
  operations: "Operations",
};

export function App() {
  const [activeTab, setActiveTab] = useState<Tab>("dashboard");
  const [overview, setOverview] = useState<Overview>(emptyOverview);
  const [providerEvents, setProviderEvents] = useState<ProviderInboxEvent[]>([]);
  const [ledgerAccounts, setLedgerAccounts] = useState<LedgerAccountBalance[]>([]);
  const [ledgerInvariant, setLedgerInvariant] = useState<LedgerInvariant | null>(null);
  const [selectedPaymentId, setSelectedPaymentId] = useState<string>("");
  const [authorizationAccepted, setAuthorizationAccepted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("Seed fictional data to begin.");
  const [error, setError] = useState("");

  const selectedPayment = useMemo(
    () =>
      overview.payment_orders.find((payment) => payment.id === selectedPaymentId) ??
      overview.payment_orders[0],
    [overview.payment_orders, selectedPaymentId],
  );
  const selectedBill = overview.bills[0];
  const selectedFundingAccount = overview.bank_accounts[0];
  const selectedUser = overview.users[0];

  const refreshAll = useCallback(async () => {
    setError("");
    try {
      const [nextOverview, nextEvents, nextLedgerAccounts, nextInvariant] = await Promise.all([
        apiJson<Overview>(`${billpayApiUrl}/dev/overview`),
        apiJson<ProviderInboxEvent[]>(`${billpayApiUrl}/v1/provider-events`),
        apiJson<LedgerAccountBalance[]>(`${billpayApiUrl}/v1/ledger/accounts`),
        apiJson<LedgerInvariant>(`${billpayApiUrl}/v1/ledger/invariants`),
      ]);
      setOverview(nextOverview);
      setProviderEvents(nextEvents);
      setLedgerAccounts(nextLedgerAccounts);
      setLedgerInvariant(nextInvariant);
      if (!selectedPaymentId && nextOverview.payment_orders[0]) {
        setSelectedPaymentId(nextOverview.payment_orders[0].id);
      }
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }, [selectedPaymentId]);

  useEffect(() => {
    void refreshAll();
  }, [refreshAll]);

  async function seedData() {
    await runAction("Seeded fictional provider and bill-pay data.", async () => {
      await apiJson<Record<string, string>>(`${mockProviderApiUrl}/_sandbox/seed-billpay-accounts`, {
        method: "POST",
      });
      await apiJson<Record<string, string>>(`${billpayApiUrl}/dev/seed`, { method: "POST" });
      setAuthorizationAccepted(false);
    });
  }

  async function submitPayment() {
    if (!selectedUser || !selectedBill || !selectedFundingAccount || !authorizationAccepted) {
      setError("Select seeded data and accept the simulated authorization first.");
      return;
    }
    await runAction("Payment order submitted.", async () => {
      const payment = await apiJson<PaymentOrder>(`${billpayApiUrl}/v1/payment-orders`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: selectedUser.id,
          bill_id: selectedBill.id,
          funding_account_id: selectedFundingAccount.id,
          idempotency_key: `web-${Date.now()}`,
          authorization_text: "I authorize this simulated ACH debit.",
        }),
      });
      setSelectedPaymentId(payment.id);
      setActiveTab("detail");
      setAuthorizationAccepted(false);
    });
  }

  async function sandboxAction(
    leg: PaymentLeg,
    action: "advance" | "fail" | "return" | "duplicate",
  ) {
    await runAction(`Sandbox ${action} completed for ${leg.leg_type} leg.`, async () => {
      if (action === "duplicate") {
        const event = await apiJson<ProviderEvent>(
          `${mockProviderApiUrl}/_sandbox/transfers/${leg.provider_transfer_id}/duplicate-last-webhook`,
          { method: "POST" },
        );
        await forwardProviderPayload(event.payload);
        return;
      }

      const body =
        action === "return"
          ? { headers: { "Content-Type": "application/json" }, body: JSON.stringify({ return_code: "R01" }) }
          : {};
      await apiJson<unknown>(`${mockProviderApiUrl}/_sandbox/transfers/${leg.provider_transfer_id}/${action}`, {
        method: "POST",
        ...body,
      });
      await forwardLatestProviderEvent(leg.provider_transfer_id);
    });
  }

  async function sendOutOfOrderEvents(leg: PaymentLeg) {
    await runAction("Out-of-order provider events forwarded.", async () => {
      const events = await apiJson<ProviderEvent[]>(
        `${mockProviderApiUrl}/_sandbox/transfers/${leg.provider_transfer_id}/send-out-of-order-events`,
        { method: "POST" },
      );
      for (const event of events) {
        await forwardProviderPayload(event.payload);
      }
    });
  }

  async function forwardLatestProviderEvent(providerTransferId: string) {
    const events = await apiJson<ProviderEvent[]>(`${mockProviderApiUrl}/v1/events`, {
      headers: { Authorization: `Bearer ${providerAuthHeader}` },
    });
    const event = events
      .filter((candidate) => candidate.transfer_id === providerTransferId)
      .reverse()[0];
    if (!event) {
      throw new Error("Provider event was not found after sandbox action.");
    }
    await forwardProviderPayload(event.payload);
  }

  async function forwardProviderPayload(payload: Record<string, unknown>) {
    await apiJson(`${billpayApiUrl}/v1/provider-events`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  }

  async function runAction(successMessage: string, action: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await action();
      await refreshAll();
      setNotice(successMessage);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="app-shell">
      <div className="simulation-banner">
        Simulation only. Use fictional test data. Do not enter real bank information.
      </div>

      <header className="topbar">
        <div>
          <p className="eyebrow">Milestone 6</p>
          <h1>ACH Bill Pay Simulator</h1>
        </div>
        <div className="topbar-actions">
          <button type="button" onClick={() => void refreshAll()} disabled={busy}>
            Refresh
          </button>
          <button type="button" className="primary" onClick={() => void seedData()} disabled={busy}>
            Seed data
          </button>
        </div>
      </header>

      <nav className="tabs" aria-label="Application sections">
        {(Object.keys(tabLabels) as Tab[]).map((tab) => (
          <button
            key={tab}
            type="button"
            className={activeTab === tab ? "active" : ""}
            onClick={() => setActiveTab(tab)}
          >
            {tabLabels[tab]}
          </button>
        ))}
      </nav>

      {(notice || error) && (
        <section className="status-strip" aria-live="polite">
          {notice && <span>{notice}</span>}
          {error && <strong>{error}</strong>}
        </section>
      )}

      <section className="workspace">
        {activeTab === "dashboard" && (
          <Dashboard overview={overview} onSelectPayment={selectPayment} />
        )}
        {activeTab === "accounts" && <Accounts accounts={overview.bank_accounts} />}
        {activeTab === "billers" && (
          <Billers billers={overview.billers} billerAccounts={overview.biller_accounts} />
        )}
        {activeTab === "bills" && (
          <Bills bills={overview.bills} billerAccounts={overview.biller_accounts} />
        )}
        {activeTab === "pay" && (
          <PayBill
            bill={selectedBill}
            account={selectedFundingAccount}
            accepted={authorizationAccepted}
            busy={busy}
            onAcceptedChange={setAuthorizationAccepted}
            onSubmit={() => void submitPayment()}
          />
        )}
        {activeTab === "detail" && (
          <PaymentDetail
            payment={selectedPayment}
            events={providerEvents}
            onSelectPayment={(paymentId) => setSelectedPaymentId(paymentId)}
            payments={overview.payment_orders}
          />
        )}
        {activeTab === "sandbox" && (
          <Sandbox
            payment={selectedPayment}
            busy={busy}
            onAction={(leg, action) => void sandboxAction(leg, action)}
            onOutOfOrder={(leg) => void sendOutOfOrderEvents(leg)}
          />
        )}
        {activeTab === "operations" && (
          <Operations
            events={providerEvents}
            ledgerAccounts={ledgerAccounts}
            ledgerInvariant={ledgerInvariant}
          />
        )}
      </section>
    </main>
  );

  function selectPayment(paymentId: string) {
    setSelectedPaymentId(paymentId);
    setActiveTab("detail");
  }
}

function Dashboard({
  overview,
  onSelectPayment,
}: {
  overview: Overview;
  onSelectPayment: (paymentId: string) => void;
}) {
  const pending = overview.payment_orders.filter((payment) =>
    ["funding_pending", "delivery_pending"].includes(payment.status),
  );
  const completed = overview.payment_orders.filter((payment) => payment.status === "delivered");
  return (
    <div className="panel-grid">
      <Metric title="Bills due" value={overview.bills.filter((bill) => bill.status === "due").length} />
      <Metric title="Pending payments" value={pending.length} />
      <Metric title="Completed payments" value={completed.length} />
      <section className="panel wide">
        <h2>Recent payments</h2>
        <PaymentList payments={overview.payment_orders} onSelectPayment={onSelectPayment} />
      </section>
    </div>
  );
}

function Accounts({ accounts }: { accounts: BankAccount[] }) {
  return (
    <section className="panel">
      <h2>Fictional bank accounts</h2>
      <div className="item-list">
        {accounts.map((account) => (
          <article key={account.id} className="list-item">
            <strong>{account.bank_name}</strong>
            <span>{account.account_type} ending {account.last4}</span>
            <Status value={account.verification_status} />
          </article>
        ))}
      </div>
    </section>
  );
}

function Billers({
  billers,
  billerAccounts,
}: {
  billers: Biller[];
  billerAccounts: BillerAccount[];
}) {
  return (
    <section className="panel">
      <h2>Billers</h2>
      <div className="item-list">
        {billers.map((biller) => {
          const account = billerAccounts.find((candidate) => candidate.biller_id === biller.id);
          return (
            <article key={biller.id} className="list-item">
              <strong>{biller.name}</strong>
              <span>{account ? `${account.nickname} ${account.display_mask}` : "No account"}</span>
              <Status value={biller.status} />
            </article>
          );
        })}
      </div>
    </section>
  );
}

function Bills({
  bills,
  billerAccounts,
}: {
  bills: Bill[];
  billerAccounts: BillerAccount[];
}) {
  return (
    <section className="panel">
      <h2>Bills</h2>
      <div className="item-list">
        {bills.map((bill) => {
          const account = billerAccounts.find(
            (candidate) => candidate.id === bill.biller_account_id,
          );
          return (
            <article key={bill.id} className="list-item">
              <strong>{bill.description}</strong>
              <span>{account?.nickname ?? bill.biller_account_id}</span>
              <span>{formatDollars(Number(bill.amount) * 100)} due {bill.due_date}</span>
              <Status value={bill.status} />
            </article>
          );
        })}
      </div>
    </section>
  );
}

function PayBill({
  bill,
  account,
  accepted,
  busy,
  onAcceptedChange,
  onSubmit,
}: {
  bill: Bill | undefined;
  account: BankAccount | undefined;
  accepted: boolean;
  busy: boolean;
  onAcceptedChange: (accepted: boolean) => void;
  onSubmit: () => void;
}) {
  return (
    <section className="panel form-panel">
      <h2>Pay bill</h2>
      <dl className="detail-list">
        <dt>Bill</dt>
        <dd>{bill ? `${bill.description} ${formatDollars(Number(bill.amount) * 100)}` : "Seed data first"}</dd>
        <dt>Funding account</dt>
        <dd>{account ? `${account.bank_name} ending ${account.last4}` : "Seed data first"}</dd>
      </dl>
      <label className="check-row">
        <input
          type="checkbox"
          checked={accepted}
          onChange={(event) => onAcceptedChange(event.target.checked)}
        />
        <span>I authorize this simulated ACH debit for fictional test data.</span>
      </label>
      <button type="button" className="primary" disabled={!bill || !account || !accepted || busy} onClick={onSubmit}>
        Submit payment order
      </button>
    </section>
  );
}

function PaymentDetail({
  payment,
  payments,
  events,
  onSelectPayment,
}: {
  payment: PaymentOrder | undefined;
  payments: PaymentOrder[];
  events: ProviderInboxEvent[];
  onSelectPayment: (paymentId: string) => void;
}) {
  if (!payment) {
    return <EmptyPanel title="Payment detail" message="Submit a payment order to inspect it." />;
  }
  const legIds = new Set(payment.legs.map((leg) => leg.id));
  const matchingEvents = events.filter((event) => event.payment_leg_id && legIds.has(event.payment_leg_id));
  return (
    <div className="stack">
      <section className="panel">
        <div className="panel-heading">
          <h2>Payment detail</h2>
          <select value={payment.id} onChange={(event) => onSelectPayment(event.target.value)}>
            {payments.map((candidate) => (
              <option key={candidate.id} value={candidate.id}>
                {candidate.id}
              </option>
            ))}
          </select>
        </div>
        <dl className="detail-list">
          <dt>Status</dt>
          <dd><Status value={payment.status} /></dd>
          <dt>Amount</dt>
          <dd>{formatDollars(Number(payment.amount) * 100)}</dd>
          <dt>Idempotency key</dt>
          <dd>{payment.idempotency_key}</dd>
        </dl>
      </section>
      <section className="panel">
        <h2>Legs</h2>
        <div className="item-list">
          {payment.legs.map((leg) => (
            <article key={leg.id} className="list-item">
              <strong>{leg.leg_type}</strong>
              <span>{leg.provider_transfer_id}</span>
              <Status value={leg.return_code ? `${leg.status} ${leg.return_code}` : leg.status} />
            </article>
          ))}
        </div>
      </section>
      <section className="panel">
        <h2>Provider events</h2>
        <EventList events={matchingEvents} />
      </section>
      <section className="panel">
        <h2>Ledger entries</h2>
        <LedgerTransactions transactions={payment.ledger_transactions} />
      </section>
    </div>
  );
}

function Sandbox({
  payment,
  busy,
  onAction,
  onOutOfOrder,
}: {
  payment: PaymentOrder | undefined;
  busy: boolean;
  onAction: (leg: PaymentLeg, action: "advance" | "fail" | "return" | "duplicate") => void;
  onOutOfOrder: (leg: PaymentLeg) => void;
}) {
  if (!payment) {
    return <EmptyPanel title="Sandbox controls" message="Submit a payment before using controls." />;
  }
  return (
    <section className="panel">
      <h2>Sandbox controls</h2>
      <div className="item-list">
        {payment.legs.map((leg) => (
          <article key={leg.id} className="sandbox-row">
            <div>
              <strong>{leg.leg_type}</strong>
              <span>{leg.provider_transfer_id}</span>
              <Status value={leg.status} />
            </div>
            <div className="button-row">
              <button type="button" disabled={busy} onClick={() => onAction(leg, "advance")}>
                Advance
              </button>
              <button type="button" disabled={busy} onClick={() => onAction(leg, "fail")}>
                Fail
              </button>
              <button type="button" disabled={busy} onClick={() => onAction(leg, "return")}>
                Return R01
              </button>
              <button type="button" disabled={busy} onClick={() => onAction(leg, "duplicate")}>
                Duplicate event
              </button>
              <button type="button" disabled={busy} onClick={() => onOutOfOrder(leg)}>
                Out of order
              </button>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function Operations({
  events,
  ledgerAccounts,
  ledgerInvariant,
}: {
  events: ProviderInboxEvent[];
  ledgerAccounts: LedgerAccountBalance[];
  ledgerInvariant: LedgerInvariant | null;
}) {
  const failedEvents = events.filter((event) => !event.processed || event.processing_error);
  return (
    <div className="stack">
      <section className="panel">
        <h2>Ledger invariant</h2>
        <p className={ledgerInvariant?.balanced ? "ok-text" : "error-text"}>
          {ledgerInvariant?.balanced ? "All ledger transactions balance." : "Unbalanced transaction detected."}
        </p>
      </section>
      <section className="panel">
        <h2>Ledger accounts</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Account</th>
                <th>Debits</th>
                <th>Credits</th>
                <th>Balance</th>
              </tr>
            </thead>
            <tbody>
              {ledgerAccounts.map((account) => (
                <tr key={account.id}>
                  <td>{account.name}</td>
                  <td>{formatDollars(account.debit_cents)}</td>
                  <td>{formatDollars(account.credit_cents)}</td>
                  <td>{formatDollars(account.balance_cents)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section className="panel">
        <h2>Provider event processing</h2>
        {failedEvents.length === 0 ? <p>No provider event processing failures.</p> : <EventList events={failedEvents} />}
      </section>
    </div>
  );
}

function PaymentList({
  payments,
  onSelectPayment,
}: {
  payments: PaymentOrder[];
  onSelectPayment: (paymentId: string) => void;
}) {
  if (payments.length === 0) {
    return <p>No payments submitted yet.</p>;
  }
  return (
    <div className="item-list">
      {payments.map((payment) => (
        <button
          type="button"
          className="list-button"
          key={payment.id}
          onClick={() => onSelectPayment(payment.id)}
        >
          <span>{payment.id}</span>
          <strong>{formatDollars(Number(payment.amount) * 100)}</strong>
          <Status value={payment.status} />
        </button>
      ))}
    </div>
  );
}

function LedgerTransactions({ transactions }: { transactions: LedgerTransaction[] }) {
  if (transactions.length === 0) {
    return <p>No ledger entries posted yet.</p>;
  }
  return (
    <div className="item-list">
      {transactions.map((transaction) => (
        <article key={transaction.id} className="ledger-card">
          <strong>{transaction.transaction_type}</strong>
          <span>{transaction.description}</span>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Account</th>
                  <th>Debit</th>
                  <th>Credit</th>
                </tr>
              </thead>
              <tbody>
                {transaction.entries.map((entry) => (
                  <tr key={entry.id}>
                    <td>{entry.ledger_account_id}</td>
                    <td>{entry.debit_cents ? formatDollars(entry.debit_cents) : ""}</td>
                    <td>{entry.credit_cents ? formatDollars(entry.credit_cents) : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>
      ))}
    </div>
  );
}

function EventList({ events }: { events: ProviderInboxEvent[] }) {
  if (events.length === 0) {
    return <p>No events recorded.</p>;
  }
  return (
    <div className="item-list">
      {events.map((event) => (
        <article key={event.id} className="list-item">
          <strong>{event.event_type}</strong>
          <span>{event.provider_event_id}</span>
          <Status value={event.processed ? "processed" : "unprocessed"} />
          {event.processing_error && <span className="error-text">{event.processing_error}</span>}
        </article>
      ))}
    </div>
  );
}

function Metric({ title, value }: { title: string; value: number }) {
  return (
    <section className="metric">
      <span>{title}</span>
      <strong>{value}</strong>
    </section>
  );
}

function EmptyPanel({ title, message }: { title: string; message: string }) {
  return (
    <section className="panel">
      <h2>{title}</h2>
      <p>{message}</p>
    </section>
  );
}

function Status({ value }: { value: string }) {
  return <span className={`status status-${statusTone(value)}`}>{value}</span>;
}

function statusTone(value: string) {
  if (value.includes("failed") || value.includes("returned") || value.includes("action_required")) {
    return "bad";
  }
  if (value.includes("succeeded") || value.includes("delivered") || value.includes("processed")) {
    return "good";
  }
  return "neutral";
}

async function apiJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`${response.status} ${response.statusText}: ${text}`);
  }
  return (await response.json()) as T;
}

function formatDollars(cents: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
  }).format(cents / 100);
}

function errorMessage(caught: unknown) {
  return caught instanceof Error ? caught.message : "Unexpected error";
}
