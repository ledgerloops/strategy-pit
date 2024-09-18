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
  return `@startuml\n`;
}
function createLine(entry: Entry, probeId?: string): string {
  const colors = {
    'probe': 'blue',
    'trace': 'green',
    'announce': 'red',
  };
  if (entry.sender === '---') {
    return '';
  }
  if (entry.event !== 'sent') {
    return '';
  }
  if ((entry.message === 'have-probes') || (entry.message === 'okay-to-send-probes')) {
    return '';
  }
  const parts = entry.message.toString().split(' ');
  if (parts.length < 2) {
    return '';
  }
  if ((typeof probeId === 'string') && (parts[1] !== probeId)) {
    return '';
  }
  // if ((parts[0] !== 'meet') && (parts[1] !== 'genRanHex2')) {
  //   return '';
  // }
  const color = colors[entry.message.toString().split(' ')[0]] || 'black';
  return `(${entry.sender}) -[#${color}]-> (${entry.receiver})\n`;
}
function createEpilogue(): string {
  return '@enduml';
}
export function createPlantUml(log: Entry[], probeId?: string): string {
  return createPreamble() + log.map(line => createLine(line, probeId)).join('') + createEpilogue();
}