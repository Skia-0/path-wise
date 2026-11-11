import { useMemo, useState } from "react";
import { api, setToken, ApiError } from "../api/client";
import "./auth.css";

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const MAX_PASSWORD_BYTES = 72;
const encoder = new TextEncoder();

const SUBJECTS = [
  { name: "Core Mathematics", description: "Diagnostic, study path and practice" },
  { name: "Elective Physics", description: "Diagnostic, study path and practice" },
];

const RULES = [
  { key: "length", label: "At least 8 characters" },
  { key: "uppercase", label: "One uppercase letter" },
  { key: "number", label: "One number" },
  { key: "special", label: "One special character (e.g. ! @ #)" },
  { key: "bytes", label: "Under 72 bytes" },
];

const STRENGTH_LABELS = { weak: "Weak", medium: "Medium", strong: "Strong" };

function passwordChecks(password) {
  return {
    length: password.length >= 8,
    uppercase: /[A-Z]/.test(password),
    number: /[0-9]/.test(password),
    special: /[^A-Za-z0-9\s]/.test(password),
    bytes: encoder.encode(password).length <= MAX_PASSWORD_BYTES,
  };
}

function getStrength(password, checks) {
  if (!password) return null;
  if (!checks.bytes) return "weak";
  const requiredMet = [checks.length, checks.uppercase, checks.number, checks.special].filter(
    Boolean
  ).length;
  if (requiredMet < 4) return requiredMet >= 3 ? "medium" : "weak";
  return password.length >= 12 ? "strong" : "medium";
}

function validate({ name, email, password, subjects }) {
  if (!name) return "Enter your full name.";
  if (!EMAIL_PATTERN.test(email)) return "Enter a valid email address.";
  if (subjects.length === 0) return "Choose at least one subject.";
  if (!password) return "Create a password.";
  const checks = passwordChecks(password);
  if (!checks.length) return "Password must be at least 8 characters.";
  if (!checks.uppercase) return "Password needs one uppercase letter.";
  if (!checks.number) return "Password needs one number.";
  if (!checks.special) return "Password needs one special character.";
  if (!checks.bytes) return "Password is too long. Keep it under 72 bytes.";
  return "";
}

function SignupPage({ onSignupSuccess, onGoToLogin }) {
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [subjects, setSubjects] = useState([]);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const checks = useMemo(() => passwordChecks(password), [password]);
  const strength = getStrength(password, checks);

  function toggleSubject(name) {
    setError("");
    setSubjects((current) => {
      const next = current.includes(name)
        ? current.filter((item) => item !== name)
        : [...current, name];
      return SUBJECTS.map((subject) => subject.name).filter((item) => next.includes(item));
    });
  }

  async function handleSubmit(event) {
    event.preventDefault();

    const cleanName = fullName.trim();
    const cleanEmail = email.trim().toLowerCase();
    const problem = validate({
      name: cleanName,
      email: cleanEmail,
      password,
      subjects,
    });
    if (problem) {
      setError(problem);
      return;
    }

    setError("");
    setSubmitting(true);
    try {
      const data = await api.post(
        "/auth/signup",
        {
          email: cleanEmail,
          password,
          full_name: cleanName,
          subjects,
        },
        { auth: false }
      );
      setToken(data.access_token);
      onSignupSuccess(data);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card auth-card--wide">
        <div className="brand">
          <div className="brand-mark">PW</div>
          <div className="brand-name">
            Path-<span>Wise</span>
          </div>
        </div>

        <h1 className="auth-title">Create your account</h1>
        <p className="auth-subtitle">Set up your WAEC practice in under a minute.</p>

        <form onSubmit={handleSubmit} noValidate>
          <div className="field">
            <label className="field-label" htmlFor="full-name">
              Full name
            </label>
            <input
              id="full-name"
              className="input"
              type="text"
              autoComplete="name"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
            />
          </div>

          <div className="field">
            <label className="field-label" htmlFor="email">
              Email
            </label>
            <input
              id="email"
              className="input"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>

          <div className="field">
            <label className="field-label" htmlFor="password">
              Password
            </label>
            <div className="input-wrap">
              <input
                id="password"
                className="input input--with-toggle"
                type={showPassword ? "text" : "password"}
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              <button
                type="button"
                className="toggle-btn"
                onClick={() => setShowPassword((visible) => !visible)}
                aria-pressed={showPassword}
                aria-label={showPassword ? "Hide password" : "Show password"}
              >
                {showPassword ? "Hide" : "Show"}
              </button>
            </div>

            <div className="strength">
              <div className="strength-head">
                <span>Password strength</span>
                {strength && (
                  <span className={`strength-label strength-label--${strength}`}>
                    {STRENGTH_LABELS[strength]}
                  </span>
                )}
              </div>
              <div className="strength-track" aria-hidden="true">
                <div className={`strength-fill${strength ? ` strength-fill--${strength}` : ""}`} />
              </div>
              <ul className="rules">
                {RULES.map((rule) => {
                  const met = checks[rule.key];
                  return (
                    <li key={rule.key} className={`rule${met ? " rule--met" : ""}`}>
                      <span className="rule-mark" aria-hidden="true">
                        {met ? "✓" : ""}
                      </span>
                      <span>{rule.label}</span>
                    </li>
                  );
                })}
              </ul>
            </div>
          </div>

          <fieldset className="subject-fieldset">
            <legend className="field-label">Subjects</legend>
            <p className="field-hint">
              Pick one or both. You can add the other later from your dashboard.
            </p>
            <div className="subject-grid">
              {SUBJECTS.map((subject) => {
                const selected = subjects.includes(subject.name);
                return (
                  <button
                    key={subject.name}
                    type="button"
                    role="checkbox"
                    aria-checked={selected}
                    className={`subject-option${selected ? " subject-option--on" : ""}`}
                    onClick={() => toggleSubject(subject.name)}
                  >
                    <span className="subject-check" aria-hidden="true">
                      {selected ? "✓" : ""}
                    </span>
                    <span>
                      <span className="subject-name">{subject.name}</span>
                      <span className="subject-desc">{subject.description}</span>
                    </span>
                  </button>
                );
              })}
            </div>
          </fieldset>

          {error && (
            <p key={error} role="alert" className="alert-error">
              {error}
            </p>
          )}

          <button type="submit" className="btn-primary" disabled={submitting}>
            {submitting && <span className="spinner" aria-hidden="true" />}
            {submitting ? "Creating account..." : "Create account"}
          </button>
        </form>

        <p className="switch-row">
          Already have an account?{" "}
          <button type="button" className="link-btn" onClick={onGoToLogin}>
            Log in
          </button>
        </p>
      </div>
    </div>
  );
}

export default SignupPage;