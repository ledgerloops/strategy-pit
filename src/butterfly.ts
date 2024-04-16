import { Probe as ProbeMessage, Loop as LoopMessage, Meet } from "../src/messages.js";
import { BasicMessageForwarder } from "../src/node.js";
import { Polite } from "../src/polite.js";
import { genRanHex } from "./util.js";

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

export class ButterflyProbeStore {
  private probes: {
    [id: string]: Probe
  } = {};

  constructor() {}
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

export class Butterfly extends Polite {
  protected probeStore: ButterflyProbeStore = new ButterflyProbeStore();
  protected debugLog: string[] = [];
  private loopsFound: string[] = [];

  constructor(name: string, messageForwarder?: BasicMessageForwarder) {
    super(name, messageForwarder);
  }
  protected sendProbe(to: string, message: ProbeMessage): void {
    const probe = this.probeStore.get((message as ProbeMessage).getId());
    probe.recordOutgoing(to);
    this.sendMessage(to, message);
  }
  protected async offerProbe(friend: string, probeId: string, homeMinted: boolean): Promise<void> {
    const probe = this.probeStore.ensure(probeId, homeMinted);
    await this.semaphore(friend);
    if (probe.isVirginFor(friend)) {
      this.sendProbe(friend, new ProbeMessage(probeId));
    }
  }
  protected async offerAllFloodProbes(other: string): Promise<void> {
    const promises = this.probeStore.getKeys().map((probeId) => {
      this.debugLog.push(`OFFERING PROBE ${probeId} TO ${other}`);
      // setting homeMinted to false but we don't expect it to matter since this probe already exists
      return this.offerProbe(other, probeId, false);
    });
    await Promise.all(promises);
  }
  protected async offerFloodProbeToAll(probeId: string, homeMinted: boolean): Promise<void> {
    const promises = this.getFriends().map(friend => {
      return this.offerProbe(friend, probeId, homeMinted);
    });
    await Promise.all(promises);
  }
  protected createFloodProbe(): Promise<void> {
    return this.offerFloodProbeToAll(genRanHex(8), true);
  }
  protected createPinnedFloodProbe(recipient: string): void {
    const probeForNewLink = genRanHex(8);
    this.offerProbe(recipient, probeForNewLink, true);
  }
  // when this node has sent a `meet` message
  async onMeet(other: string): Promise<void> {
    this.debugLog.push(`I meet ${other}, and offer them all my flood probes`);
    this.sendMessage(other, new Meet());
    await this.offerAllFloodProbes(other);
    await this.createFloodProbe();
  }
  // when this node has received a `meet` message
  handleMeetMessage(sender: string): void {
    this.debugLog.push(`MEET MESSAGE FROM ${sender}, offering all flood probes`);
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
      probe.recordIncoming(sender);
      this.offerFloodProbeToAll(message.getId(), false);
    } else {
      if (probe.isVirginFor(sender)) {
        this.debugLog.push(`PROBE ${message.getId()} ALREADY KNOWN TO US, VIRGIN FOR ${sender}!`);
        if (probe.isHomeMinted()) {
          this.createLoopTrace(message.getId(), sender);
        } else {
          this.createPinnedFloodProbe(sender);
        }
      } else {
        this.debugLog.push(`PROBE ${message.getId()} ALREADY KNOWN TO US, BUT NOT VIRGIN FOR ${sender}!`);
      }
    }
  }
  handleLoopMessage(sender: string, message: LoopMessage): void {
    const probe: Probe | undefined = this.probeStore.get(message.getProbeId());
    this.debugLog.push(`LOOP TRACE ${message.getLoopId()} FOR PROBE ${message.getProbeId()} COMING TO US FROM SENDER ${sender}`);
    this.debugLog.push(`PROBE ${message.getProbeId()} HAS TRACES: ${probe.getTraces().map(trace => trace.getTraceId()).join(' ')}`);
    this.debugLog.push(`PROBE ${message.getProbeId()} HAS FROM: ${probe.getFrom().join(' ')}`);
    this.debugLog.push(`PROBE ${message.getProbeId()} HAS TO: ${probe.getTo().join(' ')}`);
    if (typeof probe === 'undefined') {
      this.debugLog.push(`UNEXPECTED: PROBE UNKNOWN TO US!`);
      return;
    }
    if (probe.getFrom().length === 0) {
      this.debugLog.push(`OUR LOOP TRACE CAME BACK!`);
      this.loopsFound.push(message.getProbeId() + ':' + message.getLoopId());
      return;
    }
    if (probe.getFrom().length > 1) {
      this.debugLog.push(`UNEXPECTED: PROBE HAS MORE THAN ONE FROM: ${probe.getFrom().join(' ')}!`);
      return;
    }
    this.debugLog.push(`FORWARDING LOOP TO ${probe.getFrom()[0]}`);
    const recipient = probe.getFrom()[0];
    this.sendMessage(recipient, new LoopMessage(message.getProbeId(), message.getLoopId()));
    const trace = new Trace(sender, this.getName(), message.getLoopId());
    probe.addTrace(trace);
  }
  getLoops(): string[] {
    return this.loopsFound;
  }
  getLog(): string[] {
    return this.debugLog;
  }
}
