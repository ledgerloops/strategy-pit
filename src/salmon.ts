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
    other.receiveMessage(this, `meet`);
  }
  getName(): string {
    return this.name;
  }
  getFriends(): string[] {
    return Object.keys(this.friends);
  }
  receiveMessage(from: Salmon, message: string): void {
    console.log(`${this.name} receives message from ${from.getName()}`, message);
    if (message === `meet`) {
      this.addFriend(from);
    }
  }
}
