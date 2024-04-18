import EventEmitter from "node:events";
import { Message, getMessageType } from "../messages.js";
import { Node } from "../node.js";
import { Entry, createPlantUml } from "../util.js";

export abstract class NetworkNode extends EventEmitter {
  abstract process(from: string, message: string);
}
export class NetworkSimulator {
  protected nodes: { [name: string]: NetworkNode } = {};
  addNode(name: string, node: NetworkNode): void {
    this.nodes[name] = node;
  }
}

export class LoggingNetworkSimulator extends NetworkSimulator {
  private log: Entry[] = [];
  logMessageSent(sender: string, receiver: string, message: string): void {
    this.log.push(new Entry(sender, receiver, message, 'sent'));
  }
  logMessageReceived(sender: string, receiver: string, message: Message): void {
    this.log.push(new Entry(sender, receiver, message, 'received'));
  }
  forwardMessage(sender: Node, receiver: Node, message: Message): void {
    this.logMessageSent(sender.getName(), receiver.getName(), message.toString());
    receiver.receiveMessage(sender, message);
  }
  getLocalLog(name: string): string[] {
    return this.log.filter(entry => {
      if (entry.sender === name) {
        return (entry.event === 'sent');
      }
      if (entry.receiver === name) {
        return (entry.event === 'received');
      }
      // istanbul ignore next
      return false;
    }).map(entry => {
      if (entry.event === 'sent') {
        return `TO[${entry.receiver}] ${entry.message.toString()}`;
      } else {
        return `FROM[${entry.sender}] ${entry.message.toString()}`;
      }
    });
  }
  getFullLog(includeEachMessageTwice: boolean = false): string[] {
    const filtered = (includeEachMessageTwice) ? this.log : this.log.filter(entry => entry.event === 'sent');
    return filtered.map(entry => `${entry.describePath()} ${entry.message.toString()}`);
  }
  getProbeLogs(): {
    [text: string]: string[]
  } {
    const probeLogs: {
      [text: string]: string[]
    } = {};
    // console.log(this.log);
    this.log.filter(entry => (getMessageType(entry.message) === 'probe')).map(entry => {
      if (typeof probeLogs[entry.message.toString()] === 'undefined') {
        probeLogs[entry.message.toString()] = [];
      }
      probeLogs[entry.message.toString()].push(entry.describePath());
    });
    return probeLogs;
  }
  getPlantUml(): string {
    return createPlantUml(this.log);
  }
}

export class BasicMessageSimulator extends LoggingNetworkSimulator {
  addNode(name: string, node: NetworkNode): void {
    super.addNode(name, node);
    node.on('message', (to: string, message: string) => {
      if (typeof this.nodes[to] !== 'undefined') {
        this.nodes[to].process(name, message);
      }
    });
  }
}
