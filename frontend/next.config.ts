import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Standalone output keeps the production Docker image small.
  output: "standalone",
};

export default nextConfig;
