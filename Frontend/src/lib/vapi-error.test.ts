import { describe, expect, it } from "vitest";

import { describeVapiError } from "@/lib/vapi-error";

// `@vapi-ai/web` reports call failures through its `error` and
// `call-start-failed` events rather than a rejected promise. Its own
// `serializeError()` has a fallback branch - `message: errorObj.message ||
// errorObj.error || JSON.stringify(error)` - that can leave `.message` holding
// a nested object instead of a string whenever the underlying Daily.co error
// has no top-level string `message` (its connection/ICE failures are commonly
// shaped `{ error: { type, ... }, action }`, no `message` key at all). Passing
// that straight through `String(...)` is exactly how the call stage ended up
// showing the literal text "[object Object]" instead of a reason - see
// CallStage.tsx's `error` handler. Every case here is a shape the SDK is
// documented or observed to actually emit, not a hypothetical.
describe("describeVapiError", () => {
  it("returns a plain string unchanged", () => {
    expect(describeVapiError("microphone permission denied")).toBe("microphone permission denied");
  });

  it("reads the message off an Error instance", () => {
    expect(describeVapiError(new Error("network unreachable"))).toBe("network unreachable");
  });

  it("reads a string message field off a plain object", () => {
    expect(describeVapiError({ message: "assistant rejected" })).toBe("assistant rejected");
  });

  it("falls back to a string error field when message is absent", () => {
    expect(describeVapiError({ error: "room not found" })).toBe("room not found");
  });

  it("unwraps the SDK's real `error` event shape: { error: serializeError(e) }", () => {
    // What vapi.js actually emits for e.g. a daily-call-join-error, when the
    // underlying error was a real Error instance.
    const event = {
      type: "daily-call-join-error",
      stage: "daily-call-join",
      error: { message: "join timed out", name: "Error", stack: "..." },
      timestamp: "2026-09-05T07:00:00.000Z",
    };
    expect(describeVapiError(event)).toBe("join timed out");
  });

  it("unwraps the SDK's `call-start-failed` event shape: { error: <string> }", () => {
    const event = {
      stage: "unknown",
      totalDuration: 1200,
      error: "webCall creation failed",
      errorStack: "...",
      timestamp: "2026-09-05T07:00:00.000Z",
    };
    expect(describeVapiError(event)).toBe("webCall creation failed");
  });

  it("recurses through a nested object message instead of stringifying it directly", () => {
    // serializeError()'s plain-object branch sets message = errorObj.error
    // when errorObj.message is absent and errorObj.error is itself an object
    // (Daily's own error events are commonly shaped this way) - message ends
    // up as an object, not a string.
    const event = {
      type: "start-method-error",
      error: { message: { type: "ice-failed", reason: "network-error" }, name: "Error" },
    };
    const result = describeVapiError(event);
    expect(result).not.toBe("[object Object]");
    expect(result).toContain("ice-failed");
  });

  it("recurses when only a nested error.error string is present, two levels deep", () => {
    const event = { error: { error: "deep failure reason" } };
    expect(describeVapiError(event)).toBe("deep failure reason");
  });

  it("never returns the literal string \"[object Object]\" for any plain object", () => {
    expect(describeVapiError({})).not.toBe("[object Object]");
    expect(describeVapiError({ foo: "bar" })).not.toBe("[object Object]");
    expect(describeVapiError({ message: {} })).not.toBe("[object Object]");
  });

  it("does not let an empty message string shadow a usable error field", () => {
    expect(describeVapiError({ message: "", error: "fallback text" })).toBe("fallback text");
  });

  it("returns a generic message for null or undefined", () => {
    expect(describeVapiError(null)).toBeTruthy();
    expect(describeVapiError(undefined)).toBeTruthy();
    expect(describeVapiError(null)).not.toBe("[object Object]");
  });

  it("does not throw on a circular object and still returns a string", () => {
    const circular: Record<string, unknown> = { type: "weird" };
    circular.self = circular;
    expect(() => describeVapiError(circular)).not.toThrow();
    expect(typeof describeVapiError(circular)).toBe("string");
  });

  it("stringifies a non-object, non-string value rather than defaulting silently", () => {
    expect(describeVapiError(42)).toBe("42");
  });
});
