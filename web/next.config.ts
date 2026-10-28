import type { NextConfig } from "next";

// Origins allowed to frame /embed/*. The Atlan tenant origin is added at
// deploy time through NEXT_PUBLIC_ATLAN_ORIGINS (space or comma separated).
const extraOrigins = (process.env.NEXT_PUBLIC_ATLAN_ORIGINS ?? "")
  .split(/[\s,]+/)
  .filter((o) => /^https?:\/\/[\w.*-]+(:\d+)?$/.test(o));

// Production frames only the configured tenant origins; development also allows
// the local shell simulator and any Atlan origin.
const embedFrameAncestors = (
  process.env.NODE_ENV === "production"
    ? extraOrigins.length ? extraOrigins : ["'none'"]
    : ["'self'", "https://*.atlan.com", ...extraOrigins]
).join(" ");

const nextConfig: NextConfig = {
  async headers() {
    return [
      {
        // Embedded views may be framed by Atlan; no X-Frame-Options here
        // because it cannot express an allowlist and would override CSP.
        source: "/embed/:path*",
        headers: [
          {
            key: "Content-Security-Policy",
            value: `frame-ancestors ${embedFrameAncestors}`,
          },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "no-referrer" },
        ],
      },
      {
        // Everything else refuses to be framed at all.
        source: "/((?!embed/).*)",
        headers: [
          { key: "Content-Security-Policy", value: "frame-ancestors 'none'" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "no-referrer" },
        ],
      },
    ];
  },
};

export default nextConfig;
