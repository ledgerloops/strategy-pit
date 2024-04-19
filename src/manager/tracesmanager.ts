import EventEmitter from "node:events";
import { genRanHex } from "../genRanHex.js";

export class TracesManager extends EventEmitter {
  tracesCreated = {};
  tracesForwarded = {};
  getLegs(probeId: string, traceId: string): { [to: string]: string } | undefined {
    if (typeof this.tracesForwarded[probeId] === 'undefined') {
      return undefined;
    }
    return this.tracesForwarded[probeId][traceId];
  }
  getOtherLeg(probeId: string, traceId: string, thisLegId: string): string | undefined {
    const legs = this.getLegs(probeId, traceId);
    if (typeof legs === 'undefined') {
      return undefined;
    }
    return Object.keys(legs).find((to) => legs[to] !== thisLegId);
  }
  handleTraceMessage(sender: string, message: string): void {
    const [messageType, probeId, traceId, legId] = message.split(' ');
    if (messageType !== 'trace') {
      throw new Error(`expected trace message but got ${messageType}`);
    }
    this.emit('lookup-probe', probeId, (probeFrom) => {
      const otherLeg = this.getOtherLeg(probeId, traceId, legId);
      if (typeof otherLeg === 'undefined') {
        const legs = {};
        probeFrom.forEach((from) => {
          legs[from] = legId;
          this.emit('message', from, `trace ${probeId} ${traceId} ${legId}`);
        });
        if (typeof this.tracesForwarded[probeId] === 'undefined') {
          this.tracesForwarded[probeId] = {};
        }
        this.tracesForwarded[probeId][traceId] = legs;
      } else {
        if (otherLeg === sender) {
          this.emit('debug', `UNEXPECTED: Received two different legs from the same node`);
        }
        this.emit('message', otherLeg, `trace ${probeId} ${traceId} ${legId}`)
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
  