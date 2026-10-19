import { describe, expect, it } from 'vitest';
import { DEFAULT_TOLERANCE_MS, signWebhook, verifyWebhook, type VerifyInput } from '../src/webhook.ts';

const SECRET = 'whsec_test';
const NOW_S = 1_700_000_000;
const NOW_MS = NOW_S * 1000;
const bytes = (s: string) => new TextEncoder().encode(s);

async function signed(body: Uint8Array, timestampS = NOW_S, secret = SECRET): Promise<VerifyInput> {
  const timestamp = String(timestampS);
  return {
    secret: SECRET,
    rawBody: body,
    timestamp,
    signature: await signWebhook(secret, timestamp, body),
    nowMs: NOW_MS,
  };
}

const body = bytes('{"id":"t-1","status":"open"}');

describe('verifyWebhook', () => {
  it('accepts an untouched delivery', async () => {
    expect(await verifyWebhook(await signed(body))).toEqual({ ok: true });
  });

  it('matches an HMAC-SHA256 vector computed independently with openssl', async () => {
    const sig = await signWebhook('key', '1', bytes('x'));
    expect(sig).toBe('fc4913c41a7bf793267e2a384f3261c9436ec2cd097bd745e7b0d99113f510ec');
  });

  it('rejects a tampered body', async () => {
    const input = await signed(body);
    const result = await verifyWebhook({ ...input, rawBody: bytes('{"id":"t-1","status":"closed"}') });
    expect(result).toEqual({ ok: false, reason: 'bad_signature' });
  });

  it('rejects a signature made with the wrong secret', async () => {
    const result = await verifyWebhook(await signed(body, NOW_S, 'whsec_other'));
    expect(result).toEqual({ ok: false, reason: 'bad_signature' });
  });

  it('rejects a stale timestamp even when the signature is genuine', async () => {
    const result = await verifyWebhook(await signed(body, NOW_S - 301));
    expect(result).toEqual({ ok: false, reason: 'stale_timestamp' });
  });

  it('rejects a timestamp too far in the future', async () => {
    const result = await verifyWebhook(await signed(body, NOW_S + 301));
    expect(result).toEqual({ ok: false, reason: 'future_timestamp' });
  });

  it('accepts exactly the tolerance on both sides and rejects one second beyond', async () => {
    const edge = DEFAULT_TOLERANCE_MS / 1000;
    expect(await verifyWebhook(await signed(body, NOW_S - edge))).toEqual({ ok: true });
    expect(await verifyWebhook(await signed(body, NOW_S + edge))).toEqual({ ok: true });
    expect(await verifyWebhook(await signed(body, NOW_S - edge - 1))).toMatchObject({ reason: 'stale_timestamp' });
    expect(await verifyWebhook(await signed(body, NOW_S + edge + 1))).toMatchObject({ reason: 'future_timestamp' });
  });

  it('binds the timestamp into the MAC: replaying a body under a fresh timestamp fails', async () => {
    const old = await signed(body, NOW_S - 10);
    const result = await verifyWebhook({ ...old, timestamp: String(NOW_S) });
    expect(result).toEqual({ ok: false, reason: 'bad_signature' });
  });

  it('reports missing headers', async () => {
    const input = await signed(body);
    expect(await verifyWebhook({ ...input, signature: null })).toEqual({ ok: false, reason: 'missing_signature' });
    expect(await verifyWebhook({ ...input, timestamp: null })).toEqual({ ok: false, reason: 'missing_timestamp' });
  });

  it.each(['abc', '12.5', '-1', '', ' 1700000000', '9'.repeat(400)])('rejects malformed timestamp %j', async (timestamp) => {
    const input = await signed(body);
    expect(await verifyWebhook({ ...input, timestamp })).toEqual({ ok: false, reason: 'malformed_timestamp' });
  });

  it.each(['', 'zz', 'deadbeef'])('rejects malformed signature %j without throwing', async (signature) => {
    const input = await signed(body);
    expect(await verifyWebhook({ ...input, signature })).toEqual({ ok: false, reason: 'bad_signature' });
  });

  it('accepts an upper-case hex signature', async () => {
    const input = await signed(body);
    expect(await verifyWebhook({ ...input, signature: input.signature!.toUpperCase() })).toEqual({ ok: true });
  });

  it('fails on re-serialised JSON: same data, different bytes', async () => {
    const original = bytes('{"id": "t-1",  "status": "open"}');
    const input = await signed(original);
    const reserialised = bytes(JSON.stringify(JSON.parse(new TextDecoder().decode(original))));

    expect(JSON.parse(new TextDecoder().decode(reserialised))).toEqual(JSON.parse(new TextDecoder().decode(original)));
    expect(await verifyWebhook({ ...input, rawBody: reserialised })).toEqual({ ok: false, reason: 'bad_signature' });
    expect(await verifyWebhook(input)).toEqual({ ok: true });
  });

  it('is binary-safe: bytes that are not valid UTF-8 still verify', async () => {
    const binary = new Uint8Array([0xff, 0xfe, 0x00, 0x80, 0xc3]);
    expect(await verifyWebhook(await signed(binary))).toEqual({ ok: true });
  });
});
