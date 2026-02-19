import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/admin/:path*",
        destination: `${process.env.AGENT_API_URL || "http://localhost:8080"}/admin/:path*`,
      },
      {
        source: "/api/health",
        destination: `${process.env.AGENT_API_URL || "http://localhost:8080"}/health`,
      },
    ];
  },
};

export default nextConfig;
