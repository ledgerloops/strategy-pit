import EventEmitter from "node:events";
import { genRanHex } from "../genRanHex.js";

export class TracesManager extends EventEmitter {
  traces = {};
  storeTrace(probeId: string, probeFrom: string[], probeTo: string[], friend: string, traceId: string): void {
    if (typeof this.traces[probeId] === 'undefined') {
      this.traces[probeId] = { probeFrom, probeTo, traces: {} };
    }
    // FIXME: check if probeFrom and probeTo are the same as the ones we already have
    this.traces[probeId].traces[traceId] = friend;
  }
  createTrace(probeId: string, probeFrom: string[], probeTo: string[], friend: string): void {
    const traceId = genRanHex(8);
    this.storeTrace(probeId, probeFrom, probeTo, friend, traceId);
    this.emit('debug', `CREATING TRACE ${traceId} TO ${friend} FOR OUR HOME MINTED PROBE ${probeId}`);
    // this.emit('message', friend, `loop ${probeId} ${traceId}`);
    this.emit('message', friend, `trace ${probeId} ${traceId} default`);
  }  
  handleTraceMessage(sender: string, message: string): void {
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    const [ _messageType, probeId, traceId, legId ] = message.split(' ');
    this.emit('debug', `LEG ${legId} OF TRACE ${traceId} FOR PROBE ${probeId} COMING TO US FROM SENDER ${sender}`);

    const traces = this.traces[probeId].traces;
    for (let i = 0; i < traces.length; i++) {
      const trace = traces[i];
      if (trace.getTraceId() === traceId) {
        if (this.traces[probeId].from.length === 0) {
          this.emit('debug', `OUR TRACE CAME BACK!`);
          this.emit('loop-found', probeId, traceId);
          return;
        }
        if (this.traces[probeId].from.length > 1) {
          this.emit('debug', `UNEXPECTED: PROBE HAS MORE THAN ONE FROM: ${this.traces[probeId].from.join(' ')}!`);
          return;
        }
        this.emit('debug', `TRACE ${traceId} for probe ${probeId} ALREADY KNOWN TO US! NOT FORWARDING DUPLICATE MESSAGE`);
        return;
      }
    }
    this.emit('debug', `FORWARDING TRACE TO ${this.traces[probeId].from[0]}`);
    const recipient = this.traces[probeId].from[0];
    // this.emit('message', recipient, `loop ${probeId} ${traceId}`);
    this.emit('message', recipient, `trace ${probeId} ${traceId} default`);
    this.storeTrace(probeId, this.traces[probeId].probeFrom, this.traces[probeId].probeTo, sender, traceId);
  }

  handleProbeLoopback(probeId: string, situation: string, from: string[], to: string[]): void {
    this.emit('debug', `handleProbeLoopback ${probeId} ${situation} ${from.join(' ')} ${to.join(' ')}`);
    if (situation === 'root') {
      if (from.length < 1) {
        throw new Error('how can root situation probe loopback have no from?');
      }
      if (from.length > 1) {
        throw new Error('how can root situation probe loopback have more than 1 from?');
      }
      this.createTrace(probeId, from, to, from[0]);
    }
  }
}
  