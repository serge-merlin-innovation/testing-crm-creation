import { describe, expect, it } from "vitest";
import { readBoolean, readString } from "@/lib/json-field";

describe("readString", () => {
  it("returns the field when it is a string", () => {
    expect(readString({ detail: "Check your details." }, "detail")).toBe(
      "Check your details.",
    );
  });

  it("returns an empty string verbatim rather than treating it as absent", () => {
    // Callers fall back with `??`, so a backend that sends "" is reported as "", not replaced.
    expect(readString({ detail: "" }, "detail")).toBe("");
  });

  it.each([
    ["a number", { detail: 42 }],
    ["a boolean", { detail: true }],
    ["null", { detail: null }],
    ["an object", { detail: { nested: "value" } }],
  ])("returns null when the field is %s", (_label, payload) => {
    expect(readString(payload, "detail")).toBeNull();
  });

  it("returns null when the key is absent", () => {
    expect(readString({ other: "value" }, "detail")).toBeNull();
  });

  it.each([
    ["null", null],
    ["a string", "text"],
    ["a number", 42],
    ["undefined", undefined],
  ])("returns null when the payload is %s", (_label, payload) => {
    expect(readString(payload, "detail")).toBeNull();
  });

  it.each(["toString", "constructor"])(
    "does not read %s off the prototype",
    (key) => {
      expect(readString({}, key)).toBeNull();
    },
  );
});

describe("readBoolean", () => {
  it("returns true", () => {
    expect(readBoolean({ is_superuser: true }, "is_superuser")).toBe(true);
  });

  it("returns false rather than collapsing it to null", () => {
    // The distinction the page gate rests on: `false` is an answer, null means the backend
    // did not give one and the session cannot be judged.
    expect(readBoolean({ is_superuser: false }, "is_superuser")).toBe(false);
  });

  it.each([
    ["the string 'true'", { is_superuser: "true" }],
    ["zero", { is_superuser: 0 }],
    ["null", { is_superuser: null }],
  ])("returns null when the field is %s", (_label, payload) => {
    expect(readBoolean(payload, "is_superuser")).toBeNull();
  });

  it("returns null when the key is absent", () => {
    expect(readBoolean({ id: 1 }, "is_superuser")).toBeNull();
  });

  it("returns null when the payload is not an object", () => {
    expect(readBoolean(null, "is_superuser")).toBeNull();
  });

  it("does not read a prototype member", () => {
    expect(readBoolean({}, "constructor")).toBeNull();
  });
});
