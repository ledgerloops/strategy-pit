import { Salmon } from "./salmon.js";

export abstract class Message {
  private sender: Salmon;
  constructor(sender: Salmon) {
    this.sender = sender;
  }
  getSender(): Salmon {
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
  constructor(sender: Salmon, id: string) {
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
