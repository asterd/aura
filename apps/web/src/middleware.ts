import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const token = request.cookies.get("aura_token")?.value;
  const requestHeaders = new Headers(request.headers);

  if (token) {
    requestHeaders.set("Authorization", `Bearer ${token}`);
  }

  // Public paths that don't require auth
  const isLoginPage = pathname === "/login" || pathname.startsWith("/login");
  const isApiPath = pathname.startsWith("/api/");
  const isStaticPath =
    pathname.startsWith("/_next/") ||
    pathname.startsWith("/favicon") ||
    pathname === "/robots.txt";

  if (isStaticPath || isApiPath) {
    return NextResponse.next({
      request: {
        headers: requestHeaders,
      },
    });
  }

  // No token → redirect to login (except already on login)
  if (!token) {
    if (isLoginPage) return NextResponse.next();
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    return NextResponse.redirect(url);
  }

  // Has token + on login → redirect to chat
  if (token && isLoginPage) {
    const url = request.nextUrl.clone();
    url.pathname = "/chat";
    return NextResponse.redirect(url);
  }

  return NextResponse.next({
    request: {
      headers: requestHeaders,
    },
  });
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
