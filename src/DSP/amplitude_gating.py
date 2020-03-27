#!/usr/bin/env python
'''
Created on Feb 18, 2020

@author: paepcke

Given a .wav file, read it, and normalize it
so max voltage fills 32 bits. Then set all voltages that 
are less than -20dB of the maximum voltage to zero (customizable)

See header comment of method amplitude_gate() for details. 

For reading code detail:
Data structures for efficiently tracking bursts of non-zero voltages: 

   sample_npa       : a numpy array of voltages from the .wav file,
                      after normalization
                      All small amplitudes have been set to zero
    signal_index    : an array of pointers into the sample_npa. At
                      the pointed-to places in sample_npa the voltages
                      are non-zero.
    pt_into_index   : pointer into the signal_index
    
Example:
     sample_npa   : array([1,0,0,0,4,5,6,0,10])
     signal_index : array([0,4,5,6,8])
     pt_into_index: 4 points to the 8 in signal_index, and thus refers to
                    the 10V in the sample_npa    
'''

import argparse
import datetime
import math
import os
import sys

from scipy.io import wavfile
from scipy.signal import butter, lfilter, stft 

from elephant_utils.logging_service import LoggingService
import numpy as np
import numpy.ma as ma
from plotting.plotter import Plotter
from plotting.plotter import PlotterTasks

class FrequencyError(Exception):
    pass

