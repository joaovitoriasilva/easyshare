/**
 * Cheap, dependency-free password-strength estimate for UI feedback only.
 *
 * The backend enforces the real minimum (length); this just guides the user
 * toward a stronger secret by scoring length and character variety. It is not a
 * breach check and not a substitute for server-side policy.
 */

export interface PasswordStrength {
  /** 0 for an empty field, otherwise 1 (weak) to 4 (strong). */
  score: 0 | 1 | 2 | 3 | 4;
  /** Short human label matching the score ("", "Weak" … "Strong"). */
  label: string;
}

const LABELS: Record<number, string> = {
  1: "Weak",
  2: "Fair",
  3: "Good",
  4: "Strong",
};

export function estimatePasswordStrength(password: string): PasswordStrength {
  if (!password) {
    return { score: 0, label: "" };
  }
  let raw = 0;
  if (password.length >= 8) raw += 1;
  if (password.length >= 12) raw += 1;
  const classes = [/[a-z]/, /[A-Z]/, /[0-9]/, /[^A-Za-z0-9]/].filter((re) =>
    re.test(password),
  ).length;
  if (classes >= 2) raw += 1;
  if (classes >= 3) raw += 1;
  // Anything below the enforced minimum length can never rank above "Weak",
  // however much character variety it has.
  if (password.length < 8) {
    raw = Math.min(raw, 1);
  }
  // A non-empty password always shows at least one (weak) segment.
  const score = Math.max(1, Math.min(4, raw)) as 1 | 2 | 3 | 4;
  return { score, label: LABELS[score] };
}
