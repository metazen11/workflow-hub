/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [
      // PostgREST - Direct DB access for simple CRUD
      {
        source: '/postgrest/:path*',
        destination: 'http://localhost:3000/:path*',
      },
      // Django - Business logic and actions
      {
        source: '/api/:path*',
        destination: 'http://localhost:8000/api/:path*',
      },
    ]
  },
}

module.exports = nextConfig
