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

