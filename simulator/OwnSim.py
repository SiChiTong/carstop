# -*- coding: utf-8 -*-
"""
last mod 10/7/16, got rid of special turns for Qsim and added exit keystroke
"""
import numpy as np
import pandas as pd
import world
import time

def getLineLength(x1,y1, x2,y2):
    return ((y2-y1)**2 + (x2-x1)**2)**.5

def getLineLoc(x1,y1,x2,y2,dist):
    length = getLineLength(x1,y1,x2,y2)
    if dist > length:
        (0,0,0)
    x = x1+(x2-x1)*dist/length
    y = y1+(y2-y1)*dist/length
    angle = np.arctan2(y2-y1,x2-x1)
    return (x,y,angle)
    
def sumoAngle(pos, dist): # this is close to how SUMO gets its angles
    return pos/dist*np.pi/2 - np.sin(pos/dist*2*np.pi)*.2
    
def getCircleLength(x1in, y1in, x2in, y2in, x1out, y1out, x2out, y2out):
    x1 = x2in
    y1 = y2in
    x2 = x1out
    y2 = y1out
    pi = np.pi
    
    theta = np.arctan2(y2in-y1in, x2in-x1in)
    thetaOut = np.arctan2(y2out-y1out, x2out-x1out)
    angleChange = np.abs(theta - thetaOut)
    if min(angleChange, 2*pi - angleChange) < .01: # straight
        return getLineLength(x1,y1,x2,y2)
    
    r = (((y2-y1)**2.+(x2-x1)**2.) /2)**.5
    return r * pi / 2.
    
def getCircleLoc(x1in, y1in, x2in, y2in, x1out, y1out, x2out, y2out, dist):
    x1 = x2in
    y1 = y2in
    x2 = x1out
    y2 = y1out
    pi = np.pi
    
    theta = np.arctan2(y2in-y1in, x2in-x1in)
    thetaOut = np.arctan2(y2out-y1out, x2out-x1out)
    angleChange = np.abs(theta - thetaOut)
    if min(angleChange, 2*pi - angleChange) < .01: # straight
        return getLineLoc(x1,y1,x2,y2, dist)
    elif min(angleChange, 2*pi - angleChange) < pi/2 - .02:
        print "curve not perpendicular, current getCircleLoc inaccurate"    
    
    r = (((y2-y1)**2.+(x2-x1)**2.) /2)**.5
    if dist > r*pi/2.:
        return (0,0,0)
    bend = (y2-y1)*np.cos(theta) - (x2-x1)*np.sin(theta)
        
    relativeAngle = sumoAngle(dist, r*pi/2 + 5.)
        
    if bend > 0: # counterclockwise
        xr = x1 + r*np.cos(theta + pi/2)
        yr = y1 + r*np.sin(theta + pi/2)
        xf = xr + r*np.cos(theta - pi/2 + dist/r)
        yf = yr + r*np.sin(theta - pi/2 + dist/r)
        angle = theta + relativeAngle
    else: # clockwise
        xr = x1 + r*np.cos(theta - pi/2)
        yr = y1 + r*np.sin(theta - pi/2)
        xf = xr + r*np.cos(theta + pi/2 - dist/r)
        yf = yr + r*np.sin(theta + pi/2 - dist/r)
        angle = theta - relativeAngle
    return (xf,yf,angle)


