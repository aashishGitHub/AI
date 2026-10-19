import { describe, expect, it } from 'vitest';
import { EchoGuard, fingerprint } from '../src/echoGuard.ts';

describe('fingerprint', () => {
  it('ignores key order but not values or types', () => {
    expect(fingerprint({ a: 1, b: { c: [1, 2] } })).toBe(fingerprint({ b: { c: [1, 2] }, a: 1 }));
    expect(fingerprint({ a: 1 })).not.toBe(fingerprint({ a: '1' }));
    expect(fingerprint({ a: [1, 2] })).not.toBe(fingerprint({ a: [2, 1] }));
    expect(fingerprint(null)).not.toBe(fingerprint('null'));
  });
});

describe('EchoGuard.decide', () => {
  it('drops the webhook that mirrors our own push', () => {
    const guard = new EchoGuard();
    guard.recordPush('t-1', 'v1');
    expect(guard.decide('t-1', 'v1', 'v1')).toBe('drop-as-echo');
  });

  it('still drops our echo after the local copy has moved on', () => {
    const guard = new EchoGuard();
    guard.recordPush('t-1', 'v1');
    expect(guard.decide('t-1', 'v1', 'v2-local-unpushed')).toBe('drop-as-echo');
  });

  it('applies a genuine remote edit when local has not diverged from what we pushed', () => {
    const guard = new EchoGuard();
    guard.recordPush('t-1', 'v1');
    expect(guard.decide('t-1', 'v2', 'v1')).toBe('apply');
  });

  it('applies a brand-new remote entity we have never seen', () => {
    expect(new EchoGuard().decide('t-9', 'v1', undefined)).toBe('apply');
  });

  it('flags a conflict when both sides changed since the last push', () => {
    const guard = new EchoGuard();
    guard.recordPush('t-1', 'v1');
    expect(guard.decide('t-1', 'v2-remote', 'v2-local')).toBe('conflict');
  });

  it('flags a conflict when the entity was created on both sides independently', () => {
    expect(new EchoGuard().decide('t-1', 'remote', 'local')).toBe('conflict');
  });

  it('treats both sides converging on the same content as nothing to do', () => {
    const guard = new EchoGuard();
    guard.recordPush('t-1', 'v1');
    expect(guard.decide('t-1', 'v2', 'v2')).toBe('drop-as-echo');
  });

  it('tracks entities independently', () => {
    const guard = new EchoGuard();
    guard.recordPush('a', 'v1');
    expect(guard.decide('b', 'v1', undefined)).toBe('apply');
  });
});

interface Webhook {
  readonly id: string;
  readonly fp: string;
}

function simulate(guarded: boolean, maxSteps = 1000) {
  const remote = new Map<string, string>();
  const local = new Map<string, string>();
  const guard = new EchoGuard();
  const webhooks: Webhook[] = [];
  const conflicts: Webhook[] = [];
  const stats = { steps: 0, pushes: 0 };

  const writeRemote = (id: string, fp: string) => {
    remote.set(id, fp);
    webhooks.push({ id, fp });
  };

  const pushIfChanged = (id: string) => {
    const fp = local.get(id)!;
    if (guarded && guard.lastPushed(id) === fp) return;
    stats.pushes++;
    guard.recordPush(id, fp);
    writeRemote(id, fp);
  };

  const drain = () => {
    while (webhooks.length > 0 && stats.steps < maxSteps) {
      stats.steps++;
      const event = webhooks.shift()!;
      const decision = guarded ? guard.decide(event.id, event.fp, local.get(event.id)) : 'apply';
      if (decision === 'conflict') conflicts.push(event);
      if (decision !== 'apply') continue;
      local.set(event.id, event.fp);
      guard.recordPush(event.id, event.fp);
      pushIfChanged(event.id);
    }
  };

  return {
    stats,
    local,
    remote,
    conflicts,
    pending: () => webhooks.length,
    localEdit: (id: string, fp: string) => {
      local.set(id, fp);
      pushIfChanged(id);
      drain();
    },
    localEditOffline: (id: string, fp: string) => local.set(id, fp),
    remoteEdit: (id: string, fp: string) => {
      writeRemote(id, fp);
      drain();
    },
  };
}

describe('two-way sync loop', () => {
  it('terminates: our push comes back as a webhook and is dropped as an echo', () => {
    const sim = simulate(true);
    sim.localEdit('t-1', 'v1');
    expect(sim.stats).toEqual({ steps: 1, pushes: 1 });
    expect(sim.pending()).toBe(0);
    expect(sim.remote.get('t-1')).toBe('v1');
  });

  it('terminates: a remote edit is applied locally and never pushed back', () => {
    const sim = simulate(true);
    sim.localEdit('t-1', 'v1');
    sim.remoteEdit('t-1', 'v2');
    expect(sim.local.get('t-1')).toBe('v2');
    expect(sim.stats).toEqual({ steps: 2, pushes: 1 });
    expect(sim.pending()).toBe(0);
  });

  it('terminates across many entities and alternating edits', () => {
    const sim = simulate(true);
    for (let i = 0; i < 50; i++) {
      sim.localEdit(`t-${i}`, `local-${i}`);
      sim.remoteEdit(`t-${i}`, `remote-${i}`);
    }
    expect(sim.pending()).toBe(0);
    expect(sim.stats.pushes).toBe(50);
    expect(sim.stats.steps).toBe(100);
  });

  it('without the guard the same scenario ping-pongs until the step cap', () => {
    const sim = simulate(false, 200);
    sim.localEdit('t-1', 'v1');
    expect(sim.stats.steps).toBe(200);
    expect(sim.pending()).toBeGreaterThan(0);
    expect(sim.stats.pushes).toBeGreaterThan(100);
  });

  it('surfaces a conflict instead of overwriting an unpushed local edit', () => {
    const sim = simulate(true);
    sim.localEdit('t-1', 'v1');
    sim.localEditOffline('t-1', 'v2-local');
    sim.remoteEdit('t-1', 'v2-remote');
    expect(sim.conflicts).toEqual([{ id: 't-1', fp: 'v2-remote' }]);
    expect(sim.local.get('t-1')).toBe('v2-local');
    expect(sim.pending()).toBe(0);
  });
});

describe('known limitation (see DRILLS.md follow-up)', () => {
  it('a late echo of an older push is mistaken for a genuine remote edit', () => {
    const guard = new EchoGuard();
    guard.recordPush('t-1', 'v1');
    guard.recordPush('t-1', 'v2');
    expect(guard.decide('t-1', 'v1', 'v2')).toBe('apply');
  });
});
