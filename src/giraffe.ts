import EventEmitter from "node:events";
import { NetworkNode } from "./simulator/networksimulator.js";
import { getMessageType } from "./messages.js";
import { ProbesManager } from "./manager/probesmanager.js";
import { FriendsManager } from "./manager/friendsmanager.js";
import { TracesManager } from "./manager/tracesmanager.js";

export class Giraffe extends EventEmitter implements NetworkNode {
  protected friendsManager: FriendsManager;
  protected probesManager: ProbesManager;
  protected tracesManager: TracesManager;
  protected debugLog: string[] = [];
  protected name: string;

  constructor(name: string) {
    super();
    this.name = name;
    this.friendsManager = new FriendsManager(name);
    this.probesManager = this.connectProbesManager();
    this.tracesManager = this.connectTracesManager(this.probesManager);
  }
  protected connectProbesManager(): ProbesManager {
    const probesManager = new ProbesManager(this.name);
    probesManager.on('message', (to: string, message: string) => {
      this.emit('message', to, message);
    });
    probesManager.on('debug', (message: string) => {
      this.debugLog.push(message);
    });
    return probesManager;
  }
  protected connectTracesManager(probesManager: ProbesManager): TracesManager {
    const tracesManager = new TracesManager();
    probesManager.on('probe-loopback', (probeId: string, situation: string, from: string[], to: string[]): void => {
      tracesManager.handleProbeLoopback(probeId, situation, from, to);
    });
    tracesManager.on('debug', (message: string) => {
      this.debugLog.push(message);
    });
    return tracesManager;
  }
  process(sender: string, message: string): void {
    this.debugLog.push(`[Node#receiveMessage] ${this.name} receives message from ${sender}`);
    // console.log(`${this.name} receives message from ${sender}`, message);
    switch(getMessageType(message)) {
      case `meet`: return this.handleMeetMessage(sender);
      case `probe`: return this.probesManager.handleProbeMessage(sender, message);
      case `trace`: return this.probesManager.handleTraceMessage(sender, message);
      // case `loop`: return this.probesManager.handleTraceMessage(sender, message);
      case `have-probes`: return this.probesManager.handleHaveProbesMessage(sender);
      case `okay-to-send-probes`: return this.probesManager.handleOkayToSendProbesMessage(sender);
    }
  }
  meet(other: string): void {
    this.friendsManager.addFriend(other);
    this.debugLog.push(`I meet ${other} [1/4]`);
    // this is safe to because it will just queue them for the next message round
    this.emit('message', other, 'meet');
    this.debugLog.push(`I queue ${other} all my flood probes [2/4]`);
    this.probesManager.addFriend(other, true);
    this.debugLog.push(`Done onMeet ${other} [4/4]`);
  }

  // when this node has received a `meet` message
  handleMeetMessage(sender: string): void {
    this.friendsManager.addFriend(sender);
    this.debugLog.push(`MEET MESSAGE FROM ${sender}, queueing all flood probes`);
    this.probesManager.addFriend(sender, false);
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
    return this.probesManager.getProbes();
  }
  getLoops(): string[] {
    return this.probesManager.getLoops();
  }
  getName(): string {
    return this.name;
  }
  getDebugLog(): string[] {
    return this.debugLog;
  }
  getFriends(): string[] {
    return Object.keys(this.friendsManager.getFriends());
  }
}
