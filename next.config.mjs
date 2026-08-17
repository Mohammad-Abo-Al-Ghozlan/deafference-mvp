/** @type {import('next').NextConfig} */
const nextConfig = {
  // Type errors now fail the build (the 5 pre-existing errors are fixed). Keeping
  // this off restores the static-safety gate — fix types rather than re-enabling.
  typescript: {
    ignoreBuildErrors: false,
  },
  images: {
    unoptimized: true,
  },
}

export default nextConfig
