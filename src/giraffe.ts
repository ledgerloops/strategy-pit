import { ProbeMessage as ProbeMessage, TraceMessage as TraceMessage, MeetMessage, Message } from "./messages.js";
import { BasicMessageForwarder, Friend, HandRaisingStatus, Node } from "./node.js";
import { ProbesManager } from "./manager/probesmanager.js";

export class Giraffe {
  protected probesManager: ProbesManager;
  protected debugLog: string[] = [];
  protected messageForwarder: BasicMessageForwarder;
  protected name: string;
  protected friends: {
    [name: string]: Friend
   }  = {};

  constructor(name: string, messageForwarder?: BasicMessageForwarder) {
    this.name = name;
    this.messageForwarder = messageForwarder || new BasicMessageForwarder();
    this.probesManager = new ProbesManager(name);
    this.probesManager.on('message', (sender: string, message: ProbeMessage | TraceMessage) => {
      this.sendMessageToFriend(sender, message);
    });
    this.probesManager.on('debug', (message: string) => {
      this.debugLog.push(message);
    });
  }
  getName(): string {
      return this.name;
  }
  getDebugLog(): string[] {
    return this.debugLog;
  }
  protected addFriend(other: Node, handRaisingStatus: HandRaisingStatus): void {
    const otherName = other.getName();
    // console.log(`${this.name} meets ${otherName}`);
    if (typeof this.friends[other.getName()] !== 'undefined') {
      throw new Error(`${this.name} is already friends with ${otherName}`);
    }
    this.friends[otherName] = new Friend(other, handRaisingStatus);
  }
  getFriends(): string[] {
    return Object.keys(this.friends);
  }

  meet(other: Node): void {
    this.addFriend(other, HandRaisingStatus.Talking);
    this.onMeet(other.getName());
  }

  protected sendMessageToFriend(friend: string, message: Message): void {
    this.messageForwarder.forwardMessage(this as unknown as Node, this.friends[friend].node, message);
  }

  protected sendMessage(to: string, message: Message): void {
    this.messageForwarder.forwardMessage(this as unknown as Node, this.friends[to].node, message);
  }
  receiveMessage(sender: Node, message: Message): void {
    this.debugLog.push(`[Node#receiveMessage] ${this.name} receives message from ${sender.getName()}`);
    this.messageForwarder.logMessageReceived(sender.getName(), this.getName(), message);
    // console.log(`${this.name} receives message from ${sender}`, message);
    if (message.getMessageType() === `meet`) {
      this.addFriend(sender, HandRaisingStatus.Listening);
      return this.handleMeetMessage(sender.getName());
    } else if (message.getMessageType() === `probe`) {
      return this.handleProbeMessage(sender.getName(), message as ProbeMessage);
    } else if (message.getMessageType() === `loop`) {
      return this.handleTraceMessage(sender.getName(), message as TraceMessage);
    } else if (message.getMessageType() === `have-probes`) {
      this.messageForwarder.logMessageReceived(sender.getName(), this.getName(), message);
      this.handleHaveProbesMessage(sender.getName());
    } else if (message.getMessageType() === `okay-to-send-probes`) {
      this.handleOkayToSendProbesMessage(sender.getName());

    }
  }
  getMessageLog(): string[] {
    return this.messageForwarder.getLocalLog(this.name);
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
  handleProbeMessage(sender: string, message: ProbeMessage): void {
    this.probesManager.handleProbeMessage(sender, message);
  }
  handleTraceMessage(sender: string, message: TraceMessage): void {
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
