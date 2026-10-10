const RELATIVE = new Intl.RelativeTimeFormat("en", { numeric: "auto" });

function parseDate(value: string): Date {
  const hasZone = /[zZ]|[+-]\d{2}:?\d{2}$/.test(value);
  return new Date(hasZone ? value : `${value}Z`);
}

export function formatRelative(value: string | null | undefined): string {
  if (!value) return "";
  const date = parseDate(value);
  const diffSeconds = Math.round((date.getTime() - Date.now()) / 1000);
  const abs = Math.abs(diffSeconds);
  if (abs < 60) return "just now";
  if (abs < 3600) return RELATIVE.format(Math.round(diffSeconds / 60), "minute");
  if (abs < 86400) return RELATIVE.format(Math.round(diffSeconds / 3600), "hour");
  if (abs < 86400 * 7) return RELATIVE.format(Math.round(diffSeconds / 86400), "day");
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: date.getFullYear() === new Date().getFullYear() ? undefined : "numeric" });
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "";
  return parseDate(value).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "";
  return parseDate(value).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

export function percent(score: number): string {
  return `${Math.round(score * 100)}%`;
}

export function plural(count: number, word: string, pluralWord = `${word}s`): string {
  return `${count} ${count === 1 ? word : pluralWord}`;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

const HONORIFICS = new Set(["dr", "prof", "mr", "mrs", "ms", "mx", "sir", "madam"]);

export function firstName(fullName: string | null | undefined): string | undefined {
  if (!fullName) return undefined;
  const parts = fullName.trim().split(/\s+/);
  const first = parts.find((p) => !HONORIFICS.has(p.replace(/\.$/, "").toLowerCase()));
  return first ?? parts[0];
}
