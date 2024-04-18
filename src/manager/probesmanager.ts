import { genRanHex } from "../genRanHex.js";
import { HaveProbesMessage, OkayToSendProbesMessage, ProbeMessage, TraceMessage } from "../messages.js";
import { Friend, HandRaisingStatus } from "../node.js";
import { EventEmitter } from 'node:events';

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

export class ProbesManager extends EventEmitter {
  protected name: string;
  private probes: {
    [id: string]: Probe
  } = {};
  private loopsFound: string[] = [];
  protected friends: {
    [name: string]: Friend
   }  = {};
  private probesToOffer: {
    [friend: string] : string[]
  } = {};
  constructor(name: string) {
    super();
    this.name = name;
  }
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

  // Postpone sending of probes until we have received the okay-to-send-probes message
  protected raiseHand(to: string): void {
    this.friends[to].handRaisingStatus = HandRaisingStatus.Waiting;
    this.emit('debug', `${this.name} raises hand to ${to}`);
    this.emit('message', to, new HaveProbesMessage());
  }

  public handleHaveProbesMessage(from: string): void {
    this.friends[from].handRaisingStatus = HandRaisingStatus.Listening;
    this.emit('message', from, new OkayToSendProbesMessage());
  }
  protected flushProbesQueue(friend: string): void {
    if (typeof this.probesToOffer[friend] !== 'undefined') {
      this.probesToOffer[friend].forEach(probeId => {
        const probe = this.get(probeId);
        if (probe.isVirginFor(friend)) {
          this.emit('debug', `QUEUEING PROBE ${probe.getProbeId()} TO ${friend} [3/4]`);
          probe.recordOutgoing(friend);
          const message = new ProbeMessage(probe.getProbeId());
          this.emit('message', friend, message);
        }
      });
      delete this.friends[friend].promises;
    }
  }
  public handleOkayToSendProbesMessage(friend: string): void {
    this.emit('debug', `${this.name} receives okay-to-send-probes from ${friend}`);
    this.friends[friend].handRaisingStatus = HandRaisingStatus.Talking;
    this.flushProbesQueue(friend);
  }
  protected tryToSendProbes(friend: string): void {
    if (this.friends[friend].handRaisingStatus === HandRaisingStatus.Talking) {
      this.emit('debug', `${this.name} is talking to ${friend}`);
      this.flushProbesQueue(friend);
    } else if (this.friends[friend].handRaisingStatus === HandRaisingStatus.Listening) {
      this.emit('debug', `${this.name} starts waiting to talk to ${friend}`);
      this.raiseHand(friend);
    }
  }

