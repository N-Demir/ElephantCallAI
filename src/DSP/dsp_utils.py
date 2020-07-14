'''
Created on Apr 5, 2020

@author: paepcke
'''

from collections import OrderedDict
from enum import Enum
import os
import re

import torch
from torchaudio import transforms

import numpy as np
import pandas as pd


class PrecRecFileTypes(Enum):
    SPECTROGRAM  = '_spectrogram'
    TIME_LABELS  = '_time_labels'
    FREQ_LABELS  = '_freq_labels'
    GATED_WAV    = '_gated'
    PREC_REC_RES = '_prec_rec_res'
    EXPERIMENT   = '_experiment'
    PICKLE       = '_pickle'
        
class DSPUtils(object):
    '''
    classdocs
    '''

    #------------------------------------
    # prec_recall_file_name
    #-------------------

    @classmethod
    def prec_recall_file_name(cls, 
                              root_info, 
                              file_type,
                              experiment_id=None):
        '''
        Given root info like one of:
          o filtered_wav_-50dB_10Hz_50Hz_20200404_192128.npy
          o filtered_wav_-50dB_10Hz_50Hz_20200404_192128
          
        return a new name with identifying info after the
        basename:
        
          o filtered_wav_-50dB_10Hz_50Hz_20200404_192128_spectrogram.npy
          o filtered_wav_-50dB_10Hz_50Hz_20200404_192128_time_labels.npy
          o filtered_wav_-50dB_10Hz_50Hz_20200404_192128_freq_labels.npy
          o filtered_wav_-50dB_10Hz_50Hz_20200404_192128_gated.wav
        
        The experiment_id argument is for type PICKLE. Such files
        hold a single experiment object in pickle form:
        
         o filtered_wav_-50dB_10Hz_50Hz_20200404_192128_exp<experiment_id>.pickle
         
        If generated filename already exists, adds a counter before 
        the dot: 
        
          filtered_wav_-50dB_10Hz_50Hz_20200404_192128_exp<experiment_id>_<n>.pickle
        
        @param root_info: example file name
        @type root_info: str
        @param file_type: one of the PrecRecFileTypes
        @type file_type: PrecRecFileTypes
        '''
        (path_no_ext, ext) = os.path.splitext(root_info)
        if file_type in [PrecRecFileTypes.FREQ_LABELS,
                         PrecRecFileTypes.TIME_LABELS]:
            ext = '.npy'
        elif file_type in [PrecRecFileTypes.SPECTROGRAM]:
            ext = '.pickle'
        elif file_type in [PrecRecFileTypes.GATED_WAV]:
            ext = '.wav'
        elif file_type in [PrecRecFileTypes.PREC_REC_RES,
                           PrecRecFileTypes.EXPERIMENT]:
            ext = '.tsv'
        elif file_type == PrecRecFileTypes.PICKLE:
            ext = f"{experiment_id}.pickle"
        
        new_file_path = f"{path_no_ext}{file_type.value}{ext}"
        counter = 0
        
        # Find a file name that does not already exists,
        # guarding against race conditions. The 'x' mode
        # atomically opens a file for writing, but only if 
        # it does not exist. If it does, a FileExistsError
        # is generated:
        
        while True:
            try:
                with open(new_file_path, 'x') as _fd: 
                    return new_file_path
            except FileExistsError:
                counter += 1
                new_file_path = f"{path_no_ext}{file_type.value}_{counter}{ext}"

    #------------------------------------
    # save_spectrogram 
    #-------------------
    
    @classmethod
    def save_spectrogram(cls, 
                         spectrogram, 
                         spectrogram_dest,
                         freq_labels,
                         time_labels
                         ):
        '''
        Given spectrogram magnitudes, frequency
        and time axes labels, save as a pickled
        dataframe
        
        @param spectrogram: 2d array of magnitudes
        @type spectrogram: np.array
        @param spectrogram_dest: file name to save to
        @type spectrogram_dest: str
        @param freq_labels: array of y-axis labels
        @type freq_labels: np_array
        @param time_labels: array of x-axis labels
        @type time_labels: np_array
        '''
        # Save the spectrogram to file.
        # Combine spectrogram, freq_labels, and time_labels
        # into a DataFrame:
        df = pd.DataFrame(spectrogram,
                          columns=time_labels,
                          index=freq_labels
                          )
        df.to_pickle(spectrogram_dest)

    #------------------------------------
    # load_spectrogram
    #-------------------
    
    @classmethod
    def load_spectrogram(cls, df_filename):
        '''
        Given the path to a pickled dataframe
        that holds a spectrogram, return the
        dataframe. The df will have the index
        (i.e. row labels) set to the frequencies,
        and the column names to the time labels.
        
        @param df_filename: location of the pickled df
        @type df_filename: str
        @return: spectrogram DataFrame: columns are 
            times in seconds, index are frequency bands
        @rtype pandas.DataFrame
        @raise FileNotFoundError: when pickle file not found
        @raise pickle.UnpicklingError
        '''

        # Safely read the pickled DataFrame
        df = pd.read_pickle(df_filename)
        return df

        #return({'spectrogram' : df.values,
        #        'freq_labels' : df.index,
        #        'time_labels' : df.columns
        #        })

    #------------------------------------
    # spectrogram_to_db 
    #-------------------
    
    @classmethod
    def spectrogram_to_db(cls, spect_magnitude):
        '''
        Takes a numpy spectrogram  of magnitudes.
        Returns a numpy spectrogram containing 
        dB scaled power.
        
        @param spect_magnitude:
        @type spect_magnitude:
        '''
        transformer = transforms.AmplitudeToDB('power')
        spect_tensor = torch.Tensor(spect_magnitude)
        spect_dB_tensor = transformer.forward(spect_tensor)
        spect_dB = spect_dB_tensor.numpy()
        return spect_dB

    #------------------------------------
    # get_spectrogram__from_treatment
    #-------------------
    
    @classmethod
    def get_spectrogram__from_treatment(cls, threshold_db, cutoff_freq, src_dir='/tmp'):
        '''
        Given a list of treatments, construct the file names
        that are created by the calibrate_preprossing.py facility.
        Load them all, and return them.
        
        @param threshold_db: dB below which all values were set to zero
        @type threshold_db: int
        @param cutoff_freq: spectrogram cutoff frequency
        @type cutoff_freq: int
        @param src_dir: directory where all the files 
            are located.
        @type src_dir: src
        @return:  {'spectrogram' : magnitudes,
                   'freq_labels' : y-axis labels,
                   'time_labels' : x-axis labels
                  }

        '''

        files = os.listdir(src_dir)
        spec_pat = re.compile(f'filtered_wav_{str(threshold_db)}dB_{str(cutoff_freq)}Hz.*spectrogram.pickle')
        try:
            spect_file = next(filter(spec_pat.match, files))
            spect_path = os.path.join(src_dir, spect_file)
        except StopIteration:
            raise IOError("Spectrogram file not found.")

        # Safely read the pickled DataFrame
        df = eval(pd.read_pickle(spect_path),
                   {"__builtins__":None},    # No built-ins at all
                   {}                        # No additional func
                   )

        return({'spectrogram' : df.values,
                'freq_labels' : df.index,
                'time_labels' : df.columns
                })

