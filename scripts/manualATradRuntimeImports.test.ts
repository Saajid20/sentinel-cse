import { describe, expect, it } from 'vitest';

describe('ATrad script runtime imports', () => {
  it('loads the manual ATrad script modules without missing read-only safety exports', async () => {
    const [loginModule, recordModule, observeModule, loginAndObserveModule] = await Promise.all([
      import('./manualATradLogin.js'),
      import('./manualATradRecordSession.js'),
      import('./manualATradObserveOnce.js'),
      import('./manualATradLoginAndObserve.js')
    ]);

    expect(loginModule.runManualATradLogin).toBeTypeOf('function');
    expect(recordModule.runManualATradRecordSession).toBeTypeOf('function');
    expect(observeModule.runManualATradObserveOnce).toBeTypeOf('function');
    expect(loginAndObserveModule.runManualATradLoginAndObserve).toBeTypeOf('function');
  });
});
