#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Parameters:
1. lengthe of feature vectors
2. types of features
3. Gaussian mixtures
4. Segment length
5. Number of iterations of EM
6. 

TODO: Density estimation of GMM for accuracy of GMM for specific speaker. 

Created on Sun Nov 19 12:29:28 2017

@author: rehan

    --- Optional: ---
    spnsp_file:         spnsp file (all features used by default)
    em_iterations:      Number of iterations for the standard
                        segmentation loop training (3 by default)
    num_seg_iters_init: Number of majority vote iterations
                        in the initialization phase (2 by default)
    num_seg_iters:      Number of majority vote iterations
                        in the main loop (3 by default)
    seg_length:         Segment length for majority vote in frames
                        (250 frames by default)

"""
import time
import scipy.stats.mstats as stats
import numpy as np
from gmm import *
from SAD import silenceRemoval
from pyannote.core import Segment, Timeline, Annotation
from pyannote.metrics.diarization import DiarizationErrorRate
from pyannote.metrics.diarization import DiarizationPurity
from pyannote.metrics.detection import DetectionErrorRate
import librosa
import xml.etree.ElementTree as ET
from copy import copy
from sklearn.preprocessing import StandardScaler

class Diarizer(object):

    def __init__(self, data, total_frames):
        pruned_list = data       
        floatArray = np.array(pruned_list, dtype = np.float32)
        self.X = floatArray.T
        
        self.N = self.X.shape[0]
        self.D = self.X.shape[1]
        self.total_num_frames = total_frames
        
    def write_to_RTTM(self, rttm_file_name, sp_file_name,\
                      meeting_name, most_likely, num_gmms,\
                      seg_length):

        print("...Writing out RTTM file...")
        #do majority voting in chunks of 250
        duration = seg_length
        chunk = 0
        end_chunk = duration

        max_gmm_list = []

        smoothed_most_likely = np.array([], dtype=np.float32)

        while end_chunk < len(most_likely):
            chunk_arr = most_likely[list(range(chunk, end_chunk))]
            max_gmm = stats.mode(chunk_arr)[0][0]
            max_gmm_list.append(max_gmm)
            smoothed_most_likely = np.append(smoothed_most_likely, max_gmm*np.ones(seg_length)) #changed ones from 250 to seg_length
            chunk += duration
            end_chunk += duration

        end_chunk -= duration
        if end_chunk < len(most_likely):
            chunk_arr = most_likely[list(range(end_chunk, len(most_likely)))]
            max_gmm = stats.mode(chunk_arr)[0][0]
            max_gmm_list.append(max_gmm)
            smoothed_most_likely = np.append(smoothed_most_likely,\
                                             max_gmm*np.ones(len(most_likely)-end_chunk))
        most_likely = smoothed_most_likely
        
        out_file = open(rttm_file_name, 'w')

        with_non_speech = -1*np.ones(self.total_num_frames)

        if sp_file_name:
            speech_seg = np.loadtxt(sp_file_name, delimiter=' ',usecols=(0,1))
            speech_seg_i = np.round(speech_seg).astype('int32')
#            speech_seg_i = np.round(speech_seg*100).astype('int32')
            sizes = np.diff(speech_seg_i)
        
            sizes = sizes.reshape(sizes.size)
            offsets = np.cumsum(sizes)
            offsets = np.hstack((0, offsets[0:-1]))

            offsets += np.array(list(range(len(offsets))))
        
        #populate the array with speech clusters
            speech_index = 0
            counter = 0
            for pair in speech_seg_i:
                st = pair[0]
                en = pair[1]
                speech_index = offsets[counter]
                
                counter+=1
                idx = 0
                for x in range(st+1, en+1):
                    with_non_speech[x] = most_likely[speech_index+idx]
                    idx += 1
        else:
            with_non_speech = most_likely
            
        cnum = with_non_speech[0]
        cst  = 0
        cen  = 0
        for i in range(1,self.total_num_frames): 
            if with_non_speech[i] != cnum: 
                if (cnum >= 0):
                    start_secs = ((cst)*0.01)
                    dur_secs = (cen - cst + 2)*0.01
#                    out_file.write("SPEAKER " + meeting_name + " 1 " +\
#                                   str(start_secs) + " "+ str(dur_secs) +\
#                                   " <NA> <NA> " + "speaker_" + str(cnum) + " <NA>\n")
                    out_file.write("SPEAKER " + meeting_name + " 1 " +\
                                   str(start_secs) + " "+ str(dur_secs) +\
                                   " speaker_" + str(cnum) + "\n")
                cst = i
                cen = i
                cnum = with_non_speech[i]
            else:
                cen+=1
                  
        if cst < cen:
            cnum = with_non_speech[self.total_num_frames-1]
            if(cnum >= 0):
                start_secs = ((cst+1)*0.01)
                dur_secs = (cen - cst + 1)*0.01
#                out_file.write("SPEAKER " + meeting_name + " 1 " +\
#                               str(start_secs) + " "+ str(dur_secs) +\
#                               " <NA> <NA> " + "speaker_" + str(cnum) + " <NA>\n")
                out_file.write("SPEAKER " + meeting_name + " 1 " +\
                               str(start_secs) + " "+ str(dur_secs) +\
                               " speaker_" + str(cnum) + "\n")

        print("DONE writing RTTM file")

    def write_to_GMM(self, gmmfile):
        gmm_f = open(gmmfile, 'w')

        gmm_f.write("Number of clusters: " + str(len(self.gmm_list)) + "\n")
             
        #print parameters
        cluster_count = 0
        for gmm in self.gmm_list:

            gmm_f.write("Cluster " + str(cluster_count) + "\n")
            means = gmm.components.means
            covars = gmm.components.covars
            weights = gmm.components.weights

            gmm_f.write("Number of Gaussians: "+ str(gmm.M) + "\n")

            gmm_count = 0
            for g in range(0, gmm.M):
                g_means = means[gmm_count]
                g_covar_full = covars[gmm_count]
                g_covar = np.diag(g_covar_full)
                g_weight = weights[gmm_count]

                gmm_f.write("Gaussian: " + str(gmm_count) + "\n")
                gmm_f.write("Weight: " + str(g_weight) + "\n")
                
                for f in range(0, gmm.D):
                    gmm_f.write("Feature " + str(f) + " Mean " + str(g_means[f]) +\
                                " Var " + str(g_covar[f]) + "\n")
                gmm_count+=1
                
            cluster_count+=1

        print("DONE writing GMM file")
        
    def new_gmm(self, M, cvtype):
        self.M = M
        self.gmm = GMM(self.M, self.D, cvtype=cvtype)

    def new_gmm_list(self, M, K, cvtype):
        self.M = M
        self.init_num_clusters = K
        self.gmm_list = [GMM(self.M, self.D, cvtype=cvtype) for i in range(K)]

    def segment_majority_vote(self, interval_size, em_iters):
        num_clusters = len(self.gmm_list)

        # Resegment data based on likelihood scoring
        likelihoods = self.gmm_list[0].score(self.X)
        for g in self.gmm_list[1:]:
            likelihoods = np.column_stack((likelihoods, g.score(self.X)))
        if num_clusters == 1:
            most_likely = np.zeros(len(self.X))
        else:
            most_likely = likelihoods.argmax(axis=1)

        # Across 2.5 secs of observations, vote on which cluster they should be associated with
        iter_training = {}
        
        for i in range(interval_size, self.N, interval_size):

            arr = np.array(most_likely[(list(range(i-interval_size, i)))])
            max_gmm = int(stats.mode(arr)[0][0])
            iter_training.setdefault((self.gmm_list[max_gmm],max_gmm),[]).append(self.X[i-interval_size:i,:])

        arr = np.array(most_likely[(list(range((int(self.N/interval_size))*interval_size, self.N)))])
        max_gmm = int(stats.mode(arr)[0][0])
        iter_training.setdefault((self.gmm_list[max_gmm], max_gmm),[]).\
                                  append(self.X[int(self.N/interval_size) *interval_size:self.N,:])
        
        iter_bic_dict = {}
        iter_bic_list = []

        # for each gmm, append all the segments and retrain
        for gp, data_list in iter_training.items():
            g = gp[0]
            p = gp[1]
            cluster_data =  data_list[0]

            for d in data_list[1:]:
                cluster_data = np.concatenate((cluster_data, d))

            g.train(cluster_data, max_em_iters=em_iters)

            iter_bic_list.append((g,cluster_data))
            iter_bic_dict[p] = cluster_data

        return iter_bic_dict, iter_bic_list, most_likely

    def cluster(self, em_iters, KL_ntop, NUM_SEG_LOOPS_INIT, NUM_SEG_LOOPS, seg_length):
        print(" ====================== CLUSTERING ====================== ")
        main_start = time.time()

        # ----------- Uniform Initialization -----------
        # Get the events, divide them into an initial k clusters and train each GMM on a cluster
        per_cluster = int(self.N/self.init_num_clusters)
        init_training = list(zip(self.gmm_list,np.vsplit(self.X, list(range(per_cluster, self.N, per_cluster)))))

        for g, x in init_training:
            g.train(x, max_em_iters=em_iters)

        # ----------- First majority vote segmentation loop ---------
        for segment_iter in range(0,NUM_SEG_LOOPS_INIT):
            iter_bic_dict, iter_bic_list, most_likely = self.segment_majority_vote(seg_length, em_iters)

        # ----------- Main Clustering Loop using BIC ------------

        # Perform hierarchical agglomeration based on BIC scores
        best_BIC_score = 1.0
        total_events = 0
        total_loops = 0
        while (best_BIC_score > 0 and len(self.gmm_list) > 1):

            total_loops+=1
            for segment_iter in range(0,NUM_SEG_LOOPS):
                iter_bic_dict, iter_bic_list, most_likely = self.segment_majority_vote(seg_length, em_iters)
                            
            # Score all pairs of GMMs using BIC
            best_merged_gmm = None
            best_BIC_score = 0.0
            merged_tuple = None
            merged_tuple_indices = None

            # ------- KL distance to compute best pairs to merge -------
            if KL_ntop > 0:
                top_K_gmm_pairs = self.gmm_list[0].find_top_KL_pairs(KL_ntop, self.gmm_list)
                for pair in top_K_gmm_pairs:
                    score = 0.0
                    gmm1idx = pair[0]
                    gmm2idx = pair[1]
                    g1 = self.gmm_list[gmm1idx]
                    g2 = self.gmm_list[gmm2idx]

                    if gmm1idx in iter_bic_dict and gmm2idx in iter_bic_dict:
                        d1 = iter_bic_dict[gmm1idx]
                        d2 = iter_bic_dict[gmm2idx]
                        data = np.concatenate((d1,d2))
                    elif gmm1idx in iter_bic_dict:
                        data = iter_bic_dict[gmm1idx]
                    elif gmm2idx in iter_bic_dict:
                        data = iter_bic_dict[gmm2idx]
                    else:
                        continue

                    new_gmm, score = compute_distance_BIC(g1, g2, data, em_iters)
                    
                    #print "Comparing BIC %d with %d: %f" % (gmm1idx, gmm2idx, score)
                    if score > best_BIC_score: 
                        best_merged_gmm = new_gmm
                        merged_tuple = (g1, g2)
                        merged_tuple_indices = (gmm1idx, gmm2idx)
                        best_BIC_score = score

            # ------- All-to-all comparison of gmms to merge -------
            else: 
                l = len(iter_bic_list)

                for gmm1idx in range(l):
                    for gmm2idx in range(gmm1idx+1, l):
                        score = 0.0
                        g1, d1 = iter_bic_list[gmm1idx]
                        g2, d2 = iter_bic_list[gmm2idx] 

                        data = np.concatenate((d1,d2))
                        new_gmm, score = compute_distance_BIC(g1, g2, data, em_iters)

                        #print "Comparing BIC %d with %d: %f" % (gmm1idx, gmm2idx, score)
                        if score > best_BIC_score: 
                            best_merged_gmm = new_gmm
                            merged_tuple = (g1, g2)
                            merged_tuple_indices = (gmm1idx, gmm2idx)
#                            print (best_BIC_score, score)
                            best_BIC_score = score

            # Merge the winning candidate pair if its deriable to do so
            if best_BIC_score > 0.0:
                gmms_with_events = []
                for gp in iter_bic_list:
                    gmms_with_events.append(gp[0])

                #cleanup the gmm_list - remove empty gmms
                for g in self.gmm_list:
                    if g not in gmms_with_events and g != merged_tuple[0] and g!= merged_tuple[1]:
                        #remove
                        self.gmm_list.remove(g)

                self.gmm_list.remove(merged_tuple[0])
                self.gmm_list.remove(merged_tuple[1])
                self.gmm_list.append(best_merged_gmm)
            
            print(" size of each cluster:", [ g.M for g in self.gmm_list])
            
        print("=== Total clustering time: %.2f min" %((time.time()-main_start)/60))
        print("=== Final size of each cluster:", [ g.M for g in self.gmm_list])
        ################### Added later to find likelihood ####################
        lkhoods = self.gmm_list[0].score(self.X)
        for g in self.gmm_list[1:]:
            lkhoods = np.column_stack((lkhoods, g.score(self.X)))
        if len(lkhoods.shape)==2:
            ml = lkhoods.argmax(axis=1)
        else:
            ml = np.zeros(len(self.X))                
        #######################################################################
        return most_likely,ml

def DER(outfile, AudioDataSet,annotationlist, audioLength):
    reference = Annotation()

    if not AudioDataSet=='DiaExample':
        treeA = ET.parse(annotationlist[0])
        rootA = treeA.getroot()
        for child in rootA.findall('segment'):
            start,end = float(child.get('transcriber_start')), float(child.get('transcriber_end'))
            reference[Segment(start, end)] = 'A'
    
        treeB = ET.parse(annotationlist[1])
        rootB = treeB.getroot()
        for child in rootB.findall('segment'):
            start,end = float(child.get('transcriber_start')), float(child.get('transcriber_end'))
            reference[Segment(start, end)] = 'B'
    
        treeC = ET.parse(annotationlist[2])
        rootC = treeC.getroot()
        for child in rootC.findall('segment'):
            start,end = float(child.get('transcriber_start')), float(child.get('transcriber_end'))
            reference[Segment(start, end)] = 'C'
    
        treeD = ET.parse(annotationlist[3])
        rootD = treeD.getroot()
        for child in rootD.findall('segment'):
            start,end = float(child.get('transcriber_start')), float(child.get('transcriber_end'))
            reference[Segment(start, end)] = 'D'
    else:
        reference = Annotation()
        reference[Segment(0.15, 3.41)] = 'A'
        reference[Segment(3.83, 5.82)] = 'A'
        reference[Segment(6.75, 11.10)] = 'B'
        reference[Segment(11.32, 15.8)] = 'C'
        reference[Segment(15.9, 18.8)] = 'B'
        reference[Segment(18.8, 27.8)] = 'C'
        reference[Segment(27.8, 34.4)] = 'B'
        reference[Segment(34.4, 42)] = 'D'

    hypothesis = Annotation()        
    f = open(outfile,'r')
    for line in f.readlines():
        start = float(line.split(' ')[3])
        end = start + float(line.split(' ')[4])
        annotation = line.split(' ')[5][0:-1]
        hypothesis[Segment(start, end)] = annotation
    f.close()
    metric = DiarizationErrorRate()
    metricPurity = DiarizationPurity()
    uem = Timeline([Segment(0, audioLength)])

    print('DER: %.2f %%' %(metric(reference, hypothesis, uem=uem)*100))
    print('Cluster Purity: %.2f %%' %(metricPurity(reference, hypothesis, uem=uem)*100))
    
    return metric, reference, hypothesis

def SADError(segments, AudioDataSet, annotationlist, audioLength):
    reference = Annotation()
    treeA = ET.parse(annotationlist[0])
    rootA = treeA.getroot()
    for child in rootA.findall('segment'):
        start,end = float(child.get('transcriber_start')), float(child.get('transcriber_end'))
        reference[Segment(start, end)] = 'A'

    treeB = ET.parse(annotationlist[1])
    rootB = treeB.getroot()
    for child in rootB.findall('segment'):
        start,end = float(child.get('transcriber_start')), float(child.get('transcriber_end'))
        reference[Segment(start, end)] = 'A'

    treeC = ET.parse(annotationlist[2])
    rootC = treeC.getroot()
    for child in rootC.findall('segment'):
        start,end = float(child.get('transcriber_start')), float(child.get('transcriber_end'))
        reference[Segment(start, end)] = 'A'

    treeD = ET.parse(annotationlist[3])
    rootD = treeD.getroot()
    for child in rootD.findall('segment'):
        start,end = float(child.get('transcriber_start')), float(child.get('transcriber_end'))
        reference[Segment(start, end)] = 'A'

    hypothesis = Annotation()
    for seg in segments:
        start = seg[0]
        end = seg[1]
        hypothesis[Segment(start, end)] = 'A'
    
    metric = DetectionErrorRate()
    uem = Timeline([Segment(0, audioLength)])
    print('SAD Error Rate: %.2f %%' %(metric(reference, hypothesis, uem=uem)*100))
    
    return metric, reference, hypothesis

def SpeechOnlySamplesOptimal(X,Fs,AudioDataSet, annotationlist):
    # This function makes non-speech (silence + noise) samples to zeros. 
    XSpeech = np.zeros(X.shape)
    treeA = ET.parse(annotationlist[0])
    rootA = treeA.getroot()
    for child in rootA.findall('segment'):
        start,end = float(child.get('transcriber_start')), float(child.get('transcriber_end'))
        XSpeech[int(np.round(start*Fs)):int(np.round(end*Fs))] = copy(X[int(np.round(start*Fs)):int(np.round(end*Fs))])

    treeB = ET.parse(annotationlist[1])
    rootB = treeB.getroot()
    for child in rootB.findall('segment'):
        start,end = float(child.get('transcriber_start')), float(child.get('transcriber_end'))
        XSpeech[int(np.round(start*Fs)):int(np.round(end*Fs))] = copy(X[int(np.round(start*Fs)):int(np.round(end*Fs))])

    treeC = ET.parse(annotationlist[2])
    rootC = treeC.getroot()
    for child in rootC.findall('segment'):
        start,end = float(child.get('transcriber_start')), float(child.get('transcriber_end'))
        XSpeech[int(np.round(start*Fs)):int(np.round(end*Fs))] = copy(X[int(np.round(start*Fs)):int(np.round(end*Fs))])

    treeD = ET.parse(annotationlist[3])
    rootD = treeD.getroot()
    for child in rootD.findall('segment'):
        start,end = float(child.get('transcriber_start')), float(child.get('transcriber_end'))
        XSpeech[int(np.round(start*Fs)):int(np.round(end*Fs))] = copy(X[int(np.round(start*Fs)):int(np.round(end*Fs))])
            
    return XSpeech

if __name__ == '__main__':
    '''
      For ExampleDiarization file use librosa, Weight=0.025.
      And segment of 50, best DER achieved 9.9 %.
    '''
    tic = time.time()
    stWin = 0.03
    stStep = 0.01
    M = 5 # no of GMM components
    K = 16 # no of clusters or GMMs
    n_mfcc = 19

    AudioDataSet = 'IS1008d' #DiaExample, IS1000a, IS1001a, IS1003a, IS1004a, IS1008a
    FlagFeatureNormalization = True
    UseSAD = True
    UseSparseFeatures = False
    spnp = None
    SpeechOnlyOptimal = True
    SparseFeatureEngineeringFlag = False
    
    if AudioDataSet=='DiaExample':
        fileName = '/home/rehan/Diarization/ReDiarization/data/diarizationExample.wav'
        outfile = '/home/rehan/Diarization/ReDiarization/data/diarizationExample.rttm'
        gmmfile = '/home/rehan/Diarization/ReDiarization/data/diarizationExample.gmm'
        if UseSAD: spnp = '/home/rehan/Diarization/ReDiarization/data/spnp.txt' 
        meeting_name = 'diarizationExample'
        annotationlist = None
    else:
        fileName = '/home/rehan/Diarization/ReDiarization/data/AMI/'+AudioDataSet+'/audio/'+AudioDataSet+'.Mix-Headset.wav'
        annotationA = '/home/rehan/Diarization/ReDiarization/data/AMI/'+AudioDataSet+'/audio/'+AudioDataSet+'.A.segments.xml'
        annotationB = '/home/rehan/Diarization/ReDiarization/data/AMI/'+AudioDataSet+'/audio/'+AudioDataSet+'.B.segments.xml'
        annotationC = '/home/rehan/Diarization/ReDiarization/data/AMI/'+AudioDataSet+'/audio/'+AudioDataSet+'.C.segments.xml'
        annotationD = '/home/rehan/Diarization/ReDiarization/data/AMI/'+AudioDataSet+'/audio/'+AudioDataSet+'.D.segments.xml'
        annotationlist = [annotationA, annotationB, annotationC, annotationD]
        outfile = '/home/rehan/Diarization/ReDiarization/data/AMI/'+AudioDataSet+'/audio/'+AudioDataSet+'.rttm'
        gmmfile = '/home/rehan/Diarization/ReDiarization/data/AMI/'+AudioDataSet+'/audio/'+AudioDataSet+'.gmm'
        if UseSAD: spnp = '/home/rehan/Diarization/ReDiarization/data/AMI/'+AudioDataSet+'/audio/'+AudioDataSet+'_spnp.txt' 
        meeting_name = AudioDataSet

    x, Fs = librosa.load(fileName, sr=16000)
    audioLength = len(x)/(Fs)
    if SpeechOnlyOptimal:
        x = SpeechOnlySamplesOptimal(x,Fs,AudioDataSet, annotationlist)
    
    S = librosa.feature.melspectrogram(y=x, sr=Fs, n_fft=int(Fs*stWin), hop_length=int(Fs*stStep))
    fVects = librosa.feature.mfcc(y=x, S=librosa.power_to_db(S), sr=Fs, n_mfcc = n_mfcc)

    if UseSAD:
        ###################### Speech Activity Detection ##########################
        segments, idx = silenceRemoval(x, Fs, stWin, stStep, smoothWindow=.0005, Weight=0.0001, plot=False)
        me,re,hy = SADError(segments, AudioDataSet, annotationlist, audioLength)
        ###########################################################################
        
        # Creating a speech/non-speech text File which contains speech only
        # features indices. 'idx' contains speech only features indices.
        st = idx[0]
        newst=copy(st)
        seglist = []
        for i in range(1,idx.size):
            if idx[i]==st+1:
                st+=1
            else:
                en = idx[i-1]
                seglist.append([newst,en])
                st = idx[i]
                newst = copy(st)
        en = idx[i]
        seglist.append([newst,en])
        segarray = np.array(seglist)
        np.savetxt(spnp, segarray, fmt='%d', delimiter=' ')
        #######################################################################
        # Take Speech only frames....
        fVectsSpeech = copy(fVects[:,idx])
        #######################################################################
    else:
        fVectsSpeech = fVects

    if FlagFeatureNormalization:
        ss = StandardScaler()
        fVectsSpeech = ss.fit_transform(fVectsSpeech.T).T
        print("Feature Normalization Done...")

    ###########################################################################
    diarizer = Diarizer(fVectsSpeech,fVects.shape[1])
    # Create the GMM list
    num_comps = M
    num_gmms = K
    diarizer.new_gmm_list(num_comps, num_gmms, 'diag')

    # Cluster
    kl_ntop = 0
    num_em_iters = 100
    num_seg_iters_init = 2 #2
    num_seg_iters = 3 #3
    seg_length = int(150)
    if AudioDataSet=='DiaExample': seg_length = 50
    
    most_likely,_ = diarizer.cluster(num_em_iters, kl_ntop, num_seg_iters_init, num_seg_iters, seg_length)
        
    # Write out RTTM and GMM parameter files
    diarizer.write_to_RTTM(outfile, spnp, meeting_name, most_likely, num_gmms, seg_length)
    metric, ref, hyp = DER(outfile, AudioDataSet,annotationlist, audioLength)
    #diarizer.write_to_GMM(gmmfile)
    print('=== Total Time Taken: %.2f min' %((time.time()-tic)/60.0))
