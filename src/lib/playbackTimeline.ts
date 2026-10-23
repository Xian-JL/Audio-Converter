export interface TimedEvent { start:number; end:number; pitches:number[]; staff:number; velocity?:number; id?:string }

export function clipEvents(events:TimedEvent[],position:number,until:number):TimedEvent[]{
  return events.filter(e=>e.end>position&&e.start<until).map(e=>({...e,start:Math.max(position,e.start),end:Math.min(until,e.end)})).filter(e=>e.end>e.start).sort((a,b)=>a.start-b.start||a.staff-b.staff);
}

export function scheduledTime(eventStart:number,offset:number,anchor:number,now:number){
  return Math.max(now+.005,anchor+eventStart-offset);
}

/** Relative clock events for one iteration; carried notes restart at the boundary. */
export function cycleEvents(events:TimedEvent[],start:number,end:number,clockOffset:number){
  return clipEvents(events,start,end).map(e=>({...e,start:e.start-start+clockOffset,end:e.end-start+clockOffset}));
}
export function loopPosition(elapsed:number,offset:number,end:number,loop:{start:number;end:number}|null){
  const at=offset+Math.max(0,elapsed);
  return loop&&at>=end?loop.start+(at-end)%(loop.end-loop.start):Math.min(at,end);
}
