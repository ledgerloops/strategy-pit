import { Probe as ProbeMessage, Loop as LoopMessage, Meet, HaveProbes, Message, OkayToSendProbes } from "../src/messages.js";
import { BasicMessageForwarder, HandRaisingStatus, Node } from "../src/node.js";
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

export class Butterfly extends Node {
  protected probeStore: ButterflyProbeStore = new ButterflyProbeStore();
  private loopsFound: string[] = [];
  // private probesToOffer: {
  //   [friend: string] : string[]
  // } = {};
  constructor(name: string, messageForwarder?: BasicMessageForwarder) {
    super(name, messageForwarder);
  }

  // Methods copied from Polite START
  private raiseHand(to: string): void {
    this.friends[to].handRaisingStatus = HandRaisingStatus.Waiting;
    this.debugLog.push(`${this.name} raises hand to ${to}`);
    this.messageForwarder.forwardMessage(this, this.friends[to].node, new HaveProbes());
  }
  private handleRaiseHand(from: string): void {
    // console.log(this.name, 'receives raised hand from', from);
    this.debugLog.push(`${this.name} receives raised hand from ${from}`);
    this.friends[from].handRaisingStatus = HandRaisingStatus.Listening;
    this.debugLog.push(`${this.name} sends okay-to-send-probes message to ${from}`);
    super.sendMessage(from, new OkayToSendProbes());
  }
  private handleOverToYouMessage(from: string): void {
    // console.log(this.name, 'receives okay-to-send-probes from', from);
    this.debugLog.push(`${this.name} receives okay-to-send-probes from ${from}`);
    this.friends[from].handRaisingStatus = HandRaisingStatus.Talking;
    if (typeof this.friends[from].promises !== 'undefined') {
      this.friends[from].promises.forEach(promise => {
        promise.resolve();
      });
      delete this.friends[from].promises;
    }
  }
  protected async semaphore(to: string): Promise<void> {
    if(this.friends[to].handRaisingStatus === HandRaisingStatus.Talking) {
      this.debugLog.push(`${this.name} is talking to ${to}`);
      return;
    }
    this.debugLog.push(`${this.name} is waiting to talk to ${to}`);

    this.debugLog.push(`${this.name} waits for semaphore to talk to ${to}`);
    const ret: Promise<void> = new Promise((resolve, reject) => {
      if (typeof this.friends[to].promises === 'undefined') {
        this.friends[to].promises = [];
      }
      this.friends[to].promises.push({ resolve, reject });
    });
    if(this.friends[to].handRaisingStatus === HandRaisingStatus.Listening) {
      // console.log(this.name, 'raising hand to', to);
      this.raiseHand(to);
    }
    return ret;
  }
  protected async sendMessage(to: string, message: Message): Promise<void> {
    this.debugLog.push(`sendMessage ${this.name} to ${to}, semaphore wait START`);
    await this.semaphore(to);
    this.debugLog.push(`sendMessage ${this.name} to ${to}, semaphore wait END`);
    this.debugLog.push(`${this.name} is talking and sends ${message.getMessageType()} message to ${to}`);
    this.messageForwarder.forwardMessage(this, this.friends[to].node, message);
  }
  async receiveMessage(sender: Node, message: Message): Promise<void> {
    this.debugLog.push(`[Polite#receiveMessage] ${this.name} receives message from ${sender.getName()}`);
    // console.log(`${this.name} receives message from ${sender}`, message);
    if (message.getMessageType() === `have-probes`) {
      this.messageForwarder.logMessageReceived(sender.getName(), this.getName(), message);
      this.handleRaiseHand(sender.getName());
    } else if (message.getMessageType() === `okay-to-send-probes`) {
      this.handleOverToYouMessage(sender.getName());
    } else {
      this.debugLog.push(`${this.name} receives payload message from ${sender.getName()}`);
      super.receiveMessage(sender, message);
    }
  }
  // Methods copied from Polite END

