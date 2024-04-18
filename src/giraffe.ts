import { ProbeMessage as ProbeMessage, TraceMessage as TraceMessage, MeetMessage, Message, getMessageType } from "./messages.js";
import { HandRaisingStatus } from "./node.js";
import { ProbesManager } from "./manager/probesmanager.js";
import { NetworkNode } from "./simulator/networksimulator.js";
import EventEmitter from "node:events";

export class Giraffe extends EventEmitter implements NetworkNode {
  protected probesManager: ProbesManager;
  protected debugLog: string[] = [];
  protected name: string;
  protected friends: {
    [name: string]: {
      handRaisingStatus: HandRaisingStatus,
    }
  }  = {};

  constructor(name: string) {
    super();
    this.name = name;
    this.probesManager = new ProbesManager(name);
    this.probesManager.on('message', (to: string, message: ProbeMessage | TraceMessage) => {
      this.emit('message', to, message);
    });
    this.probesManager.on('debug', (message: string) => {
      this.debugLog.push(message);
    });
  }
  process(sender: string, message: string): void {
    this.debugLog.push(`[Node#receiveMessage] ${this.name} receives message from ${sender}`);
    // console.log(`${this.name} receives message from ${sender}`, message);
    if (getMessageType(message) === `meet`) {
      this.addFriend(sender, HandRaisingStatus.Listening);
      return this.handleMeetMessage(sender);
    } else if (getMessageType(message) === `probe`) {
      return this.handleProbeMessage(sender, message.toString());
    } else if (getMessageType(message) === `loop`) {
      return this.handleTraceMessage(sender, message.toString());
    } else if (getMessageType(message) === `have-probes`) {
      this.handleHaveProbesMessage(sender);
    } else if (getMessageType(message) === `okay-to-send-probes`) {
      this.handleOkayToSendProbesMessage(sender);

    }
  }
  getName(): string {
      return this.name;
  }
  getDebugLog(): string[] {
    return this.debugLog;
  }
  protected addFriend(otherName: string, handRaisingStatus: HandRaisingStatus): void {
    // console.log(`${this.name} meets ${otherName}`);
    if (typeof this.friends[otherName] !== 'undefined') {
      throw new Error(`${this.name} is already friends with ${otherName}`);
    }
    this.friends[otherName] = { handRaisingStatus };
  }
  getFriends(): string[] {
    return Object.keys(this.friends);
  }

  meet(otherName: string): void {
    this.addFriend(otherName, HandRaisingStatus.Talking);
    this.onMeet(otherName);
  }

  protected sendMessageToFriend(friend: string, message: Message): void {
    this.emit('message', this.name, friend, message);
  }

  protected sendMessage(to: string, message: Message): void {
    this.emit('message', this.name, to, message);
  }

  // when this node has sent a `meet` message
  onMeet(other: string): void {
    this.debugLog.push(`I meet ${other} [1/4]`);
    // this is safe to because it will just queue them for the next message round
    this.sendMessage(other, new MeetMessage());
    this.debugLog.push(`I queue ${other} all my flood probes [2/4]`);
    this.probesManager.addFriend(other, true);
    this.debugLog.push(`Done onMeet ${other} [4/4]`);
  }
  // when this node has received a `meet` message
  handleMeetMessage(sender: string): void {
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
  handleProbeMessage(sender: string, message: string): void {
    this.probesManager.handleProbeMessage(sender, message);
  }
  handleTraceMessage(sender: string, message: string): void {
    this.probesManager.handleTraceMessage(sender, message);
  }
  
  protected handleHaveProbesMessage(from: string): void {
    return this.probesManager.handleHaveProbesMessage(from);
  }
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  protected handleOkayToSendProbesMessage(from: string): void {
    return this.probesManager.handleOkayToSendProbesMessage(from);
  }


  getLoops(): string[] {
    return this.probesManager.getLoops();
  }
  getLog(): string[] {
    return this.debugLog;
  }
}
