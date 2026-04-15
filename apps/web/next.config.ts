import type { NextConfig } from "next";

const apiProxyTarget = process.env.AURA_API_PROXY_TARGET || process.env.AURA_API_BASE_URL || "http://localhost:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: `${apiProxyTarget}/api/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;