class RoadMap():
    def __init__(self, roads, intersections):
        # roads format: map of string (name) to tuple (x1,y1,x2,y2)
        # intersections format: list of [road1, road2]
        self.roads = roads
        self.intersections = intersections
        self.roadNameLen = len(next(roads.iterkeys()))
        
    # for two road names, find the name of the intersection road between them
    def combineRoad(self, inroad, outroad):
        if any(list(inroad==i and outroad==j for i,j in self.intersections)):
            return inroad + '_' + outroad
        return None
        
    # determine whether a road name belongs to an original road or an intersection
    def isIntersection(self, lane):
        return len(lane) == self.roadNameLen*2+1
        
    # given an intersection road name, return the two original road names
    def splitIntersection(self, intersectionRoad):
        middleInd = int(len(intersectionRoad)/2)
        assert(intersectionRoad[middleInd] == '_')
        return [intersectionRoad[:middleInd], intersectionRoad[middleInd+1:]]
           
    def getLength(self, lane):
        if self.isIntersection(lane):
            inroad, outroad = self.splitIntersection(lane)
            x1in,y1in,x2in,y2in = self.roads[inroad]
            x1out,y1out,x2out,y2out = self.roads[outroad]
            return getCircleLength(x1in,y1in,x2in,y2in,x1out,y1out,x2out,y2out)
        return getLineLength(*self.roads[lane])
           
    def getLoc(self, lane, pos, prevLane = None):
        if self.isIntersection(lane): # intersection
            inroad, outroad = self.splitIntersection(lane)
            x1in,y1in,x2in,y2in = self.roads[inroad]
            x1out,y1out,x2out,y2out = self.roads[outroad]
            return getCircleLoc(x1in,y1in,x2in,y2in,x1out,y1out,x2out,y2out, pos)
        x1,y1,x2,y2 = self.roads[lane]
        loc = getLineLoc(x1,y1,x2,y2, pos)
        if pos < 5. and not (prevLane is None):
            prevLaneLength = self.getLength(prevLane)
            inroad, outroad = self.splitIntersection(prevLane)
            x1in,y1in,x2in,y2in = self.roads[inroad]
            x,y,oldangle = getLineLoc(x1in, y1in, x2in, y2in, 0.)
            angleChange = loc[2] - oldangle
            if angleChange > np.pi:
                angleChange = angleChange - np.pi*2
            if angleChange < -np.pi:
                angleChange = angleChange + np.pi*2
            if np.abs(angleChange) > 0.1: # actually was an angle change
                angle = oldangle + np.sign(angleChange)*\
                        sumoAngle(pos + prevLaneLength, prevLaneLength + 5.)
                return (loc[0],loc[1], angle)
        return loc
    
    
class Simulator():
    def __init__(self, roadMap, gui, delay = .1, waitOnStart = False):
        self.RM = roadMap
        self.lanes = {}
        self.pos = {}
        self.offset = {}
        self.previousLanes = {}
        self.delay = delay
        self.gui = gui     
        self.inProjection = False
        
        if gui:
            xdim, ydim = self._findMapSize()
            self.world = world.World(xdim, ydim, resolution = 5.)
            for road in self.RM.roads.itervalues():
                roadshape = world.Road((road[0],road[1]),(road[2],road[3]))
                self.world.AddRoad(roadshape)
            if len(self.RM.intersections) > 0:
                self.world.AddRoad(self._findIntersectionArea())
            self.world.Start(waitOnStart)
            
    def _findMapSize(self):
        roads = self.RM.roads
        xValues = []
        yValues = []
        for road in roads.itervalues():
            x1,y1,x2,y2 = road
            wd = 1.5 / ((x2-x1)**2 + (y2-y1)**2)**.5
            wdx = wd*(y2-y1)
            wdy = wd*(x2-x1)
            xValues += [x1 + wdx, x1 - wdx, x2 + wdx, x2 - wdx]
            yValues += [y1 + wdy, y1 - wdy, y2 + wdy, y2 - wdy]
        return (max(xValues), max(yValues))
    
    def _findIntersectionArea(self):
        intersections = self.RM.intersections
        xValues = []
        yValues = []
        for inroad, outroad in intersections:
            x,y,x1,y1 = self.RM.roads[inroad]
            x2,y2,x,y = self.RM.roads[outroad]
            xValues += [x1,x2]
            yValues += [y1,y2]
        minx = min(xValues)
        maxx = max(xValues)
        centerx = (maxx + minx)/2
        differencex = (maxx - minx)/2
        miny = min(yValues)
        maxy = max(yValues)
        centery = (maxy + miny)/2
        #differencey = (maxy - miny)/2
        return world.IntersectionBox((centerx, centery), differencex)
    
    def createVehicle(self, ID, lane, pos=0.):
        self.lanes[ID] = lane
        self.pos[ID] = pos
        self.offset[ID] = 0.
        self.previousLanes[ID] = None
        
        if self.gui and not self.inProjection:
            self.world.AddCar(world.Car(ID, *self.RM.getLoc(lane, pos)))
            
    def moveVehicle(self, ID, lane, pos=None, offset=None):
        self.lanes[ID] = lane
        if not pos is None:
            self.pos[ID] = pos
        if not offset is None:
            self.offset[ID] = offset
        else:
            self.offset[ID] = 0.
        self._guiMoveVehicle(ID)
            
    def moveVehicleAlong(self, ID, dist, turn='nopreference'):
        currentLane = self.lanes[ID]
        lanelength = self.RM.getLength(currentLane)
        newpos = self.pos[ID] + dist
        removed = False        
        
        if newpos <= lanelength: # can stay on this road
            self.pos[ID] = newpos
        
        # entering a new road
        else:
            self.pos[ID] = newpos - lanelength
            self.previousLanes[ID] = currentLane
            self.offset[ID] = 0.
            if self.RM.isIntersection(currentLane): # intersection to exit road
                self.lanes[ID] = self.RM.splitIntersection(currentLane)[1]

            else: # entering intersection
                laneFound = False
                # next lane is given as a string
                if [currentLane, turn] in self.RM.intersections:
                    self.lanes[ID] = self.RM.combineRoad(currentLane, turn)
                    laneFound = True
                # couldn't find road with correct turn, use wrong one
                if not laneFound:
                    for inroad, outroad in self.RM.intersections:
                        if inroad == currentLane:
                            self.lanes[ID] = self.RM.combineRoad(inroad, outroad)
                            laneFound = True
                if laneFound:
                    pass
                    #print "new lane "+self.lanes[ID]
                else: # there is no road after this one
                    removed = True
                    
        if not removed:
            self._guiMoveVehicle(ID)
        return removed
            
    def getVehicleState(self, ID):
        x,y,angle = self.RM.getLoc(self.lanes[ID],self.pos[ID], self.previousLanes[ID])
        finalcoords = self._applyOffset(x,y,angle, self.offset[ID])
        return [self.lanes[ID], self.pos[ID], finalcoords, angle]         
            
    def _guiMoveVehicle(self, ID):
        if self.gui and not self.inProjection:
            x,y,angle = self.RM.getLoc(self.lanes[ID],self.pos[ID],
                                       self.previousLanes[ID])
            x,y = self._applyOffset(x,y,angle, self.offset[ID])
            self.world.moveCar(ID, x, y, angle)
    
    def removeVehicle(self, ID):
        del self.lanes[ID]
        del self.pos[ID]
        
        if self.gui:
            self.world.removeCar(ID)
            
    def offsetVehicle(self, ID, offsetAmt):
        self.offset[ID] = self.offset[ID] + offsetAmt      
        
    def _applyOffset(self, x,y,angle, offsetAmt): # orthogonal offset
        return (x + np.sin(angle)*offsetAmt, y - np.cos(angle)*offsetAmt)
            
    def updateGUI(self, allowPause=False, allowExit=False):
        time.sleep(self.delay)
        if self.gui:
            return self.world.Step(allowPause,allowExit)
        return False
        
    def end(self, waitOnEnd=False):
        if self.gui:
            self.world.End(waitOnEnd)
            
    def addCrashSymbol(self, carID1, carID2):
        if self.gui:
            x1,y1,angle = self.RM.getLoc(self.lanes[carID1],self.pos[carID1])
            x2,y2,angle = self.RM.getLoc(self.lanes[carID2],self.pos[carID2])
            self.world.drawOtherShape(
                        world.CrashSymbol((x1/2.+x2/2., y1/2.+y2/2.)))
                    
    def startProjection(self):
        self.truestate = [self.lanes, self.pos]
        self.inProjection = True
    def endProjection(self):
        self.lanes = self.truestate[0]
        self.pos = self.truestate[1]
        self.inProjection = False
        
        
