import { EventEmitter } from 'node:events';

export class GiraffeFriendsEngine extends EventEmitter {
  protected name: string;
  protected friends: {
    [name: string]: {
      name: string,
      maxBalance: number,
      exchangeRate: number,
      nack: boolean
    },
  } = {};
  constructor(name: string) {
    super();
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
      nack: false
    };
    return true;
  }
  getFriend(otherName: string): { name: string, maxBalance: number, exchangeRate: number } | undefined {
    return this.friends[otherName];
  }
  getFriends(): string[] {
    return Object.keys(this.friends);
  }
  public handleNackMessage(sender: string, message: string): void {
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    // const [ _messageType ] = message.split(' ');
    // const probe: Probe | undefined = this.get(probeId);
    this.emit('debug', `nack received from sender "${sender}": "${message}"`);
    if (typeof this.friends[sender] === 'undefined') {
      throw new Error('unexpected: message from sender who is not a friend');
    }
    this.friends[sender].nack = true;
  }

}
export class SaigaFriendsEngine extends GiraffeFriendsEngine {
  constructor(name: string) {
    super(name);
  }
  addFriend(otherName: string, maxBalance: number = 10.0): boolean {
    return super.addFriend(otherName, maxBalance, 1.0);
  }
}
