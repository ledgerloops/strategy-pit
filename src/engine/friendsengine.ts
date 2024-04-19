export class FriendsEngine {
  protected name: string;
  protected friends: {
    [name: string]: boolean
  } = {};
  constructor(name: string) {
    this.name = name;
  }
  addFriend(otherName: string): boolean {
    // console.log(`${this.name} meets ${otherName}`);
    if (typeof this.friends[otherName] !== 'undefined') {
      // console.log(this.debugLog);
      return false;
    }
    this.friends[otherName] = true;
    return true;
  }
  getFriends(): string[] {
    return Object.keys(this.friends);
  }

}
