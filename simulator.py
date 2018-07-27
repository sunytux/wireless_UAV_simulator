#! /usr/bin/python2.7 -u
# -*- coding: utf-8 -*-

"""Wireless UAV simulator.

This script aims at validating UAV trajectory planner in the context of
wireless UAV networks by computing several channel metrics along its path. This
is done in an iterative manner. At each position, the received signals on the
four UAV's antennas is simulated with an external Matlab simulator, which is
then used by the trajectory planner to compute the next UAV position and
orientation.

# TODO The stop condition is ...


It takes as input: user, base-station (BS) and UAV initial conditions as well
as a map of the environment and returns a complete set of information
describing both the UAV and the environment at every moment.

Usage:
    simulator.py [-i ITER] [-o DIR]

Arguments:

Options:
    -i ITER         Iterations [default: 12].
    -o DIR          Output directory [default: /tmp/result].
    -h, --help
"""
import logging
import math
from rayTracingWrapper import CloudRT
import numpy as np
from docopt import docopt
import os


LOG_FILE = "flight.csv"

logging.basicConfig(level=logging.DEBUG)
LOGGER = logging.getLogger(__name__)


def main(f, iterations, resultDir):

    terminals = [
        baseStation(96, 69, 200, 0, 0, 0),  # Base-station
        baseStation(325, 250, 2, 0, 0, 0),  # User 1
        baseStation(425, 150, 2, 0, 0, 0),  # User 2
        baseStation(225, 350, 2, 0, 0, 0),
        baseStation(225, 50, 2, 0, 0, 0)
    ]

    drone = Drone(176, 290, 100, 0, 0, 0, len(terminals),
                  # antOffset=np.deg2rad(range(0, 360, 20)),
                  routineAlgo="optimize",
                  AoAAlgo="max-rss")
    env = EnvironmentRF(f, resultDir, terminals, drone)

    for i in range(1, iterations):
        LOGGER.debug("Iterration %d", i)
        drone.routine(env)
        env.incTime()

    f.close()


def args():
    """Handle arguments for the main function."""

    iterations = int(docopt(__doc__)['-i'])
    resultDir = docopt(__doc__)['-o']
    if not os.path.exists(resultDir):
        os.makedirs(resultDir)

    logFilePath = os.path.join(resultDir, LOG_FILE)
    f = open(logFilePath, 'w')

    return [f, iterations, resultDir]


class Antenna(object):
    """docstring for Antenna"""
    def __init__(self, u, v, w):
        self.Re = 0  # I
        self.Im = 0  # Q
        self.u = u
        self.v = v
        self.w = w

    def setIQ(self, Re, Im):
        if Re == 0 and Im == 0:
            LOGGER.warn("Computed IQ are too low; Re = Im = 1e-12.")
            Re = Im = 1e-12
        self.Im = Im
        self.Re = Re

    @property
    def rss(self):
        return self.Im**2 + self.Re**2

    @rss.setter
    def rss(self, amount):
        pass


class Terminal(object):
    """docstring for Terminal"""
    def __init__(self, x, y, z, u, v, w):
        self.x = x
        self.y = y
        self.z = z
        self.u = u
        self.v = v
        self.w = w

        self.ant = []

    def _addAntenna(self, u, v, w):
        self.ant.append(Antenna(u, v, w))


class baseStation(Terminal):
    """docstring for baseStation"""
    def __init__(self, x, y, z, u, v, w):
        Terminal.__init__(self, x, y, z, u, v, w)

        self._addAntenna(0, 0, 0)


class EnvironmentRF(object):
    """docstring for EnvironmentRF"""
    def __init__(self, logFile, resultDir, terminals, drone):
        self.logFile = logFile

        self.terminals = terminals

        self.rt = CloudRT(resultDir, quiteMode=True)

        self.time = 0

        self._initLog(drone)

    def incTime(self):
        self.time += 1

    def scan(self, drone, txIdx):
        """Compute received signal on drone antennas for a given situation."""

        tx = self.terminals[txIdx]

        self.rt.setTxPose(tx.x, tx.y, tx.z,
                          tx.u + tx.ant[0].u,
                          tx.v + tx.ant[0].v,
                          tx.w + tx.ant[0].w)

        for i in range(len(drone.ant)):
            self.rt.setRxPose(drone.x, drone.y, drone.z,
                              drone.u + drone.ant[i].u,
                              drone.v + drone.ant[i].v,
                              drone.w + drone.ant[i].w)

            simId = "u{:02d}-t{:04d}-ant{:02d}".format(txIdx, self.time, i)
            IQ = self.rt.simulate(simId)
            drone.ant[i].setIQ(*IQ)

        simIds = "u{:02d}-t{:04d}-antXX".format(txIdx, self.time)

        self._log(drone, simIds)

    def _initLog(self, drone):
        def expand(t):
            return [t + ".x", t + ".y", t + ".z", t + ".u", t + ".v", t + ".w"]

        header = [
            "time", "simIdxs",
        ]
        header += expand("drone")
        for i in range(len(self.terminals)):
            header += expand("user-" + str(i))
        header += ["ant." + str(i) for i in range(len(drone.ant))]

        header = ",".join(header) + '\n'

        self.logFile.write(header)

    def _log(self, drone, simIdxs):
        rss = [a.rss for a in drone.ant]

        def expand(t):
            return [t.x, t.y, t.z, t.u, t.v, t.w]

        row = [
            self.time, simIdxs,
        ]
        row += expand(drone)
        for t in self.terminals:
            row += expand(t)
        row += rss

        lineFmt = "{:d},{:s}" + ",{:.16f}" * (len(row) - 2) + '\n'

        self.logFile.write(lineFmt.format(*row))


