export interface TimedEvent { start:number; end:number; pitches:number[]; staff:number; velocity?:number; id?:string }

export function clipEvents(events:TimedEvent[],position:number,until:number):TimedEvent[]{
  return events.filter(e=>e.end>position&&e.start<until).map(e=>({...e,start:Math.max(position,e.start),end:Math.min(until,e.end)})).filter(e=>e.end>e.start).sort((a,b)=>a.start-b.start||a.staff-b.staff);
}

export function scheduledTime(eventStart:number,offset:number,anchor:number,now:number){
  return Math.max(now+.005,anchor+eventStart-offset);
}
