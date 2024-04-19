import { Message } from "./messages.js";
export { genRanHex } from "./genRanHex.js";

// returns a new object with the values at each key mapped using mapFn(value)
export function objectMap(object, mapFn): object {
  return Object.keys(object).reduce(function(result, key) {
    result[key] = mapFn(object[key])
    return result
  }, {})
}

export class Entry {
  sender: string;
  receiver: string;
  message: Message | string;
  event: string;
  constructor(sender: string, receiver: string, message: Message | string, event: string) {
    this.sender = sender;
    this.receiver = receiver;
    this.message = message;
    this.event = event;
  }
  describePath(): string {
    if (this.event === 'sent') {
      return `[${this.sender}]->[${this.receiver}]`;
    } else {
      return `[${this.sender}]>-[${this.receiver}]`;
    }
  }
}
function createPreamble(): string {
  return `@startuml messages\n`;
}
function createLine(entry: Entry): string {
  if (entry.sender === '---') {
    return '';
  }
  if (entry.event !== 'sent') {
    return '';
  }
  if ((entry.message === 'have-probes') || (entry.message === 'okay-to-send-probes')) {
    return '';
  }
  const color = 'green';
  return `${entry.sender} -[#${color}]-> ${entry.receiver}: ${entry.message}\n`;
}
function createEpilogue(): string {
  return '@enduml';
}
export function createPlantUml(log: Entry[]): string {
  return createPreamble() + log.map(line => createLine(line)).join('') + createEpilogue();
}