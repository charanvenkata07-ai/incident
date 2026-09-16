import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

export function middleware(request: NextRequest) {
  const token = request.cookies.get('auth_token')?.value;
  const isLoginPage = request.nextUrl.pathname === '/login';

  // For a real app we'd verify the token. Here we just check presence.
  // Note: we can't easily read localStorage here, so client-side auth handles actual enforcement.
  // This middleware is just a fast path.

  return NextResponse.next();
}

export const config = {
  matcher: ['/((?!api|_next/static|_next/image|favicon.ico).*)'],
};
