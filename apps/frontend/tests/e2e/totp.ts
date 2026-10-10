import { createHmac } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";

// Enrolment secrets live beside the banked sessions, in the gitignored .auth directory, so a
// rerun against the same database can still answer the code for an already-enrolled account.
const secretsFile = "tests/e2e/.auth/totp-secrets.json";

function readSecrets(): Record<string, string> {
  return existsSync(secretsFile) ? JSON.parse(readFileSync(secretsFile, "utf8")) : {};
}

export function saveSecret(email: string, secret: string) {
  mkdirSync(dirname(secretsFile), { recursive: true });
  writeFileSync(secretsFile, JSON.stringify({ ...readSecrets(), [email]: secret }));
}

function base32(secret: string): Buffer {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = "";
  for (const character of secret.replace(/=+$/, "").toUpperCase()) {
    bits += alphabet.indexOf(character).toString(2).padStart(5, "0");
  }
  const bytes = bits.match(/.{8}/g) ?? [];
  return Buffer.from(bytes.map((byte) => parseInt(byte, 2)));
}

export function currentCode(email: string): string {
  const secret = readSecrets()[email];
  if (!secret) {
    throw new Error(`${email} has no saved TOTP secret. Reset its 2FA or use a fresh database.`);
  }
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 30_000)));
  const digest = createHmac("sha1", base32(secret)).update(counter).digest();
  const offset = digest[digest.length - 1] & 0x0f;
  const value = digest.readUInt32BE(offset) & 0x7fffffff;
  return String(value % 1_000_000).padStart(6, "0");
}
