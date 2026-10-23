"""Shared notation/harmony primitives for the active score pipeline."""
from dataclasses import dataclass


TONICS = {'Cb':11,'C':0,'C#':1,'Db':1,'D':2,'D#':3,'Eb':3,'E':4,'Fb':4,'F':5,'F#':6,'Gb':6,'G':7,'G#':8,'Ab':8,'A':9,'A#':10,'Bb':10,'B':11}

INTERVALS = {'major':(0,4,7),'minor':(0,3,7),'dim':(0,3,6),'maj7':(0,4,7,11),'min7':(0,3,7,10),'7':(0,4,7,10)}

@dataclass(frozen=True)
class Chord:
    root: int
    quality: str
    roman: str
    function: str

    @property
    def pcs(self): return tuple((self.root+step)%12 for step in INTERVALS[self.quality])

    @property
    def seventh(self): return self.pcs[-1] if len(self.pcs)==4 else None

def transition_cost(left,right):
    if left==right: return .025
    functional={('T','T'):.13,('T','P'):.04,('T','D'):.12,('P','T'):.16,('P','P'):.14,('P','D'):.015,('D','T'):.01,('D','D'):.2,('D','P'):.5}
    motion=(right.root-left.root)%12
    return functional[left.function,right.function]+(.03 if motion in (5,7) else .1)+.04
