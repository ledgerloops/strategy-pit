import { Probe as ProbeMessage, Loop as LoopMessage } from "./messages.js";
import { genRanHex } from "./util.js";
import { Node, BasicMessageForwarder } from "./node.js";

function objectMap(object, mapFn): object {
  return Object.keys(object).reduce(function(result, key) {
    result[key] = mapFn(object[key])
    return result
  }, {})
}

export class Trace {
  private traceId: string;
  private from: string | undefined;
  private to: string;
  constructor(from: string | undefined, to: string, traceId: string) {
    this.traceId = traceId;
    this.to = to;
    this.from = from;
  }
  getFrom(): string | undefined {
    return this.from;
  }
  getTo(): string {
    return this.to;
  }
  getTraceId(): string {
    return this.traceId;
  }
}
export class Probe {
  private from: string[];
  private to: string[];
  private homeMinted: boolean;
  private traces: Trace[] = [];
  constructor (from: string[], to: string[], homeMinted: boolean) {
    this.from = from;
    this.to = to;
    this.homeMinted = homeMinted;
  }
  getFrom(): string[] {
    return this.from;
  }
  addFrom(from: string): void {
    this.from.push(from);
  }
  getTo(): string[] {
    return this.to;
  }
  addTo(to: string): void {
    this.to.push(to);
  }
  isHomeMinted(): boolean {
    return this.homeMinted;
  }
  recordIncoming(from: string): void {
    this.from.push(from);
  }
  recordOutgoing(to: string): void {
    this.to.push(to);
  }
  isVirginFor(newFrom: string): boolean {
    return !this.from.includes(newFrom) && !this.to.includes(newFrom);
  }
  getTraces(): Trace[] {
    return this.traces;
  }
  addTrace(trace: Trace): void {
    this.traces.push(trace);
  }
  toJson(): {
    from: string[],
    to: string[],
    homeMinted: boolean,
    traces: {
      from: string | undefined,
      to: string,
      traceId: string
    }[]
   } {
    return {
      from: this.from,
      to: this.to,
      homeMinted: this.homeMinted,
      traces: this.traces.map(trace => {
        return {
          from: trace.getFrom(),
          to: trace.getTo(),
          traceId: trace.getTraceId()
        };
      })
    };
  }
}

export class StingrayProbeStore {
  private probes: {
    [id: string]: Probe
  } = {};
  constructor() {}
  // has(id: string): boolean {
  //   return (typeof this.probes[id] !== 'undefined');
  // }
  get(id: string): Probe | undefined {
    return this.probes[id];
  }
  ensure(id: string, homeMinted: boolean): Probe {
    if (typeof this.probes[id] === 'undefined') {
      this.probes[id] = new Probe([], [], homeMinted);
    }
    return this.probes[id];
  }
  getKeys(): string[] {
    return Object.keys(this.probes);
  }
  getProbes(): {
    [id: string]: {
      from: string[],
      to: string[],
      homeMinted: boolean,
      traces: {
        from: string | undefined,
        to: string,
        traceId: string
      }[]
     }
  } {
    return objectMap(this.probes, (probe => probe.toJson())) as {
      [id: string]: {
        from: string[],
        to: string[],
        homeMinted: boolean,
        traces: {
          from: string | undefined,
          to: string,
          traceId: string
        }[]
       }
    };
  }
}

// export class StingrayLoopStore {
//   private loops: {
//     [probeId: string]: {
//       [loopId: string]: {
//         from: string[];
//         to: string[];
//         homeMinted: boolean;
//       }
//     }
//   } = {};
//   constructor() {}
//   has(probeId: string, loopId: string): boolean {
//     return ((typeof this.loops[probeId] !== 'undefined') && (typeof this.loops[probeId][loopId] !== 'undefined'));
//   }
//   get(probeId: string, loopId: string): {
//     from: string[];
//     to: string[];
//   } {
//     return this.loops[probeId][loopId];
//   }
//   haveSentTo(friend: string, probeId: string, loopId: string): boolean {
//     const { to } = this.get(probeId, loopId);
//     return (to.includes(friend));
//   }
//   haveReceivedFrom(friend: string, probeId: string, loopId: string): boolean {
//     const { from } = this.get(probeId, loopId);
//     return (from.includes(friend));
//   }
//   haveSentOrReceived(friend: string, probeId: string, loopId: string): boolean {
//     const { from, to } = this.get(probeId, loopId);
//     return (from.includes(friend) || to.includes(friend));
//   }
//   ensure(probeId: string, loopId: string, homeMinted: boolean): Probe {
//     if (typeof this.loops[probeId] === 'undefined') {
//       this.loops[probeId] = {};
//     }
//     if (typeof this.loops[probeId][loopId] === 'undefined') {
//       this.loops[probeId][loopId] = { from: [], to: [], homeMinted };
//     }
//     return this.loops[probeId][loopId];
//   }
//   recordIncoming(probeId: string, loopId: string, from: string): void {
//     this.ensure(probeId, loopId, false);
//     this.loops[probeId][loopId].from.push(from);
//   }
//   recordOutgoing(probeId: string, loopId: string, to: string, homeMinted: boolean): void {
//     this.ensure(probeId, loopId, homeMinted);
//     this.loops[probeId][loopId].to.push(to);
//   }
//   getKeys(): string[] {
//     const loops: string[] = [];
//     Object.keys(this.loops).forEach(probeId => Object.keys(this.loops[probeId]).forEach(loopId => loops.push(`${probeId}:${loopId}`)));
//     return loops;
//   }
//   getLoops(): {
//     [probeId: string]: {
//       [loopId: string]: {
//         from: string[];
//         to: string[];
//       }
//     }
//   } {
//     return this.loops;
//   }
// }

