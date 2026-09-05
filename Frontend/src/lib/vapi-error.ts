const FALLBACK = "The voice call failed for an unknown reason.";
const MAX_DEPTH = 4;

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function safeStringify(value: unknown): string | null {
  try {
    const json = JSON.stringify(value);
    return json && json !== "{}" ? json : null;
  } catch {
    // Circular references (Daily's own call/error objects can carry them).
    return null;
  }
}

/**
 * Extract a human-readable reason from whatever `@vapi-ai/web` hands its
 * `error` and `call-start-failed` listeners.
 *
 * The SDK's own `serializeError()` has a fallback branch - `message:
 * errorObj.message || errorObj.error || JSON.stringify(error)` - that can
 * leave `.message` holding a nested object rather than a string, because
 * Daily.co's own connection/ICE failures are commonly shaped `{ error: {...},
 * action }` with no top-level string `message`. A bare `String(err.message)`
 * on that shape produces the literal text "[object Object]", which is what a
 * failed call actually showed on screen. This walks `message`/`error` fields
 * recursively (bounded, and tolerant of cycles) until it finds a real string,
 * falling back to a JSON snapshot rather than an unhelpful stringified object.
 */
export function describeVapiError(err: unknown, depth = 0): string {
  if (isNonEmptyString(err)) return err.trim();
  if (err instanceof Error) return isNonEmptyString(err.message) ? err.message : String(err);

  if (isRecord(err)) {
    if (depth >= MAX_DEPTH) return safeStringify(err) ?? FALLBACK;

    const message = err.message;
    if (isNonEmptyString(message)) return message.trim();
    if (isRecord(message)) return describeVapiError(message, depth + 1);

    const errorField = err.error;
    if (isNonEmptyString(errorField)) return errorField.trim();
    if (isRecord(errorField)) return describeVapiError(errorField, depth + 1);

    return safeStringify(err) ?? FALLBACK;
  }

  if (err === null || err === undefined) return FALLBACK;
  return String(err);
}