class AmplitudeGater(object):
    '''
    classdocs
    '''
    #------------------------------------
    # Constructor 
    #-------------------    

    def __init__(self,
                 wav_file_path,
                 outfile=None,
                 amplitude_cutoff=-40,   # dB of peak
                 spectrogram_freq_cap=300, # Hz
                 normalize=True,
                 logfile=None,
                 framerate=None,  # Only used for testing.
                 spectrogram_outfile=None,
                 testing=False
                 ):
        '''

        During its work instances of this class may
        produce plots of results. By default those
        will not be plotted. To plot some or all,
        call add_task(plot_name) on the PlotterTasks class.
        Available plots are:
           o 

        @param wav_file_path: path to .wav file to be gated
            Can leave at None, if testing is True
        @type wav_file_path: str
        
        @param outfile: where gated, normalized .wav will be written.
        @type outfile: str
        
        @param amplitude_cutoff: dB attenuation from maximum
            amplitude below which voltage is set to zero
        @type amplitude_cutoff: int
        
        @param framerate: normally extracted from the .wav file.
            Can be set here for testing. Samples/sec
        @type framerate: int

        @param spectrogram_outfile: optionally a file to which a
            spectrogram of the entire noise-gated result is written.
            If None, no spectrogram is created.
        @type spectrogram_outfile: {None | str}

        @param logfile: file where to write logs; Default: stdout
        @type logfile: str

        @param logging_period: number of seconds between reporting
            envelope placement progress.
        @type logging_period: int
        
        @param testing: whether or not unittests are being run. If
            true, __init__() does not initiate any action, allowing
            the unittests to call individual methods.
        @type testing: bool
        '''

        # Make sure the outfile can be opened for writing,
        # before going into lengthy computations:
        
        if outfile is not None:
            try:
                with open(outfile, 'wb') as _fd:
                    pass
            except Exception as e:
                print(f"Outfile cannot be access for writing; doing nothing: {repr(e)}")
                sys.exit(1)

        AmplitudeGater.log = LoggingService(logfile=logfile)
        
        # For testing; usually framerate is read from .wav file:
        self.framerate = framerate

        if not testing:
            try:
                self.log.info("Reading .wav file...")        
                (self.framerate, samples) = wavfile.read(wav_file_path)
                self.log.info("Done reading .wav file.")        
            except Exception as e:
                print(f"Cannot read .wav file: {repr(e)}")
                sys.exit(1)

        self.plotter = Plotter(self.framerate)

        # Ensure that requested filter frequency is
        # less than the Nyquist frequency: framerate/2: 
        highest_filter_freq = min(math.floor(self.framerate / 2) - 1, spectrogram_freq_cap)
        if highest_filter_freq < spectrogram_freq_cap:
            raise FrequencyError(f"Cutoff frequency must be less than Nyquist freq (1/2 of sampling rate); max allowable is {highest_filter_freq}")

        if testing:
            self.recording_length_hhmmss = "<unknown>"
        else:
            num_samples = samples.size
            recording_length_secs = num_samples / self.framerate
            self.recording_length_hhmmss = str(datetime.timedelta(seconds = recording_length_secs))

        self.samples_per_msec = round(self.framerate/1000.)
        
        if testing:
            return

        samples_float = samples.astype(float)
        # Normalize:
        if normalize:
            normed_samples = self.normalize(samples_float)
        else:
            normed_samples = samples_float.copy()
         
        # Noise gate: Chop off anything with amplitude above amplitude_cutoff:
        gated_samples  = self.amplitude_gate(normed_samples, 
                                             amplitude_cutoff, 
                                             spectrogram_freq_cap=spectrogram_freq_cap,
                                             spectrogram_dest=spectrogram_outfile
                                             )
 
        # Result back to int16:
        gated_samples = gated_samples.astype(np.int16)
               
        if outfile is not None and not testing:
            # Write out the result:
            wavfile.write(outfile, self.framerate, gated_samples)
        
        if PlotterTasks.has_task('gated_wave_excerpt'):
            
            # Find a series of 100 array elements where at least
            # the first is not zero. Just to show an interesting
            # area, not a flat line. The nonzero() function returns
            # a *tuple* of indices where arr is not zero. Therefore
            # the two [0][0] to get the first non-zero:

            start_indx = self.find_busy_array_section(gated_samples)
            end_indx   = start_indx + 100
            
            self.log.info(f"Plotting a 100 long series of result from {start_indx}...")
            self.plotter.plot(np.arange(start_indx, end_indx),
                              gated_samples[start_indx:end_indx],
                              title=f"Amplitude-Gated {os.path.basename(wav_file_path)}",
                              xlabel='Sample Index', 
                              ylabel='Voltage'
                              )
        
        print('Done')
        
        
    #------------------------------------
    # amplitude_gate
    #-------------------    
        
    def amplitude_gate(self, 
                       sample_npa, 
                       threshold_db,
                       order=4, 
                       cutoff_freq=100,
                       spectrogram_dest=None,
                       spectrogram_freq_cap=300, # Hz 
                       ):
        '''
        Given an array of raw audio samples, 
        generate a noise-gated array of the same length.
        Optionally, create a full spectrogram into a 
        .npy file. 
        Optionally, plot 30-second spectrograms from 
        18 subsections of the gated samples.
        
        Procedure:
           o Normalize audio to fill 32 bits.
           o Create a temporary 'envelope' signal over
             the samples. That is, a slow, lazy outline
             of the fast audio signal. The cutoff_freq
             controls this low-pass filter's limit on
             higher frequencies. The order is the number
             of filter stages that make up the low-pass
             (Butterworth) filter. Usually, 4 seems fine. 
           o On the envelope, find all samples that are
             threshold-db below the maximum peak of the
             envelope. The value must be negative. Experimentally,
             at most -20(dB).
           o At these very low-voltage times, set the original
             audio to zero. This takes signal areas that
             are clearly too low to be significant out of the
             picture, removing some noise. The result is the
             noise-gated signal, which will be returned.
             
           o Optionally: if spectrogram_dest is a file path
                destination, create a spectrogram over the full
                duration, and save it to that path as a numpy array.
                All frequencies above spectrogram_freq_cap are
                removed from the spectrogram before saving.
                
           o Optionally: plot 18 30-sec spectrograms from
                times evenly spaced across the total recording.
                Times and freqs in those plots correspond to
                the true times in the recording.   
             
        
        @param sample_npa: raw audio
        @type sample_npa: np.array(int)
        @param threshold_db: voltage below which signal is set to zero;
            specified as dB below peak voltage: db FS.
        @type threshold_db: negative int
        @param order: polynomial of Butterworth filter
        @type order: int
        @param cutoff_freq: frequency in Hz for the envelope
        @type cutoff_freq: int
        @param spectrogram_dest: optionally: file name where 
            spectrogram is stored
        @type spectrogram_dest: str
        @param spectrogram_freq_cap: optionally: frequency above 
            which all frequencies are removed from spectrogram.
        @type spectrogram_freq_cap: int
        '''

        # Don't want to open the gate *during* a burst.
        # So make a low-pass filter that only roughly envelops

        self.log.info("Taking abs val of values...")
        samples_abs = np.abs(sample_npa)
        self.log.info("Done taking abs val of values.")

        self.log.info(f"Applying low pass filter (cutoff {cutoff_freq})...")
        envelope = self.butter_lowpass_filter(samples_abs, cutoff_freq, order)
        self.log.info("Done applying low pass filter.")        

        if PlotterTasks.has_task('samples_plus_envelope'):
            self.plotter.over_plot(samples_abs[1000:1100], 'ABS(samples)')
            self.plotter.over_plot(envelope[1000:1100], f"Env Order {order}")
         
            #order = 5
            #envOrd3 = self.butter_lowpass_filter(samples_abs, cutoff_freq, order)
            #self.over_plot(envOrd3[1000:1100], f'Order {order}')
     
            #order = 6
            #envOrd1 = self.butter_lowpass_filter(samples_abs, cutoff_freq, order)
            #self.over_plot(envOrd1[1000:1100], f'Order {order}')

        # Compute the threshold below which we
        # set amplitude to 0. It's threshold_db of max
        # value. Note that for a normalized array
        # that max val == 1.0

        max_voltage = np.amax(envelope)
        self.log.info(f"Max voltage: {max_voltage}")
        
        # Compute threshold_db of max voltage:
        Vthresh = max_voltage * 10**(threshold_db/20)
        self.log.info(f"Cutoff threshold amplitude: {Vthresh}")

        # Zero out all amplitudes below threshold:
        self.log.info("Zeroing sub-threshold values...")

        mask_for_where_non_zero = 1 * np.ma.masked_greater(envelope, Vthresh).mask
        gated_samples = sample_npa * mask_for_where_non_zero
        
        zeroed_percentage = 100 * gated_samples[gated_samples==0].size / gated_samples.size
        self.log.info(f"Zeroed {zeroed_percentage:.2f}% of signal.")
        
        if spectrogram_dest:
            
            # Get a combined frequency x time matrix. The matrix values will
            # be complex: 
            (freq_labels, time_labels, complex_freq_time) = self.make_spectrogram(gated_samples)
            # Keep only the complex values:
            self.log.info("Getting magnitudes of complex frequency values...")  
            freq_time = np.absolute(complex_freq_time)
            self.log.info("Done getting magnitudes of complex frequency values.")
            
            if spectrogram_freq_cap is not None:
                self.log.info(f"Removing frequencies above {spectrogram_freq_cap}Hz...")
                # Remove all frequencies above, and including
                # spectrogram_freq_cap:
                (new_freq_labels, capped_spectrogram) = self.filter_spectrogram(freq_labels,
                                                                                freq_time, 
                                                                                [(None, spectrogram_freq_cap)]
                                                                                )
                self.log.info(f"Done removing frequencies above {spectrogram_freq_cap}Hz.")
            else:
                capped_spectrogram = freq_time
                new_freq_labels    = freq_labels
        
            # Save the spectrogram to file:
            self.log.info(f"Saving spectrogram to {spectrogram_dest}...")
            np.save(spectrogram_dest, capped_spectrogram)
            self.log.info(f"Done saving spectrogram to {spectrogram_dest}.")
        
        if spectrogram_dest and PlotterTasks.has_task('spectrogram_excerpts'):
            # The matrix is large, and plotting takes forever,
            # so define a matrix excerpt:
            self.plotter.plot_spectrogram(new_freq_labels, 
                                          time_labels,
                                          capped_spectrogram)

        return gated_samples

    #------------------------------------
    # filter_spectrogram
    #-------------------
    
    def filter_spectrogram(self, 
                           freq_labels, 
                           freq_time, 
                           freq_bands):
        '''
        Given a spectrogram, return a new spectrogram
        with only frequencies within given bands retained.
        
        freq_time is a matrix whose rows each contain energy
        contributions by one frequency over time. 
        
        The freq_labels is an np.array with the frequency of
        each row. I.e. the y-axis labels.
        
        freq_bands is an array of frequency intervals. The
        following would only retain rows for frequencies 
             10 <= f < 20,
              0 <= f < 5,  
         and  f >= 40:
        
           [(None, 5), (10,20), (40,None)]
           
        So: note that these extracts are logical OR.
            Contributions from each of these three
            intervals will be present, even though the 
            (10,20) would squeeze out the last due to its
            upper bound of 20.
         
        @param freq_labels: array of frequencies highest first
        @type freq_labels: np.array[float]
        @param freq_time: 2d array of energy contributions
        @type freq_time: np.array(rows x cols) {float || int || complex}
        @param freq_bands: bands of frequencies to retain.
        @type freq_bands: [({float | int})]
        @return revised spectrogram, and correspondingly reduced
            frequency labels
        @rtype: (np_array(1), np_array(n,m))
        '''
        # Prepare a new spectrogram matrix with
        # the same num of cols as the one passed
        # in, but no rows:
        
        (_num_rows, num_cols) = freq_time.shape
        new_freq_time    = np.empty((0,num_cols))
        
        # Same for the list of frequencies:
        new_freq_labels  = np.empty((0,))
        
        for (min_freq, out_freq) in freq_bands:
            if min_freq is None and out_freq is None:
                # Degenerate case: keep all:
                continue
            if min_freq is None:
                min_freq = 0
            if out_freq is None:
                # No upper bound, so make a ceiling
                # higher than maximum frequency:
                out_freq = np.amax(freq_labels) + 1.
                
            # Get the indices of the frequency array 
            # where the frequency is within this interval.
            # The np.where returns a tuple, therefore [0]

            filter_indices =  np.where(np.logical_and(freq_labels >= min_freq,
                                                      freq_labels < out_freq
                                                      ))[0]
        
            # Keep only rows (axis=0) that contain the energies for
            # included frequencies:
            new_freq_time = np.vstack(
                (new_freq_time, np.take(freq_time, filter_indices, axis=0))
                )

            # Also take away the row labels that where excluded:
            new_freq_labels = np.hstack(
                (new_freq_labels, np.take(freq_labels, filter_indices))
                )

        return (new_freq_labels, new_freq_time)
        

    #------------------------------------
    # butter_lowpass_filter
    #-------------------    

    def butter_lowpass_filter(self, data, cutoff, order=5):
        b, a = self.get_butter_lowpass_parms(cutoff, order=order)
        envelope = lfilter(b, a, data)
        
        if PlotterTasks.has_task('low_pass_filter'):
            self.plotter.plot_frequency_response(b, a, cutoff, order)
            # Plot a piece of envelope, roughly from the middle:
            mid_env_index = round(envelope.size/2)
            end_index     = mid_env_index + 100
            self.plotter.plot(np.arange(mid_env_index, end_index),
                              envelope[mid_env_index:end_index],
                              f"Envelope {mid_env_index} to {end_index}",
                              "Time",
                              "Amplitude"
                              )
        
        return envelope

    #------------------------------------
    # get_butter_lowpass_parms
    #-------------------    

    def get_butter_lowpass_parms(self, cutoff, order=5):
        nyq = 0.5 * self.framerate
        normal_cutoff = cutoff / nyq
        b, a = butter(order, normal_cutoff, btype='low', analog=False)
        return b, a

    #------------------------------------
    # suppress_small_voltages
    #-------------------
    
    def suppress_small_voltages(self, volt_vec, thresh_volt, padding_secs):
        '''
        Given an array of numbers, set all elements smaller than
        thres_volt to zero. But: leave padding array elements before
        and after each block of new zeroes alone.
        
        Return the resulting array of same length as volt_vec.
        
        Strategy: 
           o say volt_vec == array([1, 2, 3, 4, 5, 6, 7, 8, 0, 1])
                 thres_volt == 5
                 padding == 2    # samples

           o to not worry about out of bound index, add padding zeros
             to the voltage vector:
             
                 padded_volt_vec = np.hstack((volt_vec, np.zeros(2).astype(int))) 
                     ==> array([1, 2, 3, 4, 5, 6, 7, 8, 0, 1, 0, 0])
                     
           o create an array of indexes that need to be set to 0,
             because voltages at their location exceed thres_volt.
             The np.nonzero returns a one-tuple, therefore the [0]
             
                 indexes_to_zero = np.nonzero(a>5)[0]
                     ==> (array([5, 6, 7]),)

           o we need to respect the padding ahead of the elements 
             to zero. So add padding samples to each index:
             
                 indexes_to_zero = indexes_to_zero + 2

           o 
                 
        @param volt_vec:
        @type volt_vec:
        @param thresh_volt:
        @type thresh_volt:
        @param padding_secs:
        @type padding_secs:
        '''
        
        padding = self.samples_from_secs(padding_secs)

        # Get a mask with True where we will zero out the voltage:
        volt_mask = volt_vec < thresh_volt
        
        pt_next_mask_pos = 0
        while True:
            (volt_mask, pt_next_mask_pos) = self.narrow_mask_segment(volt_mask,
                                                                    pt_next_mask_pos, 
                                                                    padding
                                                                    )
            if pt_next_mask_pos is None:
                # Got a finished mask with padding.
                break

        # Do the zeroing
        volt_vec_zeroed = ma.masked_array(volt_vec,
                                          volt_mask
                                          ).filled(0)
        return volt_vec_zeroed
    
    #------------------------------------
    # narrow_mask_segment
    #------------------- 
    
    def narrow_mask_segment(self, mask, ptr_into_mask, padding):
        
        # Erroneous args or end of mask:
        mask_len = mask.size
        if ptr_into_mask >= mask_len:
            # None ptr to indicate end:
            return (mask, None)
        
        zeros_start_ptr = ptr_into_mask
        
        # Find next Truth value in mask, i.e.
        # the start of a zeroing sequence
        while zeros_start_ptr < mask_len and not mask[zeros_start_ptr]:
            zeros_start_ptr += 1
            
        # Pointing to the first True (first zeroing index)
        # after a series of False, or end of mask:
        if zeros_start_ptr >= mask_len:
            return (mask, None)
        
        # Find end of the zeroing sequence (i.e. True vals in mask):
        zeros_end_ptr = zeros_start_ptr
        while zeros_end_ptr < mask_len and mask[zeros_end_ptr]:
            zeros_end_ptr += 1

        # Is the zeroing sequence long enough to accommodate
        # padding to its left?
        zeros_len = zeros_end_ptr - zeros_start_ptr
        
        if zeros_len < padding:
            # Just don't zero at all for this seq:
            mask[zeros_start_ptr:zeros_end_ptr] = False
        else:
            # Don't zero padding samples:
            mask[zeros_start_ptr : min(zeros_start_ptr + padding, mask_len)] = False    
        
        # New start of zeroing seq: in steady state
        # it's just the start pt moved right by the amount
        # of padding. But the burst of zeroing was too narrow,
        # 
        zeros_start_ptr = min(zeros_start_ptr + padding,
                              zeros_end_ptr
                              )
         
        # Same at the end: Stop zeroing a bit earlier than
        # where the last below-threshold element sits:
        
        zeros_len = zeros_end_ptr - zeros_start_ptr
        if zeros_len <= padding:
            # Just don't do any zeroing:
            mask[zeros_start_ptr : zeros_end_ptr] = False
        else:
            # Just stop zeroing a bit earlier
            mask[zeros_end_ptr - padding : zeros_end_ptr] = False    
            zeros_end_ptr = zeros_end_ptr - padding

        return (mask, zeros_end_ptr)

    #------------------------------------
    # normalize
    #-------------------
    
    def normalize(self, samples):
        '''
        Make audio occupy the maximum dynamic range
        of int16: -2**15 to 2**15 - 1 (-32768 to 32767)
        
        Formula to compute new Intensity of each sample:

           I = ((I-Min) * (newMax - newMin)/Max-Min)) + newMin

        @param samples: samples from .wav file
        @type samples: np.narray('int16')
        @result: a new np array with normalized values
        @rtype: np.narray('int16')
        '''
        new_min = -2**15       # + 10  # Leave a little bit of room with min val of -32768
        new_max = 2**15        # - 10   # same for max:
        min_val = np.amin(samples)
        max_val = np.amax(samples)
        
        self.log.info("Begin normalization...")
        
        normed_samples = ((samples - min_val) * (new_max - new_min)/(max_val - min_val)) + new_min
        
        # Or, using scikit-learn:
        #   normed_samples = preprocessing.minmax_scale(samples, feature_range=[new_min, new_max])

        self.log.info("Done normalization.")
        return normed_samples    

    #------------------------------------
    # make_sinewave
    #-------------------    
        
    def make_sinewave(self, freq):
        time = np.arange(0,freq,0.1)
        amplitude = np.sin(time)
        return (time, amplitude)
    
    #------------------------------------
    # db_from_sample
    #-------------------    
    
    def db_from_sample(self, sample):
        return 20 * np.log10(sample)
    
    #------------------------------------
    # samples_from_msecs
    #-------------------
    
    def samples_from_msecs(self, msecs):
        
        return msecs * self.samples_per_msec
    
    #------------------------------------
    # samples_from_secs
    #-------------------
    
    def samples_from_secs(self, secs):
        '''
        Possibly fractional seconds turned into
        samples. Fractional seconds are rounded up.
         
        @param secs: number of seconds to convert
        @type secs: {int | float}
        @return: number of corresponding samples
        @rtype: int
        '''
        
        return math.ceil(secs * self.framerate)
    
    #------------------------------------
    # msecs_from_samples 
    #-------------------
    
    def msecs_from_samples(self, num_samples):
        
        return num_samples * self.samples_per_msec
    
    
    #------------------------------------
    # get_max_db
    #------------------

    def get_max_db(self, npa):
        
        max_val = npa.amax()
        max_db  = 20 * np.log10(max_val)
        return max_db

    #------------------------------------
    # export_snippet
    #-------------------    

    def export_snippet(self, samples, start_sample, end_sample, filename, to_int16=True):
        '''
        Write part of the samples to a two-col CSV.
        
        @param samples: sample array
        @type samples: np.array
        @param start_sample: index of first sample to export
        @type start_sample: int
        @param end_sample: index of sample after the last one exported
        @type end_sample: int
        @param filename: output file name
        @type filename: str
        @param to_int16: whether or not to convert samples to 16 bit signed int before writing
        @type to_int16: bool
        '''
        
        snippet = samples[start_sample : end_sample]
        if to_int16:
            snippet = snippet.astype(np.int16)
        with open(filename, 'w') as fd:
            for (indx, val) in enumerate(snippet):
                fd.write(f"{indx},{val}\n")
        
    #------------------------------------
    # make_spectrogram
    #-------------------

    def make_spectrogram(self, data):
        '''
        Given data, compute a spectrogram.

        Assumptions:
            o self.framerate contains the data framerate
    
        o The (Hanning) window overlap used (Hanning === Hann === Half-cosine)
        o Length of each FFT segment: 4096 (2**12)
        o Number of points to overlap with each window
             slide: 1/2 the segments size: 2048
        o Amount of zero-padding at the end of each segment:
             the length of the segment again, i.e. doubling the window
             so that the conversion to positive-only frequencies makes
             the correct lengths
             
        Returns a three-tuple: an array of sample frequencies,
            An array of segment times. And a 2D array of the SFTP:
            frequencies x segment times
        
        @param data: the time/amplitude data
        @type data: np.array([float])
        @return: (frequency_labels, time_labels, spectrogram_matrix)
        @rtype: (np.array, np.array, np.array)
        
        '''
        
        fft_width = 2**12  # 4096
        self.log.info("Creating spectrogram...")
        (freq_labels, time_labels, complex_freq_by_time) = stft(data, self.framerate, nperseg=fft_width)
        self.log.info("Done creating spectrogram.")
                
        return (freq_labels, time_labels, complex_freq_by_time)
        

    #------------------------------------
    # find_busy_array_section
    #-------------------    

    def find_busy_array_section(self, arr):
        
        non_zeros = np.nonzero(arr)[0]
        for indx_to_non_zero in non_zeros:
            if arr[indx_to_non_zero] > 0 and\
                arr[indx_to_non_zero + 1] > 0 and\
                arr[indx_to_non_zero + 2] > 0:
                return indx_to_non_zero
            
        # Nothing found, return start of array:
        return 0

        
