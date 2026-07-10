// The FastAPI backend. The browser never talks to it directly; instead the
// Next.js server proxies these exact API paths to it (rewrites below), so the
// whole app is reachable through a single origin / single ngrok tunnel.
const BACKEND_ORIGIN = process.env.BACKEND_ORIGIN || "http://127.0.0.1:8000";

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  webpack(config, { dev }) {
    // Next 14 applies Node export conditions while compiling Web Workers.
    // Force Transformers.js to its browser bundle so ONNX Runtime uses web WASM/WebGPU.
    config.resolve.alias["@huggingface/transformers$"] = path.resolve(
      process.cwd(),
      "node_modules/@huggingface/transformers/dist/transformers.web.js"
    );
    if (!dev) {
      // ONNX Runtime ships pre-minified ESM worker assets containing import.meta.
      // Next 14's Terser pass incorrectly parses those assets as classic scripts.
      // The runtime assets are already minified upstream; disabling the extra
      // webpack minification pass preserves their required module semantics.
      config.optimization.minimize = false;
    }
    return config;
  },
  async rewrites() {
    return [
      { source: "/chat", destination: `${BACKEND_ORIGIN}/chat` },
      { source: "/voice", destination: `${BACKEND_ORIGIN}/voice` },
      { source: "/warmup", destination: `${BACKEND_ORIGIN}/warmup` },
      { source: "/health", destination: `${BACKEND_ORIGIN}/health` },
      // Only the dashboard API sub-paths — /dashboard itself is a Next page.
      { source: "/dashboard/stats", destination: `${BACKEND_ORIGIN}/dashboard/stats` },
      { source: "/dashboard/recent", destination: `${BACKEND_ORIGIN}/dashboard/recent` },
    ];
  },
};

export default nextConfig;
import path from "node:path";