# ---------------------------- Class SignalTreatment ------------
    
class SignalTreatmentDescriptor(object):
    '''
    Hold information on how an original audio signal 
    was transformed to a noise gated file. And how 
    subsequent precision/recall calculations were done
    in different ways.
    
    Instances manage a signal treatment descriptor. These
    are part of both Experiment and PerformanceResult instances.
    They are used to match them reliably. Typically a
    descriptor is first created when a noise-gated signal file
    is created. Later, the minimum required overlap is added.
    It comes into play after the gated file is created.
    
    '''
    
    props = OrderedDict({'threshold_db' : int,
                         'low_freq'  : int,
                         'high_freq'  : int,
                         'min_required_overlap' : int
                         })

    #------------------------------------
    # Constructor 
    #-------------------

    def __init__(self, threshold_db, low_freq, high_freq, min_required_overlap=None):
        '''
        
        @param threshold_db: signal strength below which signal
            is set to 0.
        @type threshold_db: int
        @param low_freq: lowest frequency accepted by front end bandpass filter
        @type low_freq: int
        @param high_freq: highest frequency accepted by front end bandpass filter
        @type high_freq: int
        @param min_required_overlap: percentage of overlap minimally
            required for a burst to count as discovered.
        @type min_required_overlap: float
        '''
        
        try:
            self.threshold_db = int(threshold_db)
        except (ValueError, TypeError):
            raise ValueError("Threshold dB must be int, or str convertible to int")
        
        try:
            self.low_freq = int(low_freq)
        except (ValueError, TypeError):
            raise ValueError("Bandpass freqs must be int, or str convertible to int")

        try:
            self.high_freq = int(high_freq)
        except (ValueError, TypeError):
            raise ValueError("Bandpass freqs must be int, or str convertible to int")
        
        if min_required_overlap in (None, 'none', 'None', 'noneperc'):
            self.min_required_overlap = None
        else:
            try:
                self.min_required_overlap = int(min_required_overlap)
            except (ValueError, TypeError):
                raise ValueError("Minimum required overlap must be int, or str convertible to int")

    #------------------------------------
    # from_str
    #-------------------

    @classmethod
    def from_str(cls, stringified_instance):
        '''
        Reverse of what __str__() produces:
          "SignalTreatmentDescriptor(-30,10,50,20)" ==> an instance
          
        Alternatively, the method will also deal with 
        a flat string: "-20dB_10Hz_5Hz_10perc".
        
        @param cls:
        @type cls:
        @param stringified_instance: Stringified instance: either a
            string that can be evaled, or a flattened string.
        @type stringified_instance: str
        '''
        if not stringified_instance.startswith(cls.__name__):
            return cls.from_flat_str(stringified_instance)
        
        # Safe eval by creating a near-empty environment:
        try:
            inst = eval(stringified_instance,
                        {'__builtins__' : None},
                        {'SignalTreatmentDescriptor' : SignalTreatmentDescriptor}
                        )
        except Exception:
            raise ValueError(f"Expression '{stringified_instance}' does not evaluate to an instance of SignalTreatmentDescriptor")
        return inst

    #------------------------------------
    # from_flat_str
    #-------------------

    @classmethod
    def from_flat_str(cls, str_repr):
        '''
        Assume passed-in string is like "-30dB_10Hz_50Hz_10perc",
        or "-30dB_10Hz_50Hz_Noneperc". Create an instance from
        that info.
        
        @param str_repr:
        @type str_repr:
        '''
        # Already an instance?
        
        (threshold_db_str, 
         low_freq_str,
         high_freq_str, 
         min_overlap_str) = str_repr.split('_')
        
        # Extract the (always negative) threshold dB:
        p = re.compile(r'(^[-0-9]*)')
        err_msg = f"Cannot parse threshold dB from '{str_repr}'"
        try:
            threshold_db = p.search(threshold_db_str).group(1)
        except AttributeError:
            raise ValueError(err_msg)
        else:
            if len(threshold_db) == 0:
                raise ValueError(err_msg)
        
        # Low bandpass freq is int:
        p = re.compile(r'(^[0-9]*)')
        err_msg = f"Cannot parse low bandpass frequency from '{str_repr}'"
        
        try:
            low_freq = p.search(low_freq_str).group(1)
        except AttributeError:
            raise ValueError(err_msg)
        else:
            if len(low_freq) == 0:
                raise ValueError(err_msg)

        # High bandpass freq is int:
        p = re.compile(r'(^[0-9]*)')
        err_msg = f"Cannot parse high bandpass frequency from '{str_repr}'"
        
        try:
            high_freq = p.search(high_freq_str).group(1)
        except AttributeError:
            raise ValueError(err_msg)
        else:
            if len(high_freq) == 0:
                raise ValueError(err_msg)

        # Overlap:
        p = re.compile(r"(^[0-9]*|none)perc")
        err_msg = f"Cannot parse min_required_overlap from '{str_repr}'"
        try:
            min_required_overlap = p.search(min_overlap_str).group(1)
        except AttributeError:
            raise ValueError(err_msg)
        else: 
            if len(min_required_overlap) == 0:
                raise ValueError(err_msg)
            
        return(SignalTreatmentDescriptor(threshold_db,low_freq,high_freq,min_required_overlap))

    #------------------------------------
    # __str__
    #-------------------

    def __str__(self):
        '''
        Produce a string that, if eval is applied, will recreate
        and instance equivalent to this one. Ex:
           SignalTreatmentDescriptor('-40dB_300Hz_10perc')
        '''
        the_str = \
          f"SignalTreatmentDescriptor({self.threshold_db},{self.low_freq},{self.high_freq},{self.min_required_overlap})"
        return the_str

    #------------------------------------
    # __repr__
    #-------------------

    def __repr__(self):
        return f"<{__class__.__name__}: {self.to_flat_str()} at {hex(id(self))}>"
    
    #------------------------------------
    # to_flat_str
    #-------------------

    def to_flat_str(self):
        '''
        
        '''
        descriptor = f"{self.threshold_db}dB_{self.low_freq}Hz_{self.high_freq}Hz"
        if self.min_required_overlap is not None:
            descriptor += f"_{self.min_required_overlap}perc"
        else:
            descriptor += '_noneperc'
        return descriptor


    #------------------------------------
    # add_overlap
    #-------------------

    def add_overlap(self, min_required_overlap):
        '''
        Add the given minimum required overlap to the 
        given signal description.
        
        @param min_required_overlap: minimum percent overlap
        @type min_required_overlap: float
        '''
        self.min_required_overlap = min_required_overlap

    #------------------------------------
    # equality_sig_proc
    #-------------------
    
    def equality_sig_proc(self, other):
        '''
        Return True if at least the signal
        processing is equal with the 'other' 
        instance

        @param other:
        @type other:
        '''
        return self.threshold_db == other.threshold_db and \
            self.low_freq == other.low_freq and \
            self.high_freq == other.high_freq

    #------------------------------------
    # __eq__
    #-------------------
    
    def __eq__(self, other):
        '''
        Return True if all quantities of the 
        passed-in other instance are equal to this
        one.
        
        @param other:
        @type other:
        '''
        return self.equality_sig_proc(other) and \
            self.min_required_overlap == other.min_required_overlap

    def __ne__(self, other):
        if self.threshold_db != other.threshold_db or \
           self.low_freq != other.low_freq or \
           self.high_freq != other.high_freq or \
           self.min_required_overlap != other.min_required_overlap:
            return True
        else:
            return False
           
