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
}

export class Meet extends Message {
  getMessageType(): string {
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
}

export class Loop extends Message {
  private id: string;
  constructor(sender: Node, id: string) {
      super(sender);
      this.id = id;
  }
  getMessageType(): string {
    return 'loop';
  }
  getId(): string {
    return this.id;
  }
}
