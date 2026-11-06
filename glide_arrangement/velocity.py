"""Velocity-conditioned additive envelopes for isolated-note experiments."""
from dataclasses import dataclass

import numpy as np
from numpy.polynomial.chebyshev import chebvander

from .instrument import GRID

METHODS = ("amplitude","partials","joint")

def _interpolate(table,value):
    keys = sorted(table)
    index = int(np.searchsorted(keys,value))
    lo,hi = keys[max(0,index-1)],keys[min(len(keys)-1,index)]
    mix = np.clip((value-lo)/(hi-lo),0,1) if lo!=hi else 0
    return table[lo]*(1-mix)+table[hi]*mix

def _design(pitch,velocity,time):
    p = chebvander(np.broadcast_to((pitch-60)/24,time.shape),3)
    v = chebvander(np.broadcast_to((velocity-76)/51,time.shape),2)
    t = chebvander(time/.4-1,6)
    return np.einsum("ij,ik,il->ijkl",p,v,t).reshape(len(time),-1)

@dataclass
class VelocityModel:
    layers: dict
    coefficients: np.ndarray

    def predict(self,pitch,velocity,method):
        if method=="joint":
            return np.maximum(np.exp(_design(pitch,velocity,GRID)@self.coefficients).T-1e-4,0)
        if method not in METHODS:
            raise ValueError("Modelo de velocidad desconocido")
        # Interpolate across the available pitches at each training velocity
        # before combining velocities. This supports sparse recording grids.
        speeds = sorted({speed for layer in self.layers.values() for speed in layer})
        estimates = {speed:_interpolate({key:layer[speed] for key,layer in self.layers.items()
                                        if speed in layer},pitch) for speed in speeds}
        if method=="partials":
            return _interpolate(estimates,velocity)
        middle = min(estimates,key=lambda speed:abs(speed-75))
        levels = {speed:np.linalg.norm(matrix) for speed,matrix in estimates.items()}
        return estimates[middle]*(_interpolate(levels,velocity)/max(levels[middle],1e-8))


def fit_velocity(examples):
    """Train using (pitch, velocity, actual-amplitude matrix) observations."""
    layers = {}
    designs,targets = [],[]
    for pitch,velocity,values in examples:
        if not (0<=pitch<=127 and 1<=velocity<=127):
            raise ValueError("Altura o velocidad inválida")
        matrix = np.asarray(values)
        if matrix.shape!=(8,len(GRID)) or not np.all(np.isfinite(matrix)) or np.any(matrix<0):
            raise ValueError("Envolvente inválida")
        layers.setdefault(pitch,{})[velocity] = matrix
        designs.append(_design(pitch,velocity,GRID))
        targets.append(np.log(matrix.T+1e-4))
    if not designs:
        raise ValueError("Sin ejemplos de calibración")
    x,y = np.concatenate(designs),np.concatenate(targets)
    coefficients = np.linalg.solve(x.T@x+np.eye(x.shape[1])*.4,x.T@y)
    return VelocityModel(layers,coefficients)
