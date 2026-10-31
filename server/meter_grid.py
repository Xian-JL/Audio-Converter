"""A metrical grid with an optional initial incomplete measure."""
from dataclasses import dataclass
from bisect import bisect_right


def between(points,value,slope):
    """Linear calibration between anchors; use nominal tempo after the last."""
    i=bisect_right([p[0] for p in points],value)-1
    if i<0:return points[0][1]+(value-points[0][0])*slope
    if i==len(points)-1:return points[i][1]+(value-points[i][0])*slope
    x,y=points[i];xx,yy=points[i+1]
    return y+(value-x)/(xx-x)*(yy-y)

@dataclass(frozen=True)
class MeterGrid:
    seconds_per_tick:float
    bar_ticks:int
    phase:float=0.
    pickup_ticks:int=0
    anchors:tuple=()

    def tick(self,seconds):
        if self.anchors:return between(tuple((y,x) for x,y in self.anchors),seconds,1/self.seconds_per_tick)
        if self.pickup_ticks and seconds<self.phase:return seconds/self.phase*self.pickup_ticks
        return self.pickup_ticks+(seconds-self.phase)/self.seconds_per_tick

    def time(self,tick):
        if self.anchors:return between(self.anchors,tick,self.seconds_per_tick)
        if self.pickup_ticks and tick<self.pickup_ticks:return tick/self.pickup_ticks*self.phase
        return self.phase+(tick-self.pickup_ticks)*self.seconds_per_tick

    def snap(self,seconds):
        ticks=self.tick(seconds)
        origin=self.pickup_ticks if seconds>=self.phase else 0
        return origin+round((ticks-origin)/4)*4

    def measures(self,total_ticks):
        left=0
        if self.pickup_ticks:
            yield 0,self.pickup_ticks,True
            left=self.pickup_ticks
        while left<total_ticks:
            yield left,left+self.bar_ticks,False
            left+=self.bar_ticks

def make_grid(bpm,meter,divisions,anchor_time=None):
    numerator,denominator=map(int,meter.split('/'))
    tick=60/bpm/divisions;bar_ticks=numerator*divisions*4//denominator
    phase=0. if anchor_time is None else anchor_time%(bar_ticks*tick)
    if min(phase,bar_ticks*tick-phase)<1e-7:phase=0.
    pickup=max(1,round(phase/tick)) if phase else 0
    return MeterGrid(tick,bar_ticks,phase,pickup)

def score_grid(score):
    base=make_grid(score['bpm'],score['meter'],score['divisions'])
    grid=score.get('grid',{})
    return MeterGrid(base.seconds_per_tick,base.bar_ticks,grid.get('phaseSeconds',0.),grid.get('pickupTicks',0),tuple(tuple(p) for p in grid.get('anchors',[])))


def calibrated_grid(bpm,meter,divisions,points):
    """Points contain validated original seconds and written measure numbers."""
    base=make_grid(bpm,meter,divisions,points[0]['time'])
    pickup=base.pickup_ticks or (base.bar_ticks if points[0]['time']>0 and points[0]['measure']==1 else 0)
    anchors=[(pickup+(p['measure']-1)*base.bar_ticks,p['time']) for p in points]
    if anchors[0][1]==0 and anchors[0][0]!=0:
        raise ValueError('The downbeat at audio time zero must be measure 1.')
    if anchors[0][0]>0:anchors.insert(0,(0,0.))
    phase=between(anchors,pickup,base.seconds_per_tick) if pickup else 0.
    return MeterGrid(base.seconds_per_tick,base.bar_ticks,phase,pickup,tuple(anchors))
