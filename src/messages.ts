export abstract class Message {
  abstract getMessageType(): string;
  abstract toString(): string;
}

export class MeetMessage extends Message {
  getMessageType(): string {
    return 'meet';
  }
  toString(): string {
    return 'meet';
  }
}

export class HaveProbesMessage extends Message {
  getMessageType(): string {
    return 'have-probes';
  }
  toString(): string {
    return 'have-probes';
  }
}

export class OkayToSendProbesMessage extends Message {
  getMessageType(): string {
    return 'okay-to-send-probes';
  }
  toString(): string {
    return 'okay-to-send-probes';
  }
}

export class ProbeMessage extends Message {
  private id: string;
  constructor(id: string) {
      super();
      this.id = id;
  }
  getMessageType(): string {
    return 'probe';
  }
  getId(): string {
    return this.id;
  }
  toString(): string {
    return `probe ${this.id}`;
  }
}

export class TraceMessage extends Message {
  private probeId: string;
  private traceId: string;
  private legId: string;
  constructor(probeId: string, traceId: string, legId: string) {
      super();
      this.probeId = probeId;
      this.traceId = traceId;
      this.legId = legId
  }
  getMessageType(): string {
    return 'loop';
  }
  getProbeId(): string {
    return this.probeId;
  }
  getTraceId(): string {
    return this.traceId;
  }
  getLegId(): string {
    return this.legId;
  }
  toString(): string {
    return `loop ${this.probeId} ${this.traceId}`;
  }

}

export class PauzeMessage extends Message {
  private pauze: boolean;
  constructor(pauze: boolean) {
      super();
      this.pauze = pauze;
  }
  getMessageType(): string {
    return 'pauze';
  }
  getPauze(): boolean {
    return this.pauze;
  }
  toString(): string {
    return `pauze ${this.pauze}`;
  }
}

export function getMessageType(message: Message | string): string {
  if (typeof message === 'string') {
    const parts = message.split(' ');
    return parts[0];
  }
  return message.getMessageType();
}