'''
Extra functions that may be needed someday   
''' 
def getLinePos(x1,y1,x2,y2,x,y):
    length = getLineLength(x1,y1,x2,y2)
    pos = (x-x1)/(x2-x1)*length
    return pos
    
def getCirclePos(x1in, y1in, x2in, y2in, x1out, y1out, x2out, y2out, x, y):
    x1 = x2in
    y1 = y2in
    x2 = x1out
    y2 = y1out
    theta = np.arctan2(y2in-y1in,x2in-x1in)
    pi = np.pi
    
    r = (((y2-y1)**2.+(x2-x1)**2.) /2)**.5
    bend = (y2-y1)*np.cos(theta) - (x2-x1)*np.sin(theta)
    if bend > 0:
        xr = x1 + r*np.cos(theta + pi/2)
        yr = y1 + r*np.sin(theta + pi/2)
        angle = np.arctan2(y-yr,x-xr) - theta + pi/2
    else:
        xr = x1 + r*np.cos(theta - pi/2)
        yr = y1 + r*np.sin(theta - pi/2)
        angle = np.arctan2(y-yr,x-xr) - theta - pi/2
    return angle * r
    
    # roadmap method
    def getPos(self, lane, x, y):
        if self.isIntersection(lane): # intersection
            inroad = lane[:4]
            outroad = lane[5:]
            x1in,y1in,x2in,y2in = self.roads[inroad]
            x1out,y1out,x2out,y2out = self.roads[outroad]
            return getCirclePos(x1in,y1in,x2in,y2in,x1out,y1out,x2out,y2out, x,y)
        x1,y1,x2,y2 = self.roads[lane]
        return getLinePos(x1,y1,x2,y2, x,y)