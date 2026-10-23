"""A metrical grid with an optional initial incomplete measure."""
from dataclasses import dataclass

@dataclass(frozen=True)
class MeterGrid:
    seconds_per_tick:float
    bar_ticks:int
    phase:float=0.
    pickup_ticks:int=0

    def tick(self,seconds):
        if self.pickup_ticks and seconds<self.phase:return seconds/self.phase*self.pickup_ticks
        return self.pickup_ticks+(seconds-self.phase)/self.seconds_per_tick

    def time(self,tick):
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
    return MeterGrid(base.seconds_per_tick,base.bar_ticks,grid.get('phaseSeconds',0.),grid.get('pickupTicks',0))
