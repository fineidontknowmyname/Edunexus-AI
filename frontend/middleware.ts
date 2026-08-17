import { NextRequest, NextResponse } from "next/server";

const TOKEN_COOKIE = "edunexus_token";
const ROLE_COOKIE = "edunexus_role";

const PUBLIC_PATHS = ["/login", "/register"];
const EDUCATOR_PREFIXES = ["/upload", "/insights", "/quiz-review", "/students"];
const STUDENT_PREFIXES = ["/chat", "/path", "/progress", "/quiz"];

function homeFor(role: string | undefined) {
  return role === "educator" ? "/upload" : "/chat";
}

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const token = request.cookies.get(TOKEN_COOKIE)?.value;
  const role = request.cookies.get(ROLE_COOKIE)?.value;

  console.log(`[MIDDLEWARE] ${pathname} | token=${token ? "present" : "absent"} role=${role ?? "none"}`);

  if (pathname === "/") {
    const dest = token ? homeFor(role) : "/login";
    console.log(`[MIDDLEWARE] Root path -> redirecting to ${dest}`);
    return NextResponse.redirect(new URL(dest, request.url));
  }

  const isPublic = PUBLIC_PATHS.some((p) => pathname.startsWith(p));

  if (isPublic) {
    if (token) {
      console.log(`[MIDDLEWARE] Already authenticated -> redirecting away from public path ${pathname} to ${homeFor(role)}`);
      return NextResponse.redirect(new URL(homeFor(role), request.url));
    }
    return NextResponse.next();
  }

  if (!token) {
    console.log(`[MIDDLEWARE] No token for protected path ${pathname} -> redirecting to /login`);
    return NextResponse.redirect(new URL("/login", request.url));
  }

  const isEducatorPath = EDUCATOR_PREFIXES.some((p) => pathname.startsWith(p));
  const isStudentPath = STUDENT_PREFIXES.some((p) => pathname.startsWith(p));

  if (isEducatorPath && role !== "educator") {
    console.log(`[MIDDLEWARE] role=${role} blocked from educator path ${pathname} -> redirecting to ${homeFor(role)}`);
    return NextResponse.redirect(new URL(homeFor(role), request.url));
  }
  if (isStudentPath && role !== "student") {
    console.log(`[MIDDLEWARE] role=${role} blocked from student path ${pathname} -> redirecting to ${homeFor(role)}`);
    return NextResponse.redirect(new URL(homeFor(role), request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
