import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The journal is read from disk at request time. Next only bundles files
  // it can trace statically, and a path built at runtime is not traceable,
  // so the serverless function ships without them and every page renders
  // "0 decisions". Name them explicitly.
  outputFileTracingIncludes: {
    "/": ["./data/**"],
    "/api/decisions": ["./data/**"],
  },
  /* config options here */
};

export default nextConfig;
