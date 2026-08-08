import LegalPageLayout from "../components/LegalPageLayout";

export default function TermsOfService() {
  return (
    <LegalPageLayout title="Terms of Service" updated="August 2026">
      <p>
        By using this platform, you agree to the following terms. This is a demonstration application —
        these terms describe how it actually behaves, not a generic template.
      </p>

      <h2>Demonstration marketplace</h2>
      <p>
        Products, prices, and vendor shops on this platform are for demonstration purposes. Placing an
        order does not constitute a real purchase, and no real payment is captured or processed. Vendor
        listings, stock levels, and pricing are illustrative.
      </p>

      <h2>Negotiated pricing</h2>
      <p>
        Marketplace prices are negotiable through the built-in bargaining chat. A vendor's response in
        that chat may come from a human, a rule-based pricing engine, or — only when a vendor has
        explicitly enabled it for a specific product — an AI assistant. Messages from the assistant are
        always labeled as such, so you can tell who or what you're negotiating with.
      </p>

      <h2>Support tickets and SLA windows</h2>
      <p>
        Ticket priority is auto-classified and assigned a target response window (2 to 24 hours depending
        on urgency). This window reflects simulated business logic for demonstration purposes — it is not
        a binding service-level commitment.
      </p>

      <h2>Acceptable use</h2>
      <p>
        Don't use this platform to submit false, abusive, or unlawful content in tickets, comments, product
        listings, or negotiation messages. Accounts found doing so may be disabled by an administrator.
      </p>

      <h2>Account responsibility</h2>
      <p>
        You're responsible for keeping your password confidential and for activity that occurs under your
        account. If you believe your account has been compromised, change your password immediately from
        Settings.
      </p>

      <h2>Changes</h2>
      <p>
        These terms may be updated as the platform evolves. Continued use after a change means you accept
        the updated terms.
      </p>
    </LegalPageLayout>
  );
}
