import EventEmitter from "node:events";
import { NetworkNode } from "./simulator/networksimulator.js";
import { getMessageType } from "./messages.js";
import { ProbesEngine } from "./engine/probesengine.js";
import { FriendsEngine } from "./engine/friendsengine.js";
import { TracesEngine } from "./engine/tracesengine.js";
import { LoopsEngine } from "./engine/loopsengine.js";

export class Giraffe extends EventEmitter implements NetworkNode {
  protected friendsEngine: FriendsEngine;
  protected probesEngine: ProbesEngine;
  protected tracesEngine: TracesEngine;
  protected loopsEngine: LoopsEngine;
  protected debugLog: string[] = [];
  protected name: string;

  constructor(name: string) {
    super();
    this.name = name;
    this.friendsEngine = new FriendsEngine(name);
    this.probesEngine = this.connectProbesEngine();
    this.tracesEngine = this.connectTracesEngine(this.probesEngine);
    this.loopsEngine = this.connectLoopsEngine(this.tracesEngine);
  }
  protected connectProbesEngine(): ProbesEngine {
    const probesengine = new ProbesEngine(this.name);
    probesengine.on('message', (to: string, message: string) => {
      this.emit('message', to, message);
    });
    probesengine.on('debug', (message: string) => {
      this.debugLog.push(message);
    });
    return probesengine;
  }
  protected connectTracesEngine(probesengine: ProbesEngine): TracesEngine {
    const tracesengine = new TracesEngine();
    probesengine.on('probe-loopback', (probeId: string): void => {
      tracesengine.handleProbeLoopback(probeId);
    });
    tracesengine.on('debug', (message: string) => {
      this.debugLog.push(message);
    });
    tracesengine.on('lookup-probe', (probeId: string, callback: (probeFrom: string[], probeTo: string[]) => void) => {
      this.debugLog.push(`[Node#lookup-probe] ${this.name} is looking up probe ${probeId}`);
      const probe = probesengine.get(probeId);
      callback(probe.getFrom(), probe.getTo());
    });
    tracesengine.on('message', (to: string, message: string) => {
      this.debugLog.push(`[Node#sendTraceMessage] ${this.name} sends trace message to ${to}: ${message}`);
      this.emit('message', to, message);
    });
    return tracesengine;
  }
  protected connectLoopsEngine(traceEngine: TracesEngine): LoopsEngine {
    const loopsEngine = new LoopsEngine();
    traceEngine.on('loop-found', (probeId: string, traceId: string) => {
      loopsEngine.handleLoopFound(probeId, traceId);
    });
    loopsEngine.on('debug', (message: string) => {
      this.debugLog.push(message);
    });
    return loopsEngine;
  }
  process(sender: string, message: string): void {
    this.debugLog.push(`[Node#receiveMessage] ${this.name} receives message from ${sender}`);
    // console.log(`${this.name} receives message from ${sender}`, message);
    switch(getMessageType(message)) {
      case `meet`: return this.handleMeetMessage(sender);
      case `probe`: return this.probesEngine.handleProbeMessage(sender, message);
      case `trace`: return this.tracesEngine.handleTraceMessage(sender, message);
      // case `loop`: return this.probesengine.handleTraceMessage(sender, message);
      case `have-probes`: return this.probesEngine.handleHaveProbesMessage(sender);
      case `okay-to-send-probes`: return this.probesEngine.handleOkayToSendProbesMessage(sender);
    }
  }
  meet(other: string, createProbe: boolean = true): void {
    this.friendsEngine.addFriend(other);
    this.debugLog.push(`I meet ${other} [1/4]`);
    // this is safe to because it will just queue them for the next message round
    this.emit('message', other, 'meet');
    this.debugLog.push(`I queue ${other} all my flood probes [2/4]`);
    this.probesEngine.addFriend(other, true, createProbe);
    this.debugLog.push(`Done onMeet ${other} [4/4]`);
  }

  // when this node has received a `meet` message
  handleMeetMessage(sender: string): void {
    this.friendsEngine.addFriend(sender);
    this.debugLog.push(`MEET MESSAGE FROM ${sender}, queueing all flood probes`);
    this.probesEngine.addFriend(sender, false, false);
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
