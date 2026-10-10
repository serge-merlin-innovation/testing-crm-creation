import { describe, expect, it } from "vitest";
import { readString, readStringArray } from "@/lib/json-field";

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

describe("readStringArray", () => {
  it("returns a list of strings", () => {
    expect(readStringArray({ permissions: ["audit.read"] }, "permissions")).toEqual(["audit.read"]);
  });

  it.each([
    ["a string", { permissions: "audit.read" }],
    ["a list holding a non-string", { permissions: ["audit.read", 1] }],
    ["null", { permissions: null }],
  ])("returns null when the field is %s", (_label, payload) => {
    expect(readStringArray(payload, "permissions")).toBeNull();
  });

  it("does not read a prototype member", () => {
    expect(readStringArray({}, "constructor")).toBeNull();
  });
});
