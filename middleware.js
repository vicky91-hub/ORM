// Vercel Edge Middleware — free-tier password gate (Hobby plan has no native Deployment
// Password Protection, that's Pro-only; this is the standard workaround).
export const config = { matcher: '/:path*' };

const USERNAME = 'orm-audit';
const PASSWORD = 'Sumadhura@audit';

export default function middleware(request) {
  const authHeader = request.headers.get('authorization');
  if (authHeader && authHeader.startsWith('Basic ')) {
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