class Drone(Terminal):
    """docstring for Drone"""
    DEFAULT_ANTENNAS_OFFSET = np.deg2rad([0, 90, 180, 270])

    def __init__(self, x, y, z, u, v, w, nbUsers,
                 antOffset=DEFAULT_ANTENNAS_OFFSET,
                 routineAlgo="locate",
                 AoAAlgo="weighted-rss"):
        Terminal.__init__(self, x, y, z, u, v, w)

        self.nbUsers = nbUsers
        self.antOffset = antOffset

        self.routineAlgo = routineAlgo
        self.AoAAlgo = AoAAlgo

        for offset in self.antOffset:
            # TODO check 90 + 45
            self._addAntenna(np.deg2rad(90) + offset, np.deg2rad(90 + 45), 0)

    def routine(self, env):
        if self.routineAlgo == "locate":
            self.routine_locate(env)
        elif self.routineAlgo == "optimize":
            self.routine_optimize(env)

    def routine_optimize(self, env):
        # TODO add support for multiple user

        # Drone-user
        env.scan(self, 1)
        AoAUser = self.getAoA()
        maxRssUser = max([a.rss for a in self.ant])

        LOGGER.debug('User to drone: AoA = ' + str(np.rad2deg(AoAUser)))
        LOGGER.debug('User to drone: rss = ' + str(np.rad2deg(maxRssUser)))

        # Drone-base-station
        env.scan(self, 0)
        AoABs = self.getAoA()
        maxRssBs = max([a.rss for a in self.ant])

        LOGGER.debug('Bs to drone: AoA = ' + str(np.rad2deg(AoABs)))
        LOGGER.debug('Bs to drone: rss = ' + str(maxRssBs))

        if maxRssBs > maxRssUser:
            d = [math.cos(AoAUser + self.u), math.sin(AoAUser + self.u)]
        else:
            d = [math.cos(AoABs + self.u), math.sin(AoABs + self.u)]

        COEF = 20

        self.x += COEF * d[0]
        self.y += COEF * d[1]

    def routine_locate(self, env):
        # TODO add support for choosing which user to locate

        # Drone-user
        env.scan(self, 1)
        AoA = self.getAoA()
        maxRss = max([a.rss for a in self.ant])

        LOGGER.debug('User to drone: AoA = ' + str(np.rad2deg(AoA)))
        LOGGER.debug('User to drone: rss = ' + str(maxRss))

        d = [math.cos(AoA + self.u), math.sin(AoA + self.u)]

        COEF = 20

        self.x += COEF * d[0]
        self.y += COEF * d[1]

    def getAoA(self):
        if self.AoAAlgo == "max-rss":
            return self.getAoA_maxRSS()
        elif self.AoAAlgo == "weighted-rss":
            return self.getAoA_weightedRSS()

    def getAoA_maxRSS(self):
        """Return the estimated AoA using the maximum rss algorithm.

        Return : AoA relative to the drone in radians.
        """
        rss = [(i, self.ant[i].rss) for i in range(len(self.ant))]
        rss = sorted(rss, key=lambda a: a[1])[-1]

        return self.antOffset[rss[0]]

    def getAoA_weightedRSS(self):
        """Return the estimated AoA using the weighted-rss algorithm.

        Return : AoA relative to the drone in radians.
        """
        rss = [(i, self.ant[i].rss) for i in range(len(self.ant))]
        rss = sorted(rss, key=lambda a: a[1])[:-3:-1]

        phi1, rss1 = self.antOffset[rss[0][0]], rss[0][1]
        phi2, rss2 = self.antOffset[rss[1][0]], rss[1][1]

        # When phi1 and phi2 are separated by more than 180° their mean is on
        # the wrong side of the circle
        if max([phi1, phi2]) - min([phi1, phi2]) > np.deg2rad(180):
            if phi1 > phi2:
                phi2 += np.deg2rad(360)
            else:
                phi1 += np.deg2rad(360)

        return (rss1 * phi1 + rss2 * phi2) / (rss1 + rss2)


if __name__ == '__main__':
    main(*args())
