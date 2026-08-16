export const API_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export const TOKEN_COOKIE = "edunexus_token";
export const ROLE_COOKIE = "edunexus_role";

export const TOKEN_MAX_AGE_SECONDS = 24 * 60 * 60;
