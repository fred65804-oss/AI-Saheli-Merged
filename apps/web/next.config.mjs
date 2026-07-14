// The FastAPI backend. The browser never talks to it directly; instead the
// Next.js server proxies these exact API paths to it (rewrites below), so the
// whole app is reachable through a single origin / single ngrok tunnel.
const BACKEND_ORIGIN = process.env.BACKEND_ORIGIN || "http://127.0.0.1:8000";

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      { source: "/chat", destination: `${BACKEND_ORIGIN}/chat` },
      { source: "/voice", destination: `${BACKEND_ORIGIN}/voice` },
      { source: "/warmup", destination: `${BACKEND_ORIGIN}/warmup` },
      { source: "/health", destination: `${BACKEND_ORIGIN}/health` },
      { source: "/meta", destination: `${BACKEND_ORIGIN}/meta` },
      { source: "/helplines", destination: `${BACKEND_ORIGIN}/helplines` },
      { source: "/tools/:path*", destination: `${BACKEND_ORIGIN}/tools/:path*` },
      { source: "/auth/:path*", destination: `${BACKEND_ORIGIN}/auth/:path*` },
      // Analytics API sub-paths — /dashboard itself is a Next page.
      { source: "/analytics/:path*", destination: `${BACKEND_ORIGIN}/analytics/:path*` },
    ];
  },
};

export default nextConfig;
