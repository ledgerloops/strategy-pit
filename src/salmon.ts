export class Salmon {
  private name: string;
  private friends: {
   [name: string]: Salmon
  }  = {};
  constructor(name: string) {
    this.name = name;
  }
  meet(other: Salmon): void {
    const otherName = other.getName();
    console.log(`${this.name} meets ${otherName}`);
    if (typeof this.friends[other.name] !== 'undefined') {
      throw new Error(`${this.name} is already friends with ${otherName}`);
    }    
    this.friends[otherName] = other;
  }
  getName(): string {
    return this.name;
  }
  getFriends(): string[] {
    return Object.keys(this.friends);
  }
}
