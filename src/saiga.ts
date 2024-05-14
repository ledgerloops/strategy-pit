import EventEmitter from "node:events";
import { NetworkNode } from "./simulator/networksimulator.js";
import { getMessageType } from "./messages.js";
import { ProbesEngine } from "./engine/probesengine.js";
import { FriendsEngine } from "./engine/friendsengine.js";
import { TracesEngine } from "./engine/tracesengine.js";
import { SaigaLoopsEngine } from "./engine/loopsengine.js";

export class Saiga extends EventEmitter implements NetworkNode {
  protected friendsEngine: FriendsEngine;
  protected probesEngine: ProbesEngine;
  protected tracesEngine: TracesEngine;
  protected loopsEngine: SaigaLoopsEngine;
  protected debugLog: string[] = [];
  protected name: string;

  constructor(name: string) {
    super();
    this.name = name;
    this.friendsEngine = new FriendsEngine(name);
    this.probesEngine = this.connectProbesEngine();
    this.tracesEngine = this.connectTracesEngine(this.probesEngine);
    this.loopsEngine = this.connectLoopsEngine(this.tracesEngine);
    this.loopsEngine.setProfit(0.01);
  }
  protected connectProbesEngine(): ProbesEngine {
    const probesengine = new ProbesEngine(this.name);
    probesengine.on('message', (to: string, message: string) => {
      this.emit('message', to, message);
    });
    // probesengine.on('debug', (message: string) => {
    //   this.debugLog.push(message);
    // });
    return probesengine;
  }
  protected connectTracesEngine(probesengine: ProbesEngine): TracesEngine {
    const tracesEngine = new TracesEngine();
    probesengine.on('probe-loopback', (probeId: string): void => {
      tracesEngine.handleProbeLoopback(probeId);
    });
    // tracesengine.on('debug', (message: string) => {
    //   this.debugLog.push(message);
    // });
    tracesEngine.on('lookup-probe', (probeId: string, callback: (probeFrom: string[], probeTo: string[]) => void) => {
      this.debugLog.push(`[Node#lookup-probe] ${this.name} is looking up probe ${probeId}`);
      const probe = probesengine.get(probeId);
      if (typeof probe === 'undefined') {
        callback([], []);
      } else {
        callback(probe.getFrom(), probe.getTo());
      }
    });
    tracesEngine.on('debug', (message: string) => {
      this.debugLog.push(message);
    });
    tracesEngine.on('message', (to: string, message: string) => {
      this.debugLog.push(`[traceEngine.on-message] ${this.name} sends trace message to ${to}: ${message}`);
      this.emit('message', to, message);
    });
    return tracesEngine;
  }
  protected connectLoopsEngine(traceEngine: TracesEngine): SaigaLoopsEngine {
    const loopsEngine = new SaigaLoopsEngine();
    traceEngine.on('loop-found', (probeId: string, traceId: string, legId: string, outgoing: string, incoming: string) => {
      loopsEngine.handleLoopFound(probeId, traceId, legId, this.friendsEngine.getFriend(outgoing), this.friendsEngine.getFriend(incoming));
    });
    loopsEngine.on('debug', (message: string) => {
      this.debugLog.push(message);
    });
    loopsEngine.on('message', (to: string, message: string) => {
      this.debugLog.push(`[Node#sendTracMessage] ${this.name} sends loops message to ${to}: ${message}`);
      this.emit('message', to, message);
    });
    return loopsEngine;
  }
  protected handleLoopMessage(from: string, message: string): void {
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    const [messageType, probeId, traceId, legId] = message.split(' ');
    const otherPartyName = this.tracesEngine.getOtherParty(from, probeId, traceId, legId);
    const sender = this.friendsEngine.getFriend(from);
    const otherParty = this.friendsEngine.getFriend(otherPartyName);
    if (typeof sender === 'undefined' || typeof otherParty === 'undefined') {
      this.debugLog.push(`other party not found for ${from} ${message}`);
      return;
    }
    if (messageType === 'propose') {
      this.loopsEngine.handleProposeMessage(from, message, sender, otherParty);
    } else if (messageType === 'commit') {
      this.loopsEngine.handleCommitMessage(from, message, sender, otherParty);
    }
  }
  process(sender: string, message: string): void {
    this.debugLog.push(`[Node#receiveMessage] ${this.name} receives message from ${sender}`);
    // console.log(`${this.name} receives message from ${sender}`, message);
    switch(getMessageType(message)) {
      case `meet`:
        this.friendsEngine.addFriend(sender);
        this.debugLog.push(`MEET MESSAGE FROM ${sender}, queueing all flood probes`);
        return this.probesEngine.addFriend(sender, false, false);
      case `probe`: return this.probesEngine.handleProbeMessage(sender, message);
      case `trace`: return this.tracesEngine.handleTraceMessage(sender, message);
      case `propose`: return this.handleLoopMessage(sender, message);
      case `commit`: return this.handleLoopMessage(sender, message);
      case `have-probes`: return this.probesEngine.handleHaveProbesMessage(sender);
      case `okay-to-send-probes`: return this.probesEngine.handleOkayToSendProbesMessage(sender);
    }
  }
  meet(other: string, createProbe: boolean = true, maxBalance: number = 10.0, exchangeRate: number = 1.0): void {
    const newFriendship = this.friendsEngine.addFriend(other, maxBalance, exchangeRate);
    if (!newFriendship) {
      return;
    }
    this.debugLog.push(`I meet ${other} [1/4]`);
    // this is safe to because it will just queue them for the next message round
    this.emit('message', other, 'meet');
    this.debugLog.push(`I queue ${other} all my flood probes [2/4]`);
    this.probesEngine.addFriend(other, true, createProbe);
    this.debugLog.push(`Done onMeet ${other} [4/4]`);
  }
  // initiateLift(traceId: string) {
  //   this.friendsEngine.
  // }
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
    return this.probesEngine.getProbes();
  }
  getName(): string {
    return this.name;
  }
  getDebugLog(): string[] {
    return this.debugLog;
  }
  getFriends(): string[] {
    return Object.keys(this.friendsEngine.getFriends());
  }
  getLoops(): string[] {
    return this.loopsEngine.getLoops();
  }
}