# ----------------------------- Main ----------------

if __name__ == '__main__':
    
    # Just some testing; doesn't normally run as main:
    fname = 'filtered_wav_-50dB_10Hz_50Hz_20200404_192128.npy'
    
    if os.path.exists(fname):
        os.remove(fname)
        
    new_file = DSPUtils.prec_recall_file_name(fname, 
                                               PrecRecFileTypes.FREQ_LABELS)
    
    assert (new_file == f"{os.path.splitext(fname)[0]}_freq_labels.npy"), \
            f"Bad freq_label file: {new_file}"
    os.remove(new_file) 

    new_file = DSPUtils.prec_recall_file_name(fname, 
                                               PrecRecFileTypes.FREQ_LABELS) 
            
    assert (new_file == f"{os.path.splitext(fname)[0]}_freq_labels.npy"), \
            f"Bad freq_label file: {new_file}"
             
    os.remove(new_file)
    
    new_file = DSPUtils.prec_recall_file_name(fname,
                                               PrecRecFileTypes.TIME_LABELS) 

    assert (new_file == f"{os.path.splitext(fname)[0]}_time_labels.npy"),\
            f"Bad freq_label file: {new_file}"
            
    os.remove(new_file) 

    new_file = DSPUtils.prec_recall_file_name(fname,
                                              PrecRecFileTypes.GATED_WAV) 

    assert (new_file == f"{os.path.splitext(fname)[0]}_gated.wav"),\
            f"Bad freq_label file: {new_file}"

    os.remove(new_file)

