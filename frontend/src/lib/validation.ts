/** Client-side email validation for real-time UX; the backend validates strictly
 * with Pydantic's EmailStr, this is only to guide the user before submitting. */

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function isValidEmail(value: string): boolean {
  return EMAIL_RE.test(value.trim());
}

/** Split a comma/whitespace-separated list into trimmed, non-empty entries. */
export function parseEmailList(value: string): string[] {
  return value
    .split(/[\s,]+/)
    .map((email) => email.trim())
    .filter(Boolean);
}

/** Return the entries of a comma/whitespace-separated list that are not valid. */
export function invalidEmails(value: string): string[] {
  return parseEmailList(value).filter((email) => !isValidEmail(email));
}
