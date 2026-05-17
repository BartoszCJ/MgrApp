import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Wyciszamy warning "multiple lockfiles" — root MagisterkaApp tez ma package.json
  // (od `concurrently`), wiec Next.js musi wiedziec ze frontend root to ten folder.
  turbopack: {
    root: path.resolve(__dirname),
  },
};

export default nextConfig;