#     new_file = DSPUtils.prec_recall_file_name('/foo/bar/filtered_wav_-50dB_10Hz_50Hz_20200404_192128.npy', 
#                                                PrecRecFileTypes.GATED_WAV) 
# 
#     assert (new_file == '/foo/bar/filtered_wav_-50dB_10Hz_50Hz_20200404_192128_gated.wav'),\
#             f"Bad freq_label file: {new_file}" 

#    os.remove(new_file)

    print('File name manipulation tests OK')    
                                          
    # Test SignalTreatmentDescriptor:
    # To string:
    
    s1 = "SignalTreatmentDescriptor(-30,10,50,20)"
    d = SignalTreatmentDescriptor(-30, 10, 50, 20)
    assert str(d) == s1

    s2 = "SignalTreatmentDescriptor(-40,20,50,None)"
    d = SignalTreatmentDescriptor(-40, 20, 50)
    assert str(d) == s2

    try:    
        d = SignalTreatmentDescriptor('foo', 10, 50, 10)
    except ValueError:
        pass
    else:
        raise ValueError(f"String 'foo,10,50,10' should have raised an ValueError")
    
    # Test SignalTreatmentDescriptor:
    # From string:

    d = SignalTreatmentDescriptor.from_str(s1)
    assert (str(d) == s1)

    d = SignalTreatmentDescriptor.from_str(s2)
    assert (str(d) == s2)
    
    try:
        d = SignalTreatmentDescriptor.from_str('foo_10Hz_50Hz_30perc')
    except ValueError:
        pass
    else:
        raise AssertionError("Should have ValueError from 'foo_10Hz_50Hz_30perc'")

    # SignalTreatmentDescriptor
    # Adding min overlap after the fact:
    
    d = SignalTreatmentDescriptor(-40, 30, 60)
    assert (str(d) == "SignalTreatmentDescriptor(-40,30,60,None)")
    d.add_overlap(10)
    assert (str(d) == "SignalTreatmentDescriptor(-40,30,60,10)")
    
    # SignalTreatmentDescriptor
    # to_flat_str
    
    s3 = '-30dB_10Hz_50Hz_20perc'
    d = SignalTreatmentDescriptor.from_flat_str(s3)
    assert(d.to_flat_str() == s3)
    
    s4 = '-40dB_10Hz_50Hz_noneperc'
    d = SignalTreatmentDescriptor.from_flat_str(s4)
    assert(d.to_flat_str() == s4)
    
    s5 = '-40dB_10Hz_50Hz_10perc'
    d = SignalTreatmentDescriptor.from_flat_str(s5)
    assert(d.to_flat_str() == s5)
    
    # SignalTreatmentDescriptor
    # Equality
    
    d1 = SignalTreatmentDescriptor(-40,10,50,10)
    d2 = SignalTreatmentDescriptor(-40,10,50,10)
    assert (d1.__eq__(d2))
    
    d1 = SignalTreatmentDescriptor(-40,10,50,None)
    d2 = SignalTreatmentDescriptor(-40,10,50,10)
    assert (not d1.__eq__(d2))
    
    d1 = SignalTreatmentDescriptor(-40,10,50,10)
    d2 = SignalTreatmentDescriptor(-40,10,50,20)
    assert (d1.equality_sig_proc(d2))
    assert (not d1.__eq__(d2))
    
    
    print('SignalTreatmentDescriptor tests OK')
    
    print("Tests done.")
