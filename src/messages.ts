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

export class LoopMessage extends Message {
  private loopId: string;
  private probeId: string;
  constructor(probeId: string, loopId?: string) {
      super();
      this.probeId = probeId;
      this.loopId = loopId  || 'default';
  }
  getMessageType(): string {
    return 'loop';
  }
  getProbeId(): string {
    return this.probeId;
  }
  getLoopId(): string {
    return this.loopId;
  }
  toString(): string {
    return `loop ${this.probeId} ${this.loopId}`;
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