# --------------------------- Burst -----------------------

class Burst(object):

    def __init__(self):
        '''
        
        @param start:
        @type start:
        @param stop:
        @type stop:
        @param attack_start:
        @type attack_start:
        @param release_start:
        @type release_start:
        @param: averaged_value:
        @type: averaged_value:
        @param averaged_value:
        @type averaged_value:
        '''
        self._start           = None
        self._stop            = None
        self._padding_start    = None
        self._release_start   = None
        self._averaging_start = None
        self._averaging_stop  = None
        self.signal_index_pt  = None

    @property
    def start(self):
        return self._start
    @start.setter
    def start(self, val):
        self._start = val

    @property
    def stop(self):
        return self._stop
    @stop.setter
    def stop(self, val):
        self._stop = val
        
    @property
    def attack_start(self):
        return self._padding_start
    
    @attack_start.setter
    def attack_start(self, val):
        self._padding_start = val

    @property
    def release_start(self):
        return self._release_start
    @release_start.setter
    def release_start(self, val):
        self._release_start = val

    @property
    def averaging_start(self):
        return self._averaging_start
    @averaging_start.setter
    def averaging_start(self, val):
        self._averaging_start = val


    @property
    def averaging_stop(self):
        return self._averaging_stop
    @averaging_stop.setter
    def averaging_stop(self, val):
        self._averaging_stop = val

    @property
    def signal_index_pt(self):
        return self._signal_index_pt
    @signal_index_pt.setter
    def signal_index_pt(self, val):
        self._signal_index_pt = val


