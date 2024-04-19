import EventEmitter from "node:events";
import { NetworkNode } from "./simulator/networksimulator.js";
import { getMessageType } from "./messages.js";
import { ProbesEngine } from "./engine/probesengine.js";
import { FriendsEngine } from "./engine/friendsengine.js";
import { TracesEngine } from "./engine/tracesengine.js";

export class Giraffe extends EventEmitter implements NetworkNode {
  protected friendsengine: FriendsEngine;
  protected probesengine: ProbesEngine;
  protected tracesengine: TracesEngine;
  protected debugLog: string[] = [];
  protected name: string;

  constructor(name: string) {
    super();
    this.name = name;
    this.friendsengine = new FriendsEngine(name);
    this.probesengine = this.connectProbesEngine();
    this.tracesengine = this.connectTracesEngine(this.probesengine);
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
    tracesengine.on('lookup-probe', (probeId: string, callback: (probeFrom: string[]) => void) => {
      this.debugLog.push(`[Node#lookup-probe] ${this.name} is looking up probe ${probeId}`);
      callback(probesengine.get(probeId).getFrom());
    });
    tracesengine.on('message', (to: string, message: string) => {
      this.debugLog.push(`[Node#sendTraceMessage] ${this.name} sends trace message to ${to}: ${message}`);
      this.emit('message', to, message);
    });
    return tracesengine;
  }
  process(sender: string, message: string): void {
    this.debugLog.push(`[Node#receiveMessage] ${this.name} receives message from ${sender}`);
    // console.log(`${this.name} receives message from ${sender}`, message);
    switch(getMessageType(message)) {
      case `meet`: return this.handleMeetMessage(sender);
      case `probe`: return this.probesengine.handleProbeMessage(sender, message);
      case `trace`: return this.tracesengine.handleTraceMessage(sender, message);
      // case `loop`: return this.probesengine.handleTraceMessage(sender, message);
      case `have-probes`: return this.probesengine.handleHaveProbesMessage(sender);
      case `okay-to-send-probes`: return this.probesengine.handleOkayToSendProbesMessage(sender);
    }
  }
  meet(other: string): void {
    this.friendsengine.addFriend(other);
    this.debugLog.push(`I meet ${other} [1/4]`);
    // this is safe to because it will just queue them for the next message round
    this.emit('message', other, 'meet');
    this.debugLog.push(`I queue ${other} all my flood probes [2/4]`);
    this.probesengine.addFriend(other, true);
    this.debugLog.push(`Done onMeet ${other} [4/4]`);
  }

  // when this node has received a `meet` message
  handleMeetMessage(sender: string): void {
    this.friendsengine.addFriend(sender);
    this.debugLog.push(`MEET MESSAGE FROM ${sender}, queueing all flood probes`);
    this.probesengine.addFriend(sender, false);
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
    return this.probesengine.getProbes();
  }
  getLoops(): string[] {
    return this.probesengine.getLoops();
  }
  getName(): string {
    return this.name;
  }
  getDebugLog(): string[] {
    return this.debugLog;
  }
  getFriends(): string[] {
    return Object.keys(this.friendsengine.getFriends());
  }
}
