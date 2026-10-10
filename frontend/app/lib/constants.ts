export const API_URL = process.env.NEXT_PUBLIC_API_URL || "/api/v1";

export const ROLE_COOKIE = "edunexus_role";
export const CSRF_COOKIE = "edunexus_csrf";
export const CSRF_HEADER = "X-CSRF-Token";

export const REFRESH_LOCK_NAME = "edunexus-auth-refresh";

export const CHAT_MESSAGE_MAX_LENGTH = 4000;
export const CHAT_TOPIC_MAX_LENGTH = 500;
export const CHAT_SESSIONS_PAGE_SIZE = 20;
export const CHAT_HISTORY_LIMIT = 200;

export const UPLOAD_MAX_BYTES = 20 * 1024 * 1024;

export const EDUCATOR_HOME = "/overview";
export const STUDENT_HOME = "/home";
