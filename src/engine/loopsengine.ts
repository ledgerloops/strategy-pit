import EventEmitter from "events";
import { genRanHex } from "../genRanHex.js";
import { createHmac } from "node:crypto";

export class LoopsEngine extends EventEmitter {
  loops: string[];
  lifts: {
    [hash: string]: {
      loop: string,
      legId: string,
      secret: string,
    }
  }
  constructor() {
    super();
    this.loops = [];
    this.lifts = {};
  }
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  handleLoopFound(probeId: string, traceId: string, legId: string, outgoing: { name: string, maxBalance: number, exchangeRate: number }, incoming: { name: string, maxBalance: number, exchangeRate: number }): void {
    this.loops.push(`${probeId} ${traceId}`);
    this.emit('debug', `${probeId} ${traceId} ${legId} ${JSON.stringify(outgoing)} ${JSON.stringify(incoming)}`);
    const secret = genRanHex(32);
    const hash = createHmac('sha256', secret)
              //  .update('I love cupcakes')
               .digest('hex');
    // console.log(hash);

    // const hash: string = SHA256(secret).toString();
    this.emit('message', outgoing.name, `lift ${probeId} ${traceId} ${legId} ${hash}`);  
    this.lifts[hash] = {
      loop: `${probeId} ${traceId}`,
      legId,
      secret,
    };
  }
  handleLiftMessage(probeId: string, traceId: string, legId: string, outgoing: { maxBalance: number, exchangeRate: number }, incoming: { maxBalance: number, exchangeRate: number }): void {
    this.emit('debug', `${probeId} ${traceId} ${legId} ${JSON.stringify(outgoing)} ${JSON.stringify(incoming)}`);
    // this.loops.push(`${probeId} ${traceId}`);
  }
  getLoops(): string[] {
    return this.loops;
  }
}
