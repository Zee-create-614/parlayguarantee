/** @type {import('next').NextConfig} */
const nextConfig = {
  eslint: {
    // Disable ESLint during build for now
    ignoreDuringBuilds: true,
  },
  typescript: {
    // Disable type checking during build for now
    ignoreBuildErrors: true,
  },
}

module.exports = nextConfig