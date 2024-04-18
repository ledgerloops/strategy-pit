import { ProbeMessage as ProbeMessage, TraceMessage as TraceMessage, MeetMessage, HaveProbesMessage, OkayToSendProbesMessage } from "../src/messages.js";
import { BasicMessageForwarder, HandRaisingStatus, Node } from "../src/node.js";
import { genRanHex } from "./genRanHex.js";

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
  private probeId: string;
  private from: string[];
  private to: string[];
  private homeMinted: boolean;
  private traces: Trace[] = [];

  constructor (probeId: string, from: string[], to: string[], homeMinted: boolean) {
    this.probeId = probeId;
    this.from = from;
    this.to = to;
    this.homeMinted = homeMinted;
  }
  getProbeId(): string {
    return this.probeId;
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
  isVirginFor(friend: string): boolean {
    return !this.from.includes(friend) && !this.to.includes(friend);
  }
  getTraces(): Trace[] {
    return this.traces;
  }
  addTrace(trace: Trace): void {
    this.traces.push(trace);
  }
  toObject(): {
    probeId: string,
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
      probeId: this.probeId,
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
      this.probes[id] = new Probe(id, [], [], homeMinted);
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

export class Butterfly extends Node {
  protected probeStore: ButterflyProbeStore = new ButterflyProbeStore();
  private loopsFound: string[] = [];
  private probesToOffer: {
    [friend: string] : string[]
  } = {};
  constructor(name: string, messageForwarder?: BasicMessageForwarder) {
    super(name, messageForwarder);
  }

  // Postpone sending of probes until we have received the okay-to-send-probes message
  protected raiseHand(to: string): void {
    this.friends[to].handRaisingStatus = HandRaisingStatus.Waiting;
    this.debugLog.push(`${this.name} raises hand to ${to}`);
    this.messageForwarder.forwardMessage(this, this.friends[to].node, new HaveProbesMessage());
  }

  protected handleHaveProbesMessage(from: string): void {
    this.friends[from].handRaisingStatus = HandRaisingStatus.Listening;
    super.sendMessage(from, new OkayToSendProbesMessage());
  }
  protected flushProbesQueue(friend: string): void {
    if (typeof this.probesToOffer[friend] !== 'undefined') {
      this.probesToOffer[friend].forEach(probeId => {
        const probe = this.probeStore.get(probeId);
        if (probe.isVirginFor(friend)) {
          this.debugLog.push(`QUEUEING PROBE ${probe.getProbeId()} TO ${friend} [3/4]`);
          probe.recordOutgoing(friend);
          const message = new ProbeMessage(probe.getProbeId());
          this.sendMessage(friend, message);
        }
      });
      delete this.friends[friend].promises;
    }
  }
  protected handleOkayToSendProbesMessage(friend: string): void {
    this.debugLog.push(`${this.name} receives okay-to-send-probes from ${friend}`);
    this.friends[friend].handRaisingStatus = HandRaisingStatus.Talking;
    this.flushProbesQueue(friend);
  }
  protected tryToSendProbes(friend: string): void {
    if (this.friends[friend].handRaisingStatus === HandRaisingStatus.Talking) {
      this.debugLog.push(`${this.name} is talking to ${friend}`);
      this.flushProbesQueue(friend);
    } else if (this.friends[friend].handRaisingStatus === HandRaisingStatus.Listening) {
      this.debugLog.push(`${this.name} starts waiting to talk to ${friend}`);
      this.raiseHand(friend);
    }
  }

  protected queueProbe(friend: string, probeId: string, homeMinted: boolean): void {
    this.probeStore.ensure(probeId, homeMinted);
    this.probesToOffer[friend] = this.probesToOffer[friend] || [];
    this.probesToOffer[friend].push(probeId);
    this.tryToSendProbes(friend);
  }
  protected queueAllFloodProbes(other: string): void {
    this.debugLog.push(`QUEUEING ALL FLOOD PROBES TO ${other}`);
    this.probeStore.getKeys().forEach((probeId) => {
      this.debugLog.push(`QUEUEING PROBE ${probeId} TO ${other}`);
      // setting homeMinted to false but we don't expect it to matter since this probe already exists
      this.queueProbe(other, probeId, false);
    });
  }
  protected queueFloodProbeToAll(probeId: string, homeMinted: boolean): void {
    this.getFriends().forEach(friend => {
      this.queueProbe(friend, probeId, homeMinted);
    });
  }
  protected createFloodProbe(): void {
    this.debugLog.push(`creating flood probe`);
    return this.queueFloodProbeToAll(genRanHex(8), true);
  }
  protected createPinnedFloodProbe(recipient: string): void {
    const probeForNewLink = genRanHex(8);
    this.debugLog.push(`creating pinned flood probe ${probeForNewLink} for ${recipient}`);
    this.queueProbe(recipient, probeForNewLink, true);
  }
  // when this node has sent a `meet` message
  onMeet(other: string): void {
    this.debugLog.push(`I meet ${other} [1/4]`);
    // this is safe to because it will just queue them for the next message round
    this.sendMessage(other, new MeetMessage());
    this.debugLog.push(`I queue ${other} all my flood probes [2/4]`);
    // this is safe to because it will just queue them for the next message round
    this.queueAllFloodProbes(other);
    this.debugLog.push(`and create a new flood probe for other friends than ${other} [3/4]`);
    // NOTE: don't the flood probe creation because it will span multiple message rounds
    this.createFloodProbe();
    this.debugLog.push(`Done onMeet ${other} [4/4]`);
  }
  // when this node has received a `meet` message
  handleMeetMessage(sender: string): void {
    this.debugLog.push(`MEET MESSAGE FROM ${sender}, queueing all flood probes`);
    this.queueAllFloodProbes(sender);
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
    const traceId = genRanHex(8);
    const trace = new Trace(undefined, friend, traceId);
    const probe = this.probeStore.get(probeId);
    probe.addTrace(trace);
    this.debugLog.push(`CREATING TRACE ${traceId} TO ${friend} FOR OUR HOME MINTED PROBE ${probeId}`);
    this.sendMessage(friend, new TraceMessage(probeId, traceId, 'default'));
  }
  handleProbeMessage(sender: string, message: ProbeMessage): void {
    let probe: Probe | undefined = this.probeStore.get(message.getId());
    if (typeof probe === 'undefined') {
      this.debugLog.push(`INCOMING PROBE ${message.getId()} IS NEW TO US, FLOOD IT FORWARD`);
      probe = this.probeStore.ensure(message.getId(), false);
      probe.recordIncoming(sender);
      this.queueFloodProbeToAll(message.getId(), false);
    } else {
      this.debugLog.push(`INCOMING PROBE ${message.getId()} IS KNOWN TO US`);
      if (probe.isVirginFor(sender)) {
        // Record this *after* testing it:
        probe.recordIncoming(sender);
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
  handleTraceMessage(sender: string, message: TraceMessage): void {
    const probe: Probe | undefined = this.probeStore.get(message.getProbeId());
    this.debugLog.push(`TRACE ${message.getTraceId()} FOR PROBE ${message.getProbeId()} COMING TO US FROM SENDER ${sender}`);
    this.debugLog.push(`PROBE ${message.getProbeId()} HAS TRACES: ${probe.getTraces().map(trace => trace.getTraceId()).join(' ')}`);
    this.debugLog.push(`PROBE ${message.getProbeId()} HAS FROM: ${probe.getFrom().join(' ')}`);
    this.debugLog.push(`PROBE ${message.getProbeId()} HAS TO: ${probe.getTo().join(' ')}`);
    if (typeof probe === 'undefined') {
      this.debugLog.push(`UNEXPECTED: PROBE UNKNOWN TO US!`);
      return;
    }
    const traces = probe.getTraces();
    for (let i = 0; i < traces.length; i++) {
      const trace = traces[i];
      if (trace.getTraceId() === message.getTraceId()) {
        if (probe.getFrom().length === 0) {
          this.debugLog.push(`OUR TRACE CAME BACK!`);
          this.loopsFound.push(message.getProbeId() + ':' + message.getTraceId());
          return;
        }
        if (probe.getFrom().length > 1) {
          this.debugLog.push(`UNEXPECTED: PROBE HAS MORE THAN ONE FROM: ${probe.getFrom().join(' ')}!`);
          return;
        }
        this.debugLog.push(`TRACE ${message.getTraceId()} for probe ${message.getProbeId()} ALREADY KNOWN TO US! NOT FORWARDING DUPLICATE MESSAGE`);
        return;
      }
    }
    this.debugLog.push(`FORWARDING TRACE TO ${probe.getFrom()[0]}`);
    const recipient = probe.getFrom()[0];
    this.sendMessage(recipient, new TraceMessage(message.getProbeId(), message.getTraceId(), 'default'));
    const trace = new Trace(sender, this.getName(), message.getTraceId());
    probe.addTrace(trace);
  }
  getLoops(): string[] {
    return this.loopsFound;
  }
  getLog(): string[] {
    return this.debugLog;
  }
}
