export class FriendsEngine {
  protected name: string;
  protected friends: {
    [name: string]: {
      name: string,
      maxBalance: number,
      exchangeRate: number,
    },
  } = {};
  constructor(name: string) {
    this.name = name;
  }
  addFriend(otherName: string, maxBalance: number = 10.0, exchangeRate: number = 1.0): boolean {
    // console.log(`${this.name} meets ${otherName}`);
    if (typeof this.friends[otherName] !== 'undefined') {
      // console.log(this.debugLog);
      return false;
    }
    this.friends[otherName] = {
      name: otherName,
      maxBalance,
      exchangeRate,
    };
    return true;
  }
  getFriend(otherName: string): { name: string, maxBalance: number, exchangeRate: number } | undefined {
    return this.friends[otherName];
  }
  getFriends(): string[] {
    return Object.keys(this.friends);
  }

}
