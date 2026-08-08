import LegalPageLayout from "../components/LegalPageLayout";

export default function PrivacyPolicy() {
  return (
    <LegalPageLayout title="Privacy Policy" updated="August 2026">
      <p>
        This is a demonstration ticketing and marketplace platform. This policy explains, plainly, what
        data the app collects and how it's used — without overclaiming protections or processes the app
        doesn't actually implement.
      </p>

      <h2>What we collect</h2>
      <ul>
        <li>Account details: name, email, and role (customer, provider, vendor, or admin).</li>
        <li>Your password, stored as a bcrypt hash — never in plain text, and never visible to anyone, including administrators.</li>
        <li>If you register a vendor shop: shop name, phone number, and shop address.</li>
        <li>If you place an order: the delivery address you enter at checkout.</li>
        <li>Ticket content: titles, descriptions, comments, and price-negotiation messages you submit.</li>
        <li>Notification history related to your account activity.</li>
      </ul>

      <h2>What we don't collect</h2>
      <p>
        We don't use cookies. Your session is a bearer token stored in your browser's <code>sessionStorage</code>,
        which means it's cleared automatically when you close the tab — there's no persistent tracking
        identifier that survives across sessions.
      </p>

      <h2>Payments</h2>
      <p>
        This is a demonstration marketplace. No real payment processing occurs anywhere in this app —
        placing an "order" does not charge a card or move real money. Treat any pricing or checkout flow
        here as illustrative, not a real transaction.
      </p>

      <h2>Third-party sharing</h2>
      <p>
        Ticket category and priority classification runs entirely on our own server using local keyword
        matching — nothing is sent to a third party for that. Marketplace price negotiation can optionally
        be assisted by Anthropic's Claude API, but only for a specific product a vendor has explicitly
        enabled for it, and only when the deployment operator has configured an API key — this is off by
        default. When active, negotiation messages for that conversation may be sent to Anthropic to
        generate a response.
      </p>

      <h2>Multi-tenant isolation</h2>
      <p>
        Your data is scoped to your organization (tenant). Every request is checked to ensure it can only
        read or modify data belonging to your own organization.
      </p>

      <h2>Account deletion</h2>
      <p>
        There's no self-service "delete my account" button today. If you'd like your data removed, contact
        your organization's administrator.
      </p>
    </LegalPageLayout>
  );
}
