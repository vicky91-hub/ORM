// Vercel Edge Middleware — free-tier password gate (Hobby plan has no native Deployment
// Password Protection, that's Pro-only; this is the standard workaround).
export const config = { matcher: '/:path*' };

// Set in Vercel → Project → Settings → Environment Variables. Without them nobody gets in.
const USERNAME = process.env.ORM_AUTH_USER || '';
const PASSWORD = process.env.ORM_AUTH_PASSWORD || '';

export default function middleware(request) {
  // CloseLoop (proxied to Railway via vercel.json) has its own login; old /brandlens links
  // pass through to their redirect.
  const { pathname } = new URL(request.url);
  if (/^\/(closeloop|brandlens)(\/|$)/.test(pathname)) return;
  const authHeader = request.headers.get('authorization');
  if (USERNAME && PASSWORD && authHeader && authHeader.startsWith('Basic ')) {
    try {
      const decoded = atob(authHeader.slice(6));
      const sepIdx = decoded.indexOf(':');
      const username = decoded.slice(0, sepIdx);
      const password = decoded.slice(sepIdx + 1);
      if (username === USERNAME && password === PASSWORD) return;
    } catch (e) {}
  }
  return new Response('Authentication required', {
    status: 401,
    headers: { 'WWW-Authenticate': 'Basic realm="ORM Performance Report"' },
  });
}
