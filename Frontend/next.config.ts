import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Kept on deliberately. Any advice to disable this was a react-three-fiber
  // workaround; there is no 3D in this app and double-invoked effects are a
  // useful check on the SSE / abort cleanup paths.
  reactStrictMode: true,
};

export default nextConfig;
