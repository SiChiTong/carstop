#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""
last mod 4/27/18 a variety of issues, most prominently wrong occlusion reasoning
particle filter with MB
[pos, length, speed]
"""
import numpy as np
from scipy.stats import norm as spnorm
import frogger as sim
import tools
import time
#import matplotlib.pyplot as plt

use_video = False
nsamples = 4096

def predict(samples):
    samples[:,0] += samples[:,2]
    
def survival(samples):
    return np.where(np.abs(samples[:,0])-samples[:,1]<sim.road_len, .995, .05)
    
noise_std = sim.pos_noise_std+.1 # add a little tolerance
noise_precision_term = -.5 / noise_std**2
const = (np.pi*2)**-.5 / noise_std
def update(leftend, rightend, msmt):
    if msmt[1]: # left corner included
        ll = np.exp((msmt[2] - leftend)**2 * noise_precision_term) * const
    else:
        ll = spnorm.cdf((msmt[3] - leftend)/noise_std) -\
             spnorm.cdf((msmt[2] - leftend)/noise_std)
    if msmt[4]: # right corner included
        ll *= np.exp((msmt[5] - rightend)**2 * noise_precision_term) * const
    else:
        ll *= spnorm.cdf((msmt[6] - rightend)/noise_std) -\
              spnorm.cdf((msmt[5] - rightend)/noise_std)
    return ll

def DA_JAM(object_msmt, object_miss, miss_msmt):
    m = object_msmt.copy()
    for j in range(1000):
        rowsum = np.sum(m,axis=1) + object_miss
        m = object_msmt / (rowsum[:,None] - m)
        colsum = np.sum(m,axis=0) + miss_msmt
        m = object_msmt / (colsum - m)
    rowsum = np.sum(m,axis=1) + object_miss
    return m/rowsum[:,None], object_miss/rowsum#, 1 - np.sum(m/rowsum[:,None],axis=0)

def report(samples, ids, weights, min_report = .5):
    estimates = []
    for obj in range(len(ids) - 1):
        existo = weights[ids[obj]:ids[obj+1]]
        all_exist = np.sum(existo)
        if all_exist < min_report: continue
        mean = np.einsum(samples[ids[obj]:ids[obj+1],:], [0,1], existo, [0], [1])
        mean /= all_exist
        estimates += [mean]
    return estimates


birth_rate = .15#sim.birth_rate
if use_video:
    video_out = sim.vwriter('vizMWO.mkv', inputdict={'-r':'5'}, outputdict={'-an':'-y'})
ospa = 0.
objcount = 0
sim_rng = np.random.RandomState(2)


all_levels = [(np.zeros((nsamples, 3)), [nsamples], np.zeros((nsamples,)))
                    for level in range(sim.n_levels)]

objects, planned_objects = sim.simpleInit(rng=sim_rng)
firsttime = time.time()
for step in range(2000):
    
    objects, planned_objects, nn = sim.update(objects, planned_objects, rng=sim_rng)
    #### here is where you change the simulated occlusion type!
    all_measurements = sim.sense_MWO(objects, rng=sim_rng)
    
    edges = []
    
    for level in range(sim.n_levels):
                
        samples, ids, weights = all_levels[level]
        predict(samples)
        weights *= survival(samples)
        measurements = [msmt for msmt in all_measurements if msmt[0]==level]
        direction = 1. if level < sim.n_levels_left else -1
        cross_len = sim.crossing_len * (level+1)

        # resampling and birth
        entrance_covered = np.sum(weights[
                    -samples[:,0]*direction+samples[:,1] > sim.road_len])
        if entrance_covered < .3:
            cardinality = np.sum(weights)
            if cardinality > 0:
                cs = np.cumsum(weights) / cardinality
            else: cs = []
            old_obj_cutoff = cardinality / (cardinality + birth_rate)
            n_old_objs = int(old_obj_cutoff * nsamples)
            if n_old_objs > 0:
#                random_entries = np.sort(np.random.random(size=n_old_objs))
                n_fixed = min(n_old_objs, nsamples*3/4)
                fixed_step = 1./n_fixed
                n_random_resamps = n_old_objs - n_fixed
                random_entries = np.sort(np.append(
                                np.arange(np.random.random() * fixed_step,1,fixed_step),
                                    np.random.random(size=n_random_resamps), axis=0))
            else:
                random_entries = []
            index = np.searchsorted(cs, random_entries, 'right')
            ids = np.unique(np.searchsorted(index, ids, 'left'))
            samples = samples[index]
            stds = [.3,.1,sim.speed_walk_std+.02]
            samples += np.random.normal(size=samples.shape) * stds
            new_samples = np.random.uniform([0.,sim.min_car_len, sim.min_car_speed],
                                            [5.,sim.max_car_len, sim.max_car_speed],
                                            size=(nsamples-n_old_objs,3))
            if direction > 0:
                new_samples[:,0] -= sim.road_len
            else:
                new_samples[:,0] += sim.road_len-4
                new_samples[:,2] *= -1
            samples = np.append(samples, new_samples, axis=0)
            weights = np.zeros((nsamples,)) + (cardinality+birth_rate) / nsamples
            if n_old_objs < nsamples:
                ids = np.append(ids, [nsamples])
            # discretization might make an object existence >= 1
            # this will break the system, so push it down
            for obj in range(len(ids)-1):
                correction = (1-1e-8)/np.sum(weights[ids[obj]:ids[obj+1]])
                correction = np.minimum(1, correction)
                weights[ids[obj]:ids[obj+1]] *= correction
            all_levels[level] = (samples, ids, weights)
            assert not np.any(np.isnan(weights))
            

        # update occlusion list
        # this is fairly easy b.c. the measurements were generated the same way
        new_edges = [edge * cross_len/sim.crossing_len/level for edge in edges]
        edges = [edge * cross_len/sim.crossing_len/level for edge in edges]
        for msmt_level, left_visible, left_lower, left_upper,\
            right_visible, right_lower, right_upper in measurements:
            left_edge, right_edge = np.searchsorted(new_edges, [left_lower, right_upper])
            additions = []
            if left_edge % 2 == 0:
                additions += [left_lower]
            if right_edge % 2 == 0:
                additions += [right_lower]
            new_edges = new_edges[:left_edge] + additions + new_edges[right_edge:]
            assert len(new_edges)%2 == 0
    
        # can leave here if you're not filtering
        if len(ids) == 1 or len(measurements) == 0:
            edges = new_edges
            continue
        
        
        leftend, rightend = sim.getLR(samples[:,0], samples[:,1], samples[:,2])
    
        # find object-measurement correspondence
        detect_prob = np.zeros(weights.shape) + sim.detect_prob * .99
        sample_DE = weights * detect_prob
        sample_msmt = np.tile(sample_DE[:,None],(1,len(measurements)))
        for msmt_idx, msmt in enumerate(measurements):
            sample_msmt[:,msmt_idx] *= update(leftend, rightend, msmt)
            
        # for MWO filter, determine block probability
        sample_notblock = 1#sample_DE.copy()
        for pair_idx in range(0, len(edges), 2):
            sample_notblock -= spnorm.cdf((leftend-edges[pair_idx])/noise_std) *\
                               spnorm.cdf((edges[pair_idx+1]-rightend)/noise_std)
        sample_notblock *= sample_DE
        edges = new_edges
        
        # aggregate by object
        obj_miss = []
        obj_msmt = []
        for obj in range(len(ids)-1):
            obj_miss += [1 - np.sum(sample_notblock[ids[obj]:ids[obj+1]])]
            obj_msmt += [np.sum(sample_msmt[ids[obj]:ids[obj+1],:], axis=0)]

        # likelihood of false positives
        miss_msmt = [(1. if msmt[1] else msmt[3]-msmt[2])/sim.road_len/2 *
                     (1. if msmt[4] else msmt[6]-msmt[5])/sim.road_len/2
                     for msmt in measurements]
        miss_msmt = np.array(miss_msmt) * sim.fp_rate / sim.n_levels * 1.1
            
        
        # assignment
        obj_msmt = np.array(obj_msmt)
        obj_miss = np.array(obj_miss)
        miss_msmt = np.array(miss_msmt)
        jam_object_msmt, jam_object_miss = DA_JAM(obj_msmt, obj_miss, miss_msmt)
        match_object_msmt = np.divide(jam_object_msmt, obj_msmt, where=obj_msmt > 1e-30)
        match_object_miss = np.divide(jam_object_miss, obj_miss, where=obj_miss > 1e-30)
        # filtering - so easy for particles
        match_sample_msmt = sample_msmt.copy()
        match_sample_miss = weights - sample_notblock
        for obj in range(len(ids)-1):
            match_sample_msmt[ids[obj]:ids[obj+1],:] *= match_object_msmt[obj,:]
            match_sample_miss[ids[obj]:ids[obj+1]] *= match_object_miss[obj]
        match_sample_filter = np.sum(match_sample_msmt, axis=1) # prob of any match
        assert not np.any(np.isnan(match_sample_filter + match_sample_miss))
        weights[:] = match_sample_filter + match_sample_miss
        

    reported_objects = [(level, pos, length, speed)
                         for level, info in enumerate(all_levels)
                   for pos, length, speed in report(info[0], info[1], info[2])]
        
    if use_video:
        im = sim.im.copy()
        for level, pos, length, speed in objects:
            left, right = sim.getLR(pos, length, speed)
            if left > sim.road_len or right < -sim.road_len: continue
            left = max(0, int(left*sim.ppm + sim.n_horz_pixels/2))
            right = min(sim.n_horz_pixels, int(right*sim.ppm + sim.n_horz_pixels/2))
            top = int((sim.n_levels - level - .1)*sim.crossing_len*sim.ppm)
            bottom = int((sim.n_levels - level + .1)*sim.crossing_len*sim.ppm)
            sim.drawBox2D(top,left,bottom,right, im, color=[0,0,0])
        # plot estimated objects
        for level, pos, length, speed in reported_objects:
            left, right = sim.getLR(pos, length, speed)
            if left > sim.road_len or right < -sim.road_len: continue
            left = max(0, int(left*sim.ppm + sim.n_horz_pixels/2))
            right = min(sim.n_horz_pixels, int(right*sim.ppm + sim.n_horz_pixels/2))
            top = int((sim.n_levels - level - .3)*sim.crossing_len*sim.ppm)
            bottom = int((sim.n_levels - level + .3)*sim.crossing_len*sim.ppm)
            sim.drawBox2D(top,left,bottom,right, im, color=[250,50,50],linewidth=1)
        # plot measurements
        for level, vis_left, left, left2, vis_right, right, right2 in all_measurements:
            left = max(0, int(left*sim.ppm + sim.n_horz_pixels/2))
            left2 = max(0, int(left2*sim.ppm + sim.n_horz_pixels/2))
            right = min(sim.n_horz_pixels, int(right*sim.ppm + sim.n_horz_pixels/2))
            right2 = min(sim.n_horz_pixels, int(right2*sim.ppm + sim.n_horz_pixels/2))
            if vis_right: assert right == right2
            if left >= sim.n_horz_pixels or right2 < 0 or right2<left: continue
            top = int((sim.n_levels - level - .2)*sim.crossing_len*sim.ppm)
            bottom = int((sim.n_levels - level + .2)*sim.crossing_len*sim.ppm)
            if vis_left > 0 and vis_right > 0:
                sim.drawBox2D(top, left, bottom, right, im, color=[10,10,255], linewidth=0)
            elif vis_left > 0:
                sim.drawBox2D(top, left, bottom, right2, im, color=[10,10,255],linewidth=0,
                          sides_to_include=[False,True,True,False])
            elif vis_right > 0:
                sim.drawBox2D(top, left, bottom, right2, im, color=[10,10,255],linewidth=0,
                          sides_to_include=[False,False,True,True])
            else:
                sim.drawBox2D(top, left, bottom, right2, im, color=[10,10,255],linewidth=0,
                          sides_to_include=[False,False,True,False])
    #    plt.figure(figsize = (10,3)); plt.xticks([]); plt.yticks([])
    #    plt.imshow(im, interpolation='none')
    #    plt.show()
        video_out.writeFrame(im)
    
    ospa += tools.GOSPA(objects, reported_objects, c=5, costFun=tools.froggerDist)
    objcount += len(objects)
    
if use_video:
    video_out.close()
print ospa/objcount
print objcount
print(time.time() - firsttime)
