#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""
last mod 8/20/18
computer's IP must be at 192.168.1.0 (or whatever lidar is configured to send to)

function = get(block, timeout)
timeout should probably be .05

output = numpy float array, variable length, width 3
         xyz of each laser point
"""
from math import cos, sin, pi
import numpy as np
import socket, select, struct
from multiprocessing import Process, Queue#, Manager
from Queue import Empty

laser = 1 # or 14

distance_convert = .002
vert_angles = [-15,1,-13,3,-11,5,-9,7,-7,9,-5,11,-3,13,-1,15]
vert_angle = vert_angles[laser]
vert_cos = cos(vert_angle*np.pi/180)*distance_convert
vert_sin = sin(vert_angle*np.pi/180)*distance_convert
shortStruct = struct.Struct('<H')
longStruct = struct.Struct('<L')
firefmt = struct.Struct('<'+ 'HB'*32)
angle_convert = np.pi / 18000.
time_convert = 1e-6
angle_step = .0033 # radians of offset firing
step_cos = np.cos(angle_step)
step_sin = np.sin(angle_step)

min_distance_to_keep = .2 / distance_convert
max_distance_to_keep = 30. / distance_convert

def processLidarPacket(msg, last_angle = 0):
    points = []
    prev_points = points
    after_points = []
    cut = False
    cut_idx = 384
    
    for k in range(12):
        angle = shortStruct.unpack(msg[k*100 + 2: k*100 + 4])[0] * angle_convert
        hcos = np.cos(angle)
        hsin = np.sin(angle)
        hcos2 = hcos * step_cos - hsin * step_sin
        hsin2 = hcos * step_sin + hsin * step_cos
        if angle < last_angle:
            cut = True
            cut_idx = k*32
        last_angle = angle
        
        #fires = np.array(firefmt.unpack(msg[k*100 + 4: k*100 + 100])).reshape((32,2))
        fires = np.array(firefmt.unpack(msg[k*100 + 4 : k*100 + 100])[::2])
        r = fires[laser] * vert_cos
        if r > min_distance_to_keep and r < max_distance_to_keep:
            x = r * hcos
            y = r * -hsin
            points.append((x,y))
        r = fires[laser+16] * vert_cos
        if r > min_distance_to_keep and r < max_distance_to_keep:
            x = r * hcos2
            y = r * -hsin2
            points.append((x,y))


class LIDAR(Process):
    def __init__(self, queue=None, port=2368):
        Process.__init__(self)
        self.sock = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        self.port = port
        if queue is None:
            self.queue = Queue()
        else:
            self.queue = queue
        self.gap_time = True
        
    def __enter__(self):
        print("connecting to LIDAR...")
        self.sock.bind(('', self.port))
        print("waiting for first LIDAR packet...")
        self.select_sock = (self.sock,)
        ready_to_read, to_write, in_error = select.select(self.select_sock, [], [], 30.)
        assert len(ready_to_read) > 0, "LIDAR not running within 30 seconds"
        print("LIDAR working")
        
        # do one read so that all future reads are complete rotations
        msg = self.sock.recv(1206)
        assert len(msg) == 1206
        data_pre, cut, data_post, time, angle = processLidarPacket(msg, 0.)
        while not cut:
            readable,a,b = select.select(self.select_sock, [], [], .1)
            assert len(readable) > 0, "LIDAR rx timeout"
            msg = self.sock.recv(1206)
            assert len(msg) == 1206
            data_pre, cut, data_post, time, angle = processLidarPacket(msg, angle)
        self.points = data_pre
        
        # start stuff
        Process.start(self)
        return self
    
    # timeout should probably be .05?
    def get(self, timeout=.05):
        try:
            points = self.queue.get(timeout=timeout)
        except Empty: # no rotation available, just wait
            assert not self.gap_time
            self.gap_time = True
            return self.points.copy()
        try:
            points = self.queue.get(block=False) # grab extra waiting rotations
        except Empty: pass
        self.gap_time = False
        self.points = points
        return points.copy()
    
        
    # this is the part that runs in a separate thread - or at least it should
    def run(self):
        angle = 0
        rotation = []
        on_right = True
        while True:
            readable,a,b = select.select(self.select_sock, [], [], .1)
            assert len(readable) > 0, "LIDAR rx timeout"
            msg = self.sock.recv(1206)
            assert len(msg) == 1206
            
            for k in range(12):
                angle = shortStruct.unpack(msg[k*100 + 2: k*100 + 4])[0] * angle_convert
                hcos = np.cos(angle)
                hsin = np.sin(angle)
                hcos2 = hcos * step_cos - hsin * step_sin
                hsin2 = hcos * step_sin + hsin * step_cos
                if angle < last_angle:
                    cut = True
                    cut_idx = k*32
                last_angle = angle
                
                #fires = np.array(firefmt.unpack(msg[k*100 + 4: k*100 + 100])).reshape((32,2))
                fires = np.array(firefmt.unpack(msg[k*100 + 4 : k*100 + 100])[::2])
                r = fires[laser] * vert_cos
                if r > min_distance_to_keep and r < max_distance_to_keep:
                    x = r * hcos
                    y = r * -hsin
                    rotation.append((x,y))
                r = fires[laser+16] * vert_cos
                if r > min_distance_to_keep and r < max_distance_to_keep:
                    x = r * hcos2
                    y = r * -hsin2
                    rotation.append((x,y))
                    
            if on_right and hsin2
            
            data_pre, cut, data_post, time, angle = processLidarPacket(msg, angle)
            rotation.append(data_pre)
            if cut:
                self.queue.put(np.concatenate(rotation, axis=0))
                rotation = [data_post]
    
    def __exit__(self, errtype=None, errval=None, traceback=None):
        if not (errtype is None or errtype is KeyboardInterrupt or
                                   errtype is SystemExit):
            print(errtype)
            print(errval)
        self.terminate()
        
    def terminate(self):
        self.sock.close()
        self.queue.close()
        super(LIDAR, self).terminate()
        
        
### test
if __name__ == '__main__':
    
    # set up real-time plot
    import matplotlib.pyplot as plt
    from matplotlib.cm import ScalarMappable
    from matplotlib.colors import Normalize
    fig1 = plt.figure(figsize=(8., 8.))
    fig1.subplots_adjust(left=0, bottom=0, right=1, top=1, wspace=None, hspace=None)
    ax = fig1.gca()
    ax.set_xlim([-50,50])
    ax.set_ylim([-50,50])
    plt.margins(0,0)
    mycar = ax.add_patch(plt.Rectangle((-3.6,-1),5.,2.,0.,fill=True, color='k'))
    scatterpoints = ax.scatter([], [], 2., color=[],
                                 cmap = ScalarMappable(Normalize(0,7)))
    fig1.canvas.draw()
    plt.show(block=False)
    fig1.canvas.update()
    fig1.canvas.flush_events()
    rotation_period = 1 # optionally don't update plot every time
    rotations = 0
    

    with LIDAR() as lidar:
        while True:
            data = lidar.get(timeout=.11)
            
            # update plot
            rotations += 1
            if rotations % rotation_period == 0:
#                thistime = time.time()
#                print thistime - lasttime
#                lasttime = thistime
                # get downward points
                data = data[data[:,2] < 0]
                # get points past car itself
                data = data[np.hypot(data[:,0], data[:,1]) > 1.5]
                scatterpoints.set_offsets(data[:,:2])
                scatterpoints.set_array(data[:,2])
                ax.draw_artist(ax.patch)
                ax.draw_artist(mycar)
                ax.draw_artist(scatterpoints)
                fig1.canvas.update()
                fig1.canvas.flush_events()