  protected sendProbe(to: string, message: ProbeMessage): void {
    const probe = this.probeStore.get((message as ProbeMessage).getId());
    probe.recordOutgoing(to);
    this.sendMessage(to, message);
  }
  protected async offerProbe(friend: string, probeId: string, homeMinted: boolean): Promise<void> {
    const probe = this.probeStore.ensure(probeId, homeMinted);
    this.debugLog.push(`OFFERING PROBE ${probeId} TO ${friend} [1/4]`);
    await this.semaphore(friend);
    this.debugLog.push(`OFFERING PROBE ${probeId} TO ${friend} [2/4]`);
    if (probe.isVirginFor(friend)) {
      this.debugLog.push(`OFFERING PROBE ${probeId} TO ${friend} [3/4]`);
      this.sendProbe(friend, new ProbeMessage(probeId));
    }
    this.debugLog.push(`OFFERING PROBE ${probeId} TO ${friend} [4/4]`);
  }
  protected async offerAllFloodProbes(other: string): Promise<void> {
    this.debugLog.push(`OFFERING ALL FLOOD PROBES TO ${other}`);
    const promises = this.probeStore.getKeys().map((probeId) => {
      this.debugLog.push(`OFFERING PROBE ${probeId} TO ${other}`);
      // setting homeMinted to false but we don't expect it to matter since this probe already exists
      return this.offerProbe(other, probeId, false);
    });
    this.debugLog.push(`AWAITING ALL PROBES TO BE OFFERED TO ${other}`);
    await Promise.all(promises);
  }
  protected async offerFloodProbeToAll(probeId: string, homeMinted: boolean): Promise<void> {
    const promises = this.getFriends().map(friend => {
      return this.offerProbe(friend, probeId, homeMinted);
    });
    this.debugLog.push(`AWAITING PROBE ${probeId} TO BE OFFERED TO ALL FRIENDS`);
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
    this.debugLog.push(`I meet ${other} [1/4]`);
    // this is safe to await because it will just queue them for the next message round
    await this.sendMessage(other, new Meet());
    this.debugLog.push(`I offer ${other} all my flood probes [2/4]`);
    // this is safe to await because it will just queue them for the next message round
    await this.offerAllFloodProbes(other);
    this.debugLog.push(`and create a new flood probe for other friends than ${other} [3/4]`);
    // NOTE: don't await the flood probe creation because it will span multiple message rounds
    this.createFloodProbe();
    this.debugLog.push(`Done onMeet ${other} [4/4]`);
  }
  // when this node has received a `meet` message
  async handleMeetMessage(sender: string): Promise<void> {
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
  async handleProbeMessage(sender: string, message: ProbeMessage): Promise<void> {
    let probe: Probe | undefined = this.probeStore.get(message.getId());
    if (typeof probe === 'undefined') {
      this.debugLog.push(`INCOMING PROBE ${message.getId()} IS NEW TO US, FLOOD IT FORWARD`);
      probe = this.probeStore.ensure(message.getId(), false);
      probe.recordIncoming(sender);
      await this.offerFloodProbeToAll(message.getId(), false);
    } else {
      this.debugLog.push(`INCOMING PROBE ${message.getId()} IS KNOWN TO US`);
      if (probe.isVirginFor(sender)) {
        this.debugLog.push(`PROBE ${message.getId()} ALREADY KNOWN TO US, VIRGIN FOR ${sender}!`);
        if (probe.isHomeMinted()) {
          await this.createLoopTrace(message.getId(), sender);
        } else {
          await this.createPinnedFloodProbe(sender);
        }
      } else {
        this.debugLog.push(`PROBE ${message.getId()} ALREADY KNOWN TO US, BUT NOT VIRGIN FOR ${sender}!`);
      }
    }
  }
  async handleLoopMessage(sender: string, message: LoopMessage): Promise<void> {
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
