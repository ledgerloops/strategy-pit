import { Message, Meet } from "./messages.js";

export class Salmon {
  private name: string;
  private friends: {
   [name: string]: Salmon
  }  = {};
  constructor(name: string) {
    this.name = name;
  }
  private addFriend(other: Salmon): void {
    const otherName = other.getName();
    console.log(`${this.name} meets ${otherName}`);
    if (typeof this.friends[other.name] !== 'undefined') {
      throw new Error(`${this.name} is already friends with ${otherName}`);
    }    
    this.friends[otherName] = other;
  }
  meet(other: Salmon): void {
    this.addFriend(other);
    other.receiveMessage(new Meet(this));
  }
  getName(): string {
    return this.name;
  }
  getFriends(): string[] {
    return Object.keys(this.friends);
  }
  receiveMessage(message: Message): void {
    console.log(`${this.name} receives message from ${message.getSender().getName()}`, message);
    if (message.getMessageType() === `meet`) {
      this.addFriend(message.getSender());
    }
  }
}
