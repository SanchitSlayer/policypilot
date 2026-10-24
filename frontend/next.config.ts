import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Self-contained server (server.js + minimal node_modules) for the production image.
  output: "standalone",
  poweredByHeader: false,
};

export default nextConfig;
