import { Node } from "./node.js";

export abstract class Message {
  private sender: Node;
  constructor(sender: Node) {
    this.sender = sender;
  }
  getSender(): Node {
    return this.sender;
  }
  abstract getMessageType(): string;
  abstract toString(): string; 
}

export class Meet extends Message {
  getMessageType(): string {
    return 'meet';
  }
  toString(): string {
    return 'meet';
  }
}

export class Probe extends Message {
  private id: string;
  constructor(sender: Node, id: string) {
      super(sender);
      this.id = id;
  }
  getMessageType(): string {
    return 'probe';
  }
  getId(): string {
    return this.id;
  }
  toString(): string {
    return `probe ${this.id}`;
  }
}

export class Loop extends Message {
  private loopId: string;
  private probeId: string;
  constructor(sender: Node, probeId: string, loopId?: string) {
      super(sender);
      this.probeId = probeId;
      this.loopId = loopId;
  }
  getMessageType(): string {
    return 'loop';
  }
  getProbeId(): string {
    return this.probeId;
  }
  getLoopId(): string {
    return this.loopId;
  }
  toString(): string {
    return `loop ${this.probeId} ${this.loopId}`;
  }

}
