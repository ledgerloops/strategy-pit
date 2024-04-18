import { ProbeMessage as ProbeMessage, TraceMessage as TraceMessage, MeetMessage, Message } from "./messages.js";
import { genRanHex } from "./genRanHex.js";
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
  getTo(): string[] {
    return this.to;
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

// Stingray nodes always send all the probes they can to all their friends.
export class Stingray extends Node {
  protected probeStore: StingrayProbeStore = new StingrayProbeStore();
  // protected loopStore: StingrayLoopStore = new StingrayLoopStore();
  protected log: string[] = [];
  private loopsFound: string[] = [];

  constructor(name: string, messageForwarder?: BasicMessageForwarder) {
    super(name, messageForwarder);
  }
  protected sendMessage(to: string, message: Message): void {
    if (message.getMessageType() === 'probe') {
      const probe = this.probeStore.get((message as ProbeMessage).getId());
      probe.recordOutgoing(to);
    }
    super.sendMessage(to, message);
  }
  protected offerProbe(friend: string, probeId: string, homeMinted: boolean): void {
    const probe = this.probeStore.ensure(probeId, homeMinted);
    if (probe.isVirginFor(friend)) {
      this.sendMessage(friend, new ProbeMessage(probeId));
    }
  }
  protected offerAllFloodProbes(other: string): void {
    this.probeStore.getKeys().forEach((probeId) => {
      this.log.push(`OFFERING PROBE ${probeId} TO ${other}`);
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
    this.log.push(`I meet ${other}, and offer them all my flood probes`);
    this.sendMessage(other, new MeetMessage());
    this.offerAllFloodProbes(other);
    this.createFloodProbe();
  }
  // when this node has received a `meet` message
  handleMeetMessage(sender: string): void {
    this.log.push(`MEET MESSAGE FROM ${sender}, offering all flood probes`);
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
  createTrace(probeId: string, friend: string): void {
    const traceId = genRanHex(8);
    const trace = new Trace(undefined, friend, traceId);
    const probe = this.probeStore.get(probeId);
    probe.addTrace(trace);
    this.sendMessage(friend, new TraceMessage(probeId, traceId, 'default'));
  }
  handleProbeMessage(sender: string, message: ProbeMessage): void {
    let probe: Probe | undefined = this.probeStore.get(message.getId());
    if (typeof probe === 'undefined') {
      // INCOMING PROBE IS NEW TO US, FLOOD IT FORWARD
      probe = this.probeStore.ensure(message.getId(), false);
      probe.recordIncoming(sender);
      this.offerFloodProbeToAll(message.getId(), false);
    } else {
      if (probe.isVirginFor(sender)) {
        this.log.push(`PROBE ${message.getId()} ALREADY KNOWN TO US, VIRGIN FOR ${sender}!`);
        if (probe.isHomeMinted()) {
          this.createTrace(message.getId(), sender);
        } else {
          this.createPinnedFloodProbe(sender);
        }
      } else {
        this.log.push(`PROBE ${message.getId()} ALREADY KNOWN TO US, BUT NOT VIRGIN FOR ${sender}!`);
      }
    }
  }
  handleTraceMessage(sender: string, message: TraceMessage): void {
    const probe: Probe | undefined = this.probeStore.get(message.getProbeId());
    this.log.push(`TRACE ${message.getTraceId()} FOR PROBE ${message.getProbeId()} COMING TO US FROM SENDER ${sender}`);
    this.log.push(`PROBE ${message.getProbeId()} HAS TRACES: ${probe.getTraces().map(trace => trace.getTraceId()).join(' ')}`);
    this.log.push(`PROBE ${message.getProbeId()} HAS FROM: ${probe.getFrom().join(' ')}`);
    this.log.push(`PROBE ${message.getProbeId()} HAS TO: ${probe.getTo().join(' ')}`);
    if (typeof probe === 'undefined') {
      this.log.push(`UNEXPECTED: PROBE UNKNOWN TO US!`);
      return;
    }
    if (probe.getFrom().length === 0) {
      this.log.push(`OUR TRACE CAME BACK!`);
      this.loopsFound.push(message.getProbeId() + ':' + message.getTraceId());
      return;
    }
    if (probe.getFrom().length > 1) {
      this.log.push(`UNEXPECTED: PROBE HAS MORE THAN ONE FROM: ${probe.getFrom().join(' ')}!`);
      return;
    }
    this.log.push(`FORWARDING TRACE TO ${probe.getFrom()[0]}`);
    const recipient = probe.getFrom()[0];
    this.sendMessage(recipient, new TraceMessage(message.getProbeId(), message.getTraceId(), 'default'));
    const trace = new Trace(sender, this.getName(), message.getTraceId());
    probe.addTrace(trace);
  }
  getLoops(): string[] {
    return this.loopsFound;
  }
  getLog(): string[] {
    return this.log;
  }
}
