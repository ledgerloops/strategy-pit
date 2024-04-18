import { ProbeMessage, TraceMessage } from "./messages.js";
import { genRanHex } from "./genRanHex.js";
import { Salmon } from "./salmon.js";
import { BasicMessageForwarder } from "./node.js";

// Pelican nodes always send all the probes they can to all their friends.
// Unlike Salmons, Pelicans are able to fork multiple Loop messages from one successful Probe.
export class Pelican extends Salmon {
  protected pelicanLoops: {
    [probeId: string]: {
      [traceId: string]: boolean
    }
  } = {};
  constructor(name: string, messageForwarder?: BasicMessageForwarder) {
    super(name, messageForwarder);
  }
  protected sendExistingProbesToNewFriend(other: string): void {
    Object.entries(this.probes).forEach(([id, probes]) => {
      if (this.pelicanLoops[id]) {
        // console.log(`existing probe apparently looped back`);
      } else {
        if (typeof probes[other] === 'undefined') {
          this.probes[id][other] = true;
          this.sendMessage(other, new ProbeMessage(id));
        }
      }
    });
  }
  getLoops(): string[] {
    const loops: string[] = [];
    Object.keys(this.pelicanLoops).forEach(probeId => Object.keys(this.pelicanLoops[probeId]).forEach(traceId => loops.push(`${probeId}:${traceId}`)));
    return loops;
  }
  onLoopDetected(message: ProbeMessage): void {
    // console.log(`LOOP DETECTED!: ${this.name} already has probe ${message.getId()} from (or sent to) ${Object.keys(this.probes[message.getId()]).join(' and ')}`);
    const initialTraceId = genRanHex(8);
    if (typeof this.pelicanLoops[message.getId()] === 'undefined') {
      this.pelicanLoops[message.getId()] = {};
    }
    this.pelicanLoops[message.getId()][initialTraceId] = true;
    Object.keys(this.probes[message.getId()]).forEach(name => {
      this.sendMessage(name, new TraceMessage(message.getId(), initialTraceId, 'default'));
    });
  }

  handleTraceMessage(sender: string, message: TraceMessage): void {
    if (!this.pelicanLoops[message.getProbeId()] || !this.pelicanLoops[message.getProbeId()][message.getTraceId()]) {
        // console.log(`${this.name} received loop message about ${message.getProbeId()} from ${sender} - loop id ${message.getTraceId()}`);
      let traceId = message.getTraceId();
      Object.keys(this.probes[message.getProbeId()]).forEach(name => {
        if (name !== sender) {
          this.sendMessage(name, new TraceMessage(message.getProbeId(), traceId, 'default'));
          if (typeof this.pelicanLoops[message.getProbeId()] === 'undefined') {
            this.pelicanLoops[message.getProbeId()] = {};
          }
          this.pelicanLoops[message.getProbeId()][traceId] = true;

          // Make sure the next forward (in case of a fork) will use a different loop id
          traceId = genRanHex(8);
        }
      });
    } else {
      // console.log(`TRACE ${message.getProbeId()} IS NOT NEW TO ME`);
    }
  }
}
