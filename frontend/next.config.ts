import type { NextConfig } from "next";

const configuredDevOrigins = process.env.NEXT_ALLOWED_DEV_ORIGINS?.split(",")
  .map((origin) => origin.trim())
  .filter(Boolean);

const config: NextConfig = {
  allowedDevOrigins: [
    "172.18.*.*",
    "host.docker.internal",
    ...(configuredDevOrigins ?? []),
  ],
};

export default config;
