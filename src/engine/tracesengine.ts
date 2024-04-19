import EventEmitter from "node:events";
import { genRanHex } from "../genRanHex.js";

export class TracesEngine extends EventEmitter {
  tracesCreated = {};
  tracesForwarded = {};
  getLegsForwarded(probeId: string, traceId: string): { [to: string]: string } | undefined {
    return this.tracesForwarded[probeId]?.[traceId];
  }
  getLegsCreated(probeId: string, traceId: string): { [to: string]: string } | undefined {
    return this.tracesCreated[probeId]?.[traceId];
  }
  wasCreatedByUs(probeId: string, traceId: string): boolean {
    return typeof this.getLegsCreated(probeId, traceId) !== 'undefined';
  }
  getOtherLeg(probeId: string, traceId: string, thisLegId: string): string | undefined {
    const legs = this.getLegsForwarded(probeId, traceId);
    this.emit('debug', `Looking for other leg ${probeId} ${traceId} ${thisLegId} in ${JSON.stringify(legs)}`);
    if (typeof legs === 'undefined') {
      return undefined;
    }
    return Object.keys(legs).find((to) => legs[to] !== thisLegId);
  }
  logTraceMessage(sender: string, probeId: string, traceId: string, legId: string): void {
    if (typeof this.tracesForwarded[probeId] === 'undefined') {
      this.tracesForwarded[probeId] = {};
    }
    if (typeof this.tracesForwarded[probeId][traceId] === 'undefined') {
      this.tracesForwarded[probeId][traceId] = {};
    }
    this.tracesForwarded[probeId][traceId][sender] = legId;
  }
  forwardTraceMessage(probeId: string, traceId: string, legId: string, nextHops: string[]): void {
    nextHops.forEach((from) => {
      this.emit('debug', `[TracesEngine] sending message to ${from}: trace ${probeId} ${traceId} ${legId}`);
      this.emit('message', from, `trace ${probeId} ${traceId} ${legId}`);
    });
  }
  handleTraceMessage(sender: string, message: string): void {
    this.emit('debug', `[TraceEngine] handling trace message from ${sender}: ${message}`);
    const [messageType, probeId, traceId, legId] = message.split(' ');
    if (this.wasCreatedByUs(probeId, traceId)) {
      this.emit('debug', `loop-found ${probeId} ${traceId}`);
      this.emit('loop-found', probeId, traceId);
      return;
    }
    if (messageType !== 'trace') {
      throw new Error(`expected trace message but got ${messageType}`);
    }
    this.logTraceMessage(sender,probeId, traceId, legId);
    this.emit('lookup-probe', probeId, (probeFrom: string[], probeTo: string[]) => {
      if (probeFrom.includes(sender)) {
        this.emit('debug', `[TraceEngine] forwarding a probe-wise trace message from ${sender}: ${message}`);
        this.forwardTraceMessage(probeId, traceId, legId, probeTo);
      } else if (probeTo.includes(sender)) {
        this.emit('debug', `[TraceEngine] forwarding a counter-probe-wise trace message from ${sender}: ${message}`);
        const otherLeg = this.getOtherLeg(probeId, traceId, legId);
        this.emit('debug', `[TraceEngine] in the context of trace message from ${sender}: ${message}, we found these counter-probe-wise next hops: [${probeFrom.join(', ')}], and otherLeg ${otherLeg}`);
        if (typeof otherLeg === 'undefined') {  
          this.forwardTraceMessage(probeId, traceId, legId, probeFrom);
        } else {
          this.emit('debug', `[TracesEngine] found otherLeg ${otherLeg} for trace ${traceId} of probe ${probeId}`);
          if (otherLeg === sender) {
            this.emit('debug', `UNEXPECTED: Received two different legs from the same node`);
          }
          this.emit('message', otherLeg, `trace ${probeId} ${traceId} ${legId}`);
        }
      } else {
        throw new Error(`received trace message '${message}' from unexpected sender ${sender}`);
      }
    });
  }

  handleProbeLoopback(probeId: string): void {
    this.emit('lookup-probe', probeId, (probeFrom) => {
      const traceId = genRanHex(8);
      const legs = {};
      probeFrom.forEach((from) => {
        const legId = genRanHex(8);
        legs[from] = legId;
        this.emit('message', from, `trace ${probeId} ${traceId} ${legId}`);
      });
      if (typeof this.tracesCreated[probeId] === 'undefined') {
        this.tracesCreated[probeId] = {};
      }
      this.tracesCreated[probeId][traceId] = legs;
    });
  }
}
  