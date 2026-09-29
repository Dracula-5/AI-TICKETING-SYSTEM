import LegalPageLayout from "../components/LegalPageLayout";

export default function SecurityPolicy() {
  return (
    <LegalPageLayout title="Security" updated="August 2026">
      <p>
        A factual summary of the security measures actually built into this platform.
      </p>

      <h2>Passwords</h2>
      <p>
        Passwords are hashed with bcrypt before storage. We never store or log plain-text passwords, and
        we can't recover your existing password — only reset it via a new one that you choose from Settings.
      </p>

      <h2>Authentication</h2>
      <p>
        Sessions use signed JWT tokens (HS256) with an expiry. Tokens are kept in your browser's
        <code> sessionStorage</code>, not a cookie, and are cleared when you close the tab.
      </p>

      <h2>Rate limiting</h2>
      <p>
        Login and registration endpoints are rate-limited per IP address to resist brute-force and spam
        attempts, on top of a general rate limit applied across the whole API.
      </p>

      <h2>Transport and response headers</h2>
      <p>
        Every API response includes <code>X-Content-Type-Options: nosniff</code>,{" "}
        <code>X-Frame-Options: DENY</code>, and a strict <code>Referrer-Policy</code> header. Cross-origin
        requests are restricted to an explicit allowlist configured by the deployment operator.
      </p>

      <h2>Multi-tenant data isolation</h2>
      <p>
        Every data query is scoped to your organization at the database-query level, not just hidden in
        the interface — cross-organization access attempts are rejected by the server.
      </p>

      <h2>Reporting a concern</h2>
      <p>
        If you believe you've found a security issue with this platform, contact your organization's
        administrator.
      </p>
    </LegalPageLayout>
  );
}
