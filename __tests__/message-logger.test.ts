/* eslint-disable @typescript-eslint/no-explicit-any */
import { Loop, Probe } from '../src/messages.js';

describe('MessageForwarder', () => {
  it('logs messages', async () => {
    const { MessageForwarder } = await import('../src/node.js');
    const logger = new MessageForwarder();
    const probe = new Probe('probe-alice-bob');
    const loop = new Loop('probe-alice-bob', 'Hi');
    logger.logMessageSent('Alice', 'Bob', probe);
    logger.logMessageReceived('Alice', 'Bob', probe);
    logger.logMessageSent('Bob', 'Alice', loop);
    logger.logMessageReceived('Bob', 'Alice', loop);
    expect(logger.getLocalLog('Alice')).toEqual([
      "TO[Bob] probe probe-alice-bob",
      "FROM[Bob] loop probe-alice-bob Hi",
    ]);
    expect(logger.getFullLog(true)).toEqual([
      "[Alice]->[Bob] probe probe-alice-bob",
      "[Alice]>-[Bob] probe probe-alice-bob",
      "[Bob]->[Alice] loop probe-alice-bob Hi",
      "[Bob]>-[Alice] loop probe-alice-bob Hi",
    ]);
    expect(logger.getFullLog()).toEqual([
      "[Alice]->[Bob] probe probe-alice-bob",
      "[Bob]->[Alice] loop probe-alice-bob Hi",
    ]);

  });
});