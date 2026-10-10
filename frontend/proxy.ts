import { NextRequest, NextResponse } from "next/server";

const TOKEN_COOKIE = "edunexus_access";
const REFRESH_HINT_COOKIE = "edunexus_csrf";
const ROLE_COOKIE = "edunexus_role";

const PUBLIC_PATHS = ["/login", "/register"];
const EDUCATOR_PREFIXES = ["/overview", "/subjects", "/upload", "/insights", "/quiz-review", "/students"];
const STUDENT_PREFIXES = ["/home", "/chat", "/path", "/progress", "/quiz"];

function homeFor(role: string | undefined) {
  return role === "educator" ? "/overview" : "/home";
}

function matchesPrefix(pathname: string, prefix: string): boolean {
  return pathname === prefix || pathname.startsWith(`${prefix}/`);
}

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  const token = request.cookies.get(TOKEN_COOKIE)?.value;
  const canRefresh = Boolean(request.cookies.get(REFRESH_HINT_COOKIE)?.value);
  const role = request.cookies.get(ROLE_COOKIE)?.value;
  const signedIn = Boolean(token) || (canRefresh && Boolean(role));

  if (pathname === "/") {
    return NextResponse.redirect(new URL(signedIn ? homeFor(role) : "/login", request.url));
  }

  if (PUBLIC_PATHS.some((p) => matchesPrefix(pathname, p))) {
    if (token) {
      return NextResponse.redirect(new URL(homeFor(role), request.url));
    }
    return NextResponse.next();
  }

  if (!signedIn) {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  if (EDUCATOR_PREFIXES.some((p) => matchesPrefix(pathname, p)) && role !== "educator") {
    return NextResponse.redirect(new URL(homeFor(role), request.url));
  }
  if (STUDENT_PREFIXES.some((p) => matchesPrefix(pathname, p)) && role !== "student") {
    return NextResponse.redirect(new URL(homeFor(role), request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!api/|_next/static|_next/image|favicon.ico|icon|sitemap.xml|robots.txt).*)"],
};
