import { NextRequest, NextResponse } from "next/server";

const TOKEN_COOKIE = "edunexus_token";
const ROLE_COOKIE = "edunexus_role";

const PUBLIC_PATHS = ["/login", "/register"];
const EDUCATOR_PREFIXES = ["/upload", "/insights", "/quiz-review", "/students"];
const STUDENT_PREFIXES = ["/chat", "/path", "/progress", "/quiz"];

function homeFor(role: string | undefined) {
  return role === "educator" ? "/upload" : "/chat";
}

/**
 * Route gating only — this cookie is not httpOnly and its value is never
 * cryptographically verified here. It exists so unauthenticated/wrong-role
 * navigations redirect immediately instead of rendering a page that will
 * just 401 on its first API call. The backend JWT check on every request is
 * the actual authorization boundary.
 */
export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const token = request.cookies.get(TOKEN_COOKIE)?.value;
  const role = request.cookies.get(ROLE_COOKIE)?.value;

  if (pathname === "/") {
    return NextResponse.redirect(new URL(token ? homeFor(role) : "/login", request.url));
  }

  const isPublic = PUBLIC_PATHS.some((p) => pathname.startsWith(p));

  if (isPublic) {
    if (token) {
      return NextResponse.redirect(new URL(homeFor(role), request.url));
    }
    return NextResponse.next();
  }

  if (!token) {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  const isEducatorPath = EDUCATOR_PREFIXES.some((p) => pathname.startsWith(p));
  const isStudentPath = STUDENT_PREFIXES.some((p) => pathname.startsWith(p));

  if (isEducatorPath && role !== "educator") {
    return NextResponse.redirect(new URL(homeFor(role), request.url));
  }
  if (isStudentPath && role !== "student") {
    return NextResponse.redirect(new URL(homeFor(role), request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
