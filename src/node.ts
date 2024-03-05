import { Message } from "./messages.js";

export abstract class Node {
    protected name: string;
    constructor(name: string) {
      this.name = name;
    }
    getName(): string {
        return this.name;
    }
    abstract meet(other: Node): void;
    abstract receiveMessage(message: Message): void;
}