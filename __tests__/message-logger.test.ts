/* eslint-disable @typescript-eslint/no-explicit-any */
import { TraceMessage, ProbeMessage } from '../src/messages.js';

describe('BasicMessageForwarder', () => {
  it('logs messages', async () => {
    const { BasicMessageForwarder } = await import('../src/node.js');
    const logger = new BasicMessageForwarder();
    const probe = new ProbeMessage('probe-alice-bob');
    const trace = new TraceMessage('probe-alice-bob', 'Hi', 'Ho');
    logger.logMessageSent('Alice', 'Bob', probe);
    logger.logMessageReceived('Alice', 'Bob', probe);
    logger.logMessageSent('Bob', 'Alice', trace);
    logger.logMessageReceived('Bob', 'Alice', trace);
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