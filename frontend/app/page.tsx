import { redirect } from 'next/navigation';

/**
 * Root route — immediately redirect to /login.
 * The AuthProvider in use-auth.tsx handles post-login routing
 * (admin → /admin, employee → /dashboard).
 */
export default function RootPage() {
  redirect('/login');
}