# --------------------------- Main -----------------------

if __name__ == '__main__':
    
    parser = argparse.ArgumentParser(prog=os.path.basename(sys.argv[0]),
                                     formatter_class=argparse.RawTextHelpFormatter,
                                     description="Apply amplitude filter to a given .wav file"
                                     )

    parser.add_argument('-l', '--logfile',
                        help='fully qualified log file name to which info and error messages \n' +\
                             'are directed. Default: stdout.',
                        dest='logfile',
                        default=None);

    parser.add_argument('-c', '--cutoff',
                        help='dB attenuation from max amplitude below which signal \n' +\
                            'is set to zero; default: -40dB',
                        type=int,
                        default='-40'
                        )
    
    parser.add_argument('-f', '--filter',
                        help='highest frequency to keep in spectrogram.',
                        type=int,
                        default=300);
    
    parser.add_argument('-p', '--padding',
                        help='seconds to keep before/after events; default: 5',
                        type=int,
                        default=5);
               
    parser.add_argument('-r', '--raw',
                        action='store_true',
                        default=False,
                        help="Set to prevent amplitudes to be  normalized to range from -32k to 32k; default is to normalize"
                        )
                        
    parser.add_argument('--plot',
                        nargs='+',
                        action='extend',
                        choices=['gated_wave_excerpt','samples_plus_envelope','spectrogram_excerpts','low_pass_filter'],
                        help="Plots to produce; repeatable; default: no plots"
                        )

    parser.add_argument('wavefile',
                        help="Input .wav file"
                        )
    parser.add_argument('outfile',
                        help="Path to where result .wav file will be written; if None, nothing other than plotting is output",
                        default=None
                        )
    
    args = parser.parse_args();

    cutoff = args.cutoff
    if cutoff >= 0:
        print(f"Amplitude cutoff must be negative, not {cutoff}")
        sys.exit(1)

    # Register the plots to produce:
    for plot_name in args.plot:
        PlotterTasks.add_task(plot_name)
    
    # AmplitudeGater('/Users/paepcke/tmp/nn01c_20180311_000000.wav',
    #                plot_result=True)
    AmplitudeGater(args.wavefile,
                   args.outfile,
                   amplitude_cutoff=cutoff,
                   spectrogram_freq_cap=args.filter,
                   normalize=not args.raw,
                   plot_result=args.plot,
                   logfile=args.logfile,
                   )

    sys.exit(0)
