export type VerifyFailure =
  | 'missing_timestamp'
  | 'missing_signature'
  | 'malformed_timestamp'
  | 'stale_timestamp'
  | 'future_timestamp'
  | 'bad_signature';

export type VerifyResult =
  | { readonly ok: true }
  | { readonly ok: false; readonly reason: VerifyFailure };

export interface VerifyInput {
  readonly secret: string;
  readonly rawBody: Uint8Array;
  readonly timestamp: string | null;
  readonly signature: string | null;
  readonly nowMs: number;
  readonly toleranceMs?: number;
}

export const DEFAULT_TOLERANCE_MS = 5 * 60 * 1000;

const encoder = new TextEncoder();
const fail = (reason: VerifyFailure): VerifyResult => ({ ok: false, reason });

export async function signWebhook(secret: string, timestamp: string, rawBody: Uint8Array): Promise<string> {
  const key = await crypto.subtle.importKey(
    'raw',
    encoder.encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign'],
  );
  const prefix = encoder.encode(`${timestamp}.`);
  const message = new Uint8Array(prefix.length + rawBody.length);
  message.set(prefix);
  message.set(rawBody, prefix.length);
  const mac = new Uint8Array(await crypto.subtle.sign('HMAC', key, message));
  return Array.from(mac, (b) => b.toString(16).padStart(2, '0')).join('');
}

function constantTimeEqual(a: Uint8Array, b: Uint8Array): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a[i]! ^ b[i]!;
  return diff === 0;
}

export async function verifyWebhook(input: VerifyInput): Promise<VerifyResult> {
  if (input.timestamp === null) return fail('missing_timestamp');
  if (input.signature === null) return fail('missing_signature');
  if (!/^\d{1,12}$/.test(input.timestamp)) return fail('malformed_timestamp');

  const tolerance = input.toleranceMs ?? DEFAULT_TOLERANCE_MS;
  const ageMs = input.nowMs - Number(input.timestamp) * 1000;
  if (ageMs > tolerance) return fail('stale_timestamp');
  if (ageMs < -tolerance) return fail('future_timestamp');

  const expected = await signWebhook(input.secret, input.timestamp, input.rawBody);
  const matches = constantTimeEqual(encoder.encode(expected), encoder.encode(input.signature.toLowerCase()));
  return matches ? { ok: true } : fail('bad_signature');
}
