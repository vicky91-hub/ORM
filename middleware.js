// Vercel Edge Middleware — free-tier password gate (Hobby plan has no native Deployment
// Password Protection, that's Pro-only; this is the standard workaround). Any username is
// accepted, only the password is checked.
export const config = { matcher: '/:path*' };

const PASSWORD = 'nsd@2026';

export default function middleware(request) {
  const authHeader = request.headers.get('authorization');
  if (authHeader && authHeader.startsWith('Basic ')) {
    try {
      const decoded = atob(authHeader.slice(6));
      const password = decoded.slice(decoded.indexOf(':') + 1);
      if (password === PASSWORD) return;
    } catch (e) {}
  }
  return new Response('Authentication required', {
    status: 401,
    headers: { 'WWW-Authenticate': 'Basic realm="ORM Performance Report"' },
  });
}
