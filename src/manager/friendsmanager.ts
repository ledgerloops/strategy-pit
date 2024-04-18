export class FriendsManager {
  protected name: string;
  protected friends: {
    [name: string]: boolean
  } = {};
  constructor(name: string) {
    this.name = name;
  }
  addFriend(otherName: string): void {
    // console.log(`${this.name} meets ${otherName}`);
    if (typeof this.friends[otherName] !== 'undefined') {
      // console.log(this.debugLog);
      throw new Error(`${this.name} is already friends with ${otherName}`);
    }
    this.friends[otherName] = true;
  }
  getFriends(): string[] {
    return Object.keys(this.friends);
  }

}