// Stingray nodes always send all the probes they can to all their friends.
export class Stingray extends Node {
  protected probeStore: StingrayProbeStore = new StingrayProbeStore();
  // protected loopStore: StingrayLoopStore = new StingrayLoopStore();

  constructor(name: string, messageForwarder?: BasicMessageForwarder) {
    super(name, messageForwarder);
  }
  protected offerProbe(friend: string, probeId: string, homeMinted: boolean): void {
    const probe = this.probeStore.ensure(probeId, homeMinted);
    if (probe.isVirginFor(friend)) {
      probe.recordOutgoing(friend);
      this.sendMessage(friend, new ProbeMessage(probeId));
    }
  }
  protected offerAllFloodProbes(other: string): void {
    this.probeStore.getKeys().forEach((probeId) => {
      // setting homeMinted to false but we don't expect it to matter since this probe already exists
      this.offerProbe(other, probeId, false);
    });
  }
  protected offerFloodProbeToAll(probeId: string, homeMinted: boolean): void {
    this.getFriends().forEach(friend => {
      this.offerProbe(friend, probeId, homeMinted);
    });
  }
  protected createFloodProbe(): void {
    this.offerFloodProbeToAll(genRanHex(8), true);
  }
  protected createPinnedFloodProbe(recipient: string): void {
    const probeForNewLink = genRanHex(8);
    this.offerProbe(recipient, probeForNewLink, true);
  }
  // when this node has sent a `meet` message
  onMeet(other: string): void {
    this.offerAllFloodProbes(other);
    this.createFloodProbe();
  }
  // when this node has received a `meet` message
  handleMeetMessage(sender: string): void {
    this.offerAllFloodProbes(sender);
  }
  getProbes(): {
    [id: string]: {
      from: string[],
      to: string[],
      homeMinted: boolean,
      traces: {
        from: string | undefined,
        to: string,
        traceId: string
      }[]
     }
  } {
    return this.probeStore.getProbes();
  }
  createLoopTrace(probeId: string, friend: string): void {
    const loopId = genRanHex(8);
    const trace = new Trace(undefined, friend, loopId);
    const probe = this.probeStore.get(probeId);
    probe.addTrace(trace);
    this.sendMessage(friend, new LoopMessage(probeId, loopId));
  }
  handleProbeMessage(sender: string, message: ProbeMessage): void {
    let probe: Probe | undefined = this.probeStore.get(message.getId());
    if (typeof probe === 'undefined') {
      // INCOMING PROBE IS NEW TO US, FLOOD IT FORWARD
      probe = this.probeStore.ensure(message.getId(), false);
      probe.addFrom(sender);
      this.offerFloodProbeToAll(message.getId(), false);
    } else {
      if (probe.isVirginFor(sender)) {
        if (probe.isHomeMinted()) {
          this.createLoopTrace(message.getId(), sender);
        } else {
          this.createPinnedFloodProbe(sender);
        }

      }
    }
  }
  handleLoopMessage(sender: string, message: LoopMessage): void {
    const probe: Probe | undefined = this.probeStore.get(message.getProbeId());
    // console.log(`LOOP TRACE ${message.getLoopId()} FOR PROBE ${message.getProbeId()} COMING TO US FROM SENDER ${sender}`);
    if (typeof probe === 'undefined') {
      // console.log(`UNEXPECTED: PROBE UNKNOWN TO US!`);
      return;
    }
    if (probe.getFrom().length != 1) {
      console.log(`UNEXPECTED: PROBE DOES NOT HAVE ONE FROM: ${probe.getFrom().join(' ')}!`);
      return;
    }
    const recipient = probe.getFrom()[0];
    this.sendMessage(recipient, new LoopMessage(message.getProbeId(), message.getLoopId()));
    const trace = new Trace(sender, this.getName(), message.getLoopId());
    probe.addTrace(trace);
  }
  getLoops(): string[] {
    const loops: string[] = [];
    Object.keys(this.probeStore.getProbes()).forEach(probeId => {
      const traces = this.probeStore.get(probeId).getTraces();
      Object.keys(traces).forEach(traceId => {
        if (typeof traces[traceId].getFrom() !== 'undefined') {
          loops.push(`${probeId}:${traceId}`);
        }
      });
    });
    return loops;
  }
}
