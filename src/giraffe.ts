import { ProbeMessage as ProbeMessage, TraceMessage as TraceMessage, MeetMessage } from "./messages.js";
import { BasicMessageForwarder, Node } from "./node.js";
import { ProbesManager } from "./manager/probesmanager.js";

export class Giraffe extends Node {
  protected probesManager: ProbesManager;
  constructor(name: string, messageForwarder?: BasicMessageForwarder) {
    super(name, messageForwarder);
    this.probesManager = new ProbesManager(name);
    this.probesManager.on('message', (sender: string, message: ProbeMessage | TraceMessage) => {
      this.sendMessageToFriend(sender, message);
    });
    this.probesManager.on('debug', (message: string) => {
      this.debugLog.push(message);
    });
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
