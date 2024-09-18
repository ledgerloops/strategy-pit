import EventEmitter from "node:events";
import { genRanHex } from "../genRanHex.js";

export class TracesEngine extends EventEmitter {
  tracesCreated = {};
  tracesForwardedFrom = {};
  tracesForwardedTo = {};
  tracesByPath = {};
  getLegsCreated(probeId: string, traceId: string): { [to: string]: string } | undefined {
    return this.tracesCreated[probeId]?.[traceId];
  }
  getLegsForwardedFrom(probeId: string, traceId: string): { [to: string]: string } | undefined {
    return this.tracesForwardedFrom[probeId]?.[traceId];
  }
  getLegsForwardedTo(probeId: string, traceId: string): { [to: string]: string } | undefined {
    return this.tracesForwardedTo[probeId]?.[traceId];
  }
  wasCreatedByUs(probeId: string, traceId: string, legId: string): string | undefined {
    const legs = this.getLegsCreated(probeId, traceId);
    if (typeof legs !== 'undefined') {
      return Object.keys(legs).find((to) => legs[to] === legId);
    }
    return undefined;
  }
  getOtherLeg(probeId: string, traceId: string, thisLegId: string): string | undefined {
    const legs = this.getLegsForwardedFrom(probeId, traceId);
    this.emit('debug', `Looking for other leg ${probeId} ${traceId} ${thisLegId} in ${JSON.stringify(legs)}`);
    if (typeof legs === 'undefined') {
      return undefined;
    }
    return Object.keys(legs).find((to) => legs[to] !== thisLegId);
  }
  logIncomingTraceMessage(from: string, probeId: string, traceId: string, legId: string): void {
    if (typeof this.tracesForwardedFrom[probeId] === 'undefined') {
      this.tracesForwardedFrom[probeId] = {};
    }
    if (typeof this.tracesForwardedFrom[probeId][traceId] === 'undefined') {
      this.tracesForwardedFrom[probeId][traceId] = {};
    }
    this.tracesForwardedFrom[probeId][traceId][from] = legId;
    this.emit('debug', `tracesForwardedFrom now looks like this: ${JSON.stringify(this.tracesForwardedFrom)}`)

  }
  logTracePath(from: string, to: string, probeId: string, traceId: string, legId: string): void {
    if (typeof this.tracesByPath[`${from} ${to}`] === 'undefined') {
      this.tracesByPath[`${from} ${to}`] = [];
    }
    if (this.tracesByPath[`${from} ${to}`].indexOf(`${probeId} ${traceId} ${legId}`) === -1) {
      this.tracesByPath[`${from} ${to}`].push(`${probeId} ${traceId} ${legId}`);
    }
    this.emit('debug', `[TracesEngine] tracesByPath now: ${JSON.stringify(this.tracesByPath)}`);
  }
  logTraceMessage(from: string, to: string, probeId: string, traceId: string, legId: string): void {
    this.logIncomingTraceMessage(from, probeId, traceId, legId);
    this.logTracePath(from, to, probeId, traceId, legId);
    this.emit('debug', `logTraceMessage from="${from}" to="${to}" trace="${probeId} ${traceId} ${legId}"`);
    if (typeof this.tracesForwardedTo[probeId] === 'undefined') {
      this.tracesForwardedTo[probeId] = {};
    }
    if (typeof this.tracesForwardedTo[probeId][traceId] === 'undefined') {
      this.tracesForwardedTo[probeId][traceId] = {};
    }
    this.tracesForwardedTo[probeId][traceId][to] = legId;
    this.emit('debug', `tracesForwardedTo now looks like this: ${JSON.stringify(this.tracesForwardedTo)}`)
  }
  forwardTraceMessage(sender: string, probeId: string, traceId: string, legId: string, nextHops: string[]): void {
    nextHops.forEach((to) => {
      this.emit('debug', `[TracesEngine] sending message to ${to}: trace ${probeId} ${traceId} ${legId}`);
      this.logTraceMessage(sender, to, probeId, traceId, legId);
      this.emit('message', to, `trace ${probeId} ${traceId} ${legId}`);
    });
  }
  seenThisTraceBefore(probeId: string, traceId: string, legId: string): boolean {
    const legs = this.getLegsForwardedFrom(probeId, traceId);
    this.emit('debug', `checking if we have seenThisTraceBefore ${probeId} ${traceId} ${legId} in ${JSON.stringify(legs)}`);
    if (typeof legs === 'undefined') {
      return false;
    }
    return Object.values(legs).includes(legId);
  }
  handleTraceMessage(sender: string, message: string): void {
    this.emit('debug', `[TraceEngine] handling trace message from ${sender}: ${message}`);
    const [messageType, probeId, traceId, legId] = message.split(' ');
    if (messageType !== 'trace') {
      throw new Error(`expected trace message but got ${messageType}`);
    }
    const to = this.wasCreatedByUs(probeId, traceId, legId);
    if (to !== undefined) {
      this.emit('debug', `loop-found ${probeId} ${traceId} ${legId} ${to} ${sender}`);
      this.emit('loop-found', probeId, traceId, legId, to, sender);
      return;
    }
    if (this.seenThisTraceBefore(probeId, traceId, legId)) {
      this.emit('debug', `seen this trace before ${probeId} ${traceId} ${legId}`);
      return;
    }
    this.logIncomingTraceMessage(sender, probeId, traceId, legId);
    this.emit('lookup-probe', probeId, (probeFrom: string[], probeTo: string[]) => {
      if (probeFrom.includes(sender)) {
        this.emit('debug', `[TraceEngine] forwarding a probe-wise trace message from ${sender}: ${message}`);
        this.forwardTraceMessage(sender, probeId, traceId, legId, probeTo);
      } else if (probeTo.includes(sender)) {
        this.emit('debug', `[TraceEngine] forwarding a counter-probe-wise trace message from ${sender}: ${message}`);
        const otherLeg = this.getOtherLeg(probeId, traceId, legId);
        this.emit('debug', `[TraceEngine] in the context of trace message from ${sender}: ${message}, we found these counter-probe-wise next hops: [${probeFrom.join(', ')}], and otherLeg ${otherLeg}`);
        if (typeof otherLeg === 'undefined') {
          this.emit('debug', `[TraceEngine] forwardTraceMessage ${sender} ${probeId} ${traceId} ${legId} ${probeFrom}`);
          this.forwardTraceMessage(sender, probeId, traceId, legId, probeFrom);
        } else {
          this.emit('debug', `[TraceEngine] found otherLeg ${otherLeg} for trace ${traceId} of probe ${probeId}`);
          if (otherLeg === sender) {
            this.emit('debug', `UNEXPECTED: Received two different legs from the same node`);
          }
          this.logTraceMessage(sender, otherLeg, probeId, traceId, legId);
          this.emit('message', otherLeg, `trace ${probeId} ${traceId} ${legId}`);
        }
      } else {
        this.emit('debug', `received trace message '${message}' from unexpected sender ${sender}`);
        // throw new Error(`received trace message '${message}' from unexpected sender ${sender}`);
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
  getOtherParty(firstParty: string, probeId: string, traceId: string, legId: string): string | undefined {
    const legsCreated = this.getLegsCreated(probeId, traceId);
    this.emit('debug', `Looking for a party in ${probeId} ${traceId} with ${legId} other than ${firstParty} in created: ${JSON.stringify(legsCreated)}`);
    if (typeof legsCreated !== 'undefined') {
      return Object.keys(legsCreated).find((to) => legsCreated[to] === legId && to !== firstParty);
    }
    const legsForwarded = this.getLegsForwardedFrom(probeId, traceId);
    this.emit('debug', `Looking for a party in ${probeId} ${traceId} with ${legId} other than ${firstParty} in forwarded: ${JSON.stringify(legsForwarded)}`);
    if (typeof legsForwarded !== 'undefined') {
      return Object.keys(legsForwarded).find((to) => legsForwarded[to] === legId && to !== firstParty);
    }
    return undefined;
  }
  getTraceTo ({ probeId, traceId, legId }: { probeId: string, traceId: string, legId: string }): string | undefined {
    const legsCreated = this.getLegsCreated(probeId, traceId);
    this.emit('debug', `Looking for a party in ${probeId} ${traceId} with ${legId} in created: ${JSON.stringify(legsCreated)}`);
    if (typeof legsCreated !== 'undefined') {
      const result = Object.keys(legsCreated).find((to) => legsCreated[to] === legId);
      if (result) {
        return result;
      }
    }
    const legsForwardedTo = this.getLegsForwardedTo(probeId, traceId);
    this.emit('debug', `Looking for a party in ${probeId} ${traceId} with ${legId} in forwarded: ${JSON.stringify(legsForwardedTo)}`);
    if (typeof legsForwardedTo !== 'undefined') {
      const result = Object.keys(legsForwardedTo).find((to) => legsForwardedTo[to] === legId);
      if (result) {
        return result;
      }
    }
    return undefined;
  }
  lookup ({ sender, probeId, traceId, legId }: { sender: string, probeId: string, traceId: string, legId: string }): { to: string, equivalent: string[] } | undefined {
    this.emit('debug', `[TraceEngine] lookup ${sender} ${probeId} ${traceId} ${legId}`);
      const traceTo = this.getTraceTo({ probeId, traceId, legId });
    const equivalent = [];
    if (traceTo) {
      return {
        to: traceTo,
        equivalent
      };
    }
    return undefined;
  }
}
