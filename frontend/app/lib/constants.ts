export const API_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

// Non-httpOnly cookie so middleware (server-side) can read it for route
// gating. The cookie's presence only gates navigation; the backend is the
// actual authority — every API call still validates the JWT itself.
export const TOKEN_COOKIE = "edunexus_token";
export const ROLE_COOKIE = "edunexus_role";

export const TOKEN_MAX_AGE_SECONDS = 24 * 60 * 60; // matches backend JWT_EXPIRE_HOURS default