  protected queueProbe(friend: string, probeId: string, homeMinted: boolean): void {
    this.ensure(probeId, homeMinted);
    this.probesToOffer[friend] = this.probesToOffer[friend] || [];
    this.probesToOffer[friend].push(probeId);
    this.tryToSendProbes(friend);
  }
  public queueAllFloodProbes(other: string): void {
    this.emit('debug', `QUEUEING ALL FLOOD PROBES TO ${other}`);
    this.getKeys().forEach((probeId) => {
      this.emit('debug', `QUEUEING PROBE ${probeId} TO ${other}`);
      // setting homeMinted to false but we don't expect it to matter since this probe already exists
      this.queueProbe(other, probeId, false);
    });
  }
  protected queueFloodProbeToAll(probeId: string, homeMinted: boolean): void {
    Object.keys(this.friends).forEach(friend => {
      this.queueProbe(friend, probeId, homeMinted);
    });
  }
  protected createFloodProbe(): void {
    this.emit('debug', `creating flood probe`);
    return this.queueFloodProbeToAll(genRanHex(8), true);
  }
  protected createPinnedFloodProbe(recipient: string): void {
    const probeForNewLink = genRanHex(8);
    this.emit('debug', `creating pinned flood probe ${probeForNewLink} for ${recipient}`);
    this.queueProbe(recipient, probeForNewLink, true);
  }
  public addFriend(other: string, weInitiate: boolean): void {
    this.friends[other] = new Friend(null, weInitiate ? HandRaisingStatus.Talking : HandRaisingStatus.Listening);

    this.queueAllFloodProbes(other);
    if (weInitiate) {
      this.emit('debug', `and create a new flood probe for other friends than ${other} [3/4]`);
      this.createFloodProbe();      
    }
  }
  public handleProbeMessage(sender: string, message: ProbeMessage): void {
    let probe: Probe | undefined = this.get(message.getId());
    if (typeof probe === 'undefined') {
      this.emit('debug', `INCOMING PROBE ${message.getId()} IS NEW TO US, FLOOD IT FORWARD`);
      probe = this.ensure(message.getId(), false);
      probe.recordIncoming(sender);
      this.queueFloodProbeToAll(message.getId(), false);
    } else {
      this.emit('debug', `INCOMING PROBE ${message.getId()} IS KNOWN TO US`);
      if (probe.isVirginFor(sender)) {
        // Record this *after* testing it:
        probe.recordIncoming(sender);
        this.emit('debug', `PROBE ${message.getId()} ALREADY KNOWN TO US, VIRGIN FOR ${sender}!`);
        if (probe.isHomeMinted()) {
          this.createTrace(message.getId(), sender);
        } else {
          this.createPinnedFloodProbe(sender);
        }
      } else {
        this.emit('debug', `PROBE ${message.getId()} ALREADY KNOWN TO US, BUT NOT VIRGIN FOR ${sender}!`);
      }
    }
  }
  createTrace(probeId: string, friend: string): void {
    const traceId = genRanHex(8);
    const trace = new Trace(undefined, friend, traceId);
    const probe = this.get(probeId);
    probe.addTrace(trace);
    this.emit('debug', `CREATING TRACE ${traceId} TO ${friend} FOR OUR HOME MINTED PROBE ${probeId}`);
    this.emit('message', friend, new TraceMessage(probeId, traceId, 'default'));
  }  
  handleTraceMessage(sender: string, message: TraceMessage): void {
    const probe: Probe | undefined = this.get(message.getProbeId());
    this.emit('debug', `TRACE ${message.getTraceId()} FOR PROBE ${message.getProbeId()} COMING TO US FROM SENDER ${sender}`);
    this.emit('debug', `PROBE ${message.getProbeId()} HAS TRACES: ${probe.getTraces().map(trace => trace.getTraceId()).join(' ')}`);
    this.emit('debug', `PROBE ${message.getProbeId()} HAS FROM: ${probe.getFrom().join(' ')}`);
    this.emit('debug', `PROBE ${message.getProbeId()} HAS TO: ${probe.getTo().join(' ')}`);
    if (typeof probe === 'undefined') {
      this.emit('debug', `UNEXPECTED: PROBE UNKNOWN TO US!`);
      return;
    }
    const traces = probe.getTraces();
    for (let i = 0; i < traces.length; i++) {
      const trace = traces[i];
      if (trace.getTraceId() === message.getTraceId()) {
        if (probe.getFrom().length === 0) {
          this.emit('debug', `OUR TRACE CAME BACK!`);
          this.loopsFound.push(message.getProbeId() + ':' + message.getTraceId());
          return;
        }
        if (probe.getFrom().length > 1) {
          this.emit('debug', `UNEXPECTED: PROBE HAS MORE THAN ONE FROM: ${probe.getFrom().join(' ')}!`);
          return;
        }
        this.emit('debug', `TRACE ${message.getTraceId()} for probe ${message.getProbeId()} ALREADY KNOWN TO US! NOT FORWARDING DUPLICATE MESSAGE`);
        return;
      }
    }
    this.emit('debug', `FORWARDING TRACE TO ${probe.getFrom()[0]}`);
    const recipient = probe.getFrom()[0];
    this.emit('message', recipient, new TraceMessage(message.getProbeId(), message.getTraceId(), 'default'));
    const trace = new Trace(sender, this.name, message.getTraceId());
    probe.addTrace(trace);  
  }
  getLoops(): string[] {
    return this.loopsFound;
  }
}
  