#!/usr/bin/env python
'''
Created on Mar 5, 2020

@author: paepcke
'''
from _collections import OrderedDict
import argparse
from collections import deque
from pathlib import Path
import os
import pickle
import sys
import time

from amplitude_gating import AmplitudeGater
from amplitude_gating import FrequencyError
from dsp_utils import DSPUtils, PrecRecFileTypes, SignalTreatmentDescriptor
from elephant_utils.logging_service import LoggingService
import numpy as np
from plotting.plotter import PlotterTasks
from precision_recall_from_wav import PerformanceResult
from precision_recall_from_wav import PrecRecComputer


sys.path.append(os.path.join(os.path.dirname(__file__), '.'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

class PreprocessingCalibration(object):
    
    #------------------------------------
    # Constructor
    #-------------------    

    def __init__(self,
                 in_wav_file,
                 labelfile,
                 overlap_percentages=1,
                 thresholds_db=-40,
                 low_freqs=10,
                 high_freqs=150,
                 spectrogram_freq_cap=AmplitudeGater.spectrogram_freq_cap,
                 outfile_dir='/tmp',
                 spectrogram=None,
                 logfile=None):
        '''
        Run a series of experiments, and save the result
        Each experiment uses a different combination of 
        parameters.
        
        @param in_wav_file: wav file to experiment with
        @type in_wav_file: str
        @param labelfile: txt file of truth labels (elephant locations)
            usually created via Raven 
        @type labelfile: str
        @param overlap_percentages: one or more values for how much
            predicted time periods of el calls must overlap with 
            the true range to be counted as successful prediction
        @type overlap_percentages: {int|[int]}
        @param thresholds_db: dB below which all audio is set to zero.
            Currently, dB is relative to signal RMS. Must be a negative
            number. Low lower it is, the less signal is removed
        @type thresholds_db: int
        @param low_freqs: one or more frequencies to use as lower
            bounds of the bandpass filter that is applied to the 
            input before further processing.
        @type low_freqs: {int|[int]}
        @param high_freqs: one or more frequencies to use as upper
            bounds of the bandpass filter that is applied to the 
            input before further processing.
        @type upper_freqs: {int|[int]}
        @param spectrogram_freq_cap: highest frequency included in the
            spectrogram
        @type spectrogram_freq_cap: {int|[int]}
        @param outfile_dir: where the various result files will be
            written
        @type outfile_dir: str
        @param spectrogram: whether or not a spectrogram is 
            created, and written to an npy file
        @type spectrogram: bool
        @param logfile: file where log is written, instead of
            to stdout
        @type logfile: str
        '''
        
        if type(low_freqs) != list:
            low_freqs = [low_freqs]
        if type(high_freqs) != list:
            high_freqs = [high_freqs]
        if type(thresholds_db) != list:
            thresholds_db = [thresholds_db]

        # Make sure the corresponding low/high freqs
        # to try for the bandpass filter are suitable:
        # All low freqs must be less than all high freqs,
        # b/c all pairings will be tried:
        #   low_freqs: [10,20] and high_freqs: [50,60]
        # results in
        #    10/50, 10/60, 20/50, 20/60 being tried.
        for lowf in low_freqs:
            for highf in high_freqs:
                if lowf >= highf:
                    raise ValueError(f"All low freqs must be less than all high freqs; offenders: [{lowf},{highf}]")

        if not isinstance(overlap_percentages, list):
            overlap_percentages = [overlap_percentages]
            
        AmplitudeGater.log = LoggingService(logfile=logfile)
        self.log = AmplitudeGater.log

        self.outfile_dir = outfile_dir
        #*********
        #import logging
        #self.log.logging_level = logging.ERROR
        #*********

        self.log.info("Constructing output file names...")
        outfile_names_deque = self.construct_outfile_names(thresholds_db, 
                                                           low_freqs,
                                                           high_freqs,
                                                           outfile_dir)
        names_as_str = self.list_outfiles_from_deque(outfile_names_deque)
        self.log.info(f"Output files will be: {names_as_str}")

        self.spectrogram = spectrogram
                
        # Generate a new .wav file from the input file 
        # for each pair of voltage threshold/cutoff-freq pair.
        
        # Lots of work happens here: all the
        # spectrograms are created, if their
        # plots are requested:

        # To skip generating gated files for
        # testing the precision/recall component,
        # switch the commenting below:
        
        #****************************
        # Exchange commented/uncommented region for testing
        # just this method:

        #************
        #print(f"Pid {os.getpid()}: about to generate_outfiles")
        #************

        experiments = self.generate_outfiles(in_wav_file, 
                                             thresholds_db, 
                                             low_freqs,
                                             high_freqs,
                                             outfile_names_deque,
                                             spectrogram_freq_cap=spectrogram_freq_cap,
                                             spectrogram=self.spectrogram)
        #************
        #print(f"Pid {os.getpid()}: done generate_outfiles")
        #************
        
        # Remember whether we started writing
        # experiment files to a .tsv yet:
        started_tsv_output = False

        # Get in turn each Experiment instance that holds
        # the parameters of one volt/cutoffFreq experiment:
        
        for experiment in experiments:
            # Add additional info to each experiment
            experiment['in_wav_file'] = in_wav_file
            experiment['labelfile'] = labelfile
            
            #************
            #print(f"Pid {os.getpid()}: one experiment loop")
            #************
    
            # Gated signal file created by this experiment:
            gated_outfile_name = experiment['gated_outfile']
            
            for overlap_perc in overlap_percentages:
                # Create a copy of the experiment, so that
                # each overlap percentage computation will
                # be one experiment:
                this_experiment = experiment.copy()
                
                #************
                #print(f"Pid {os.getpid()}: in overlap loop")
                #************
                
                
                # Update the signal treatment from the original
                # experiment to reflect this overlap percentage
                # in the new exp:
                treatment = this_experiment['signal_treatment']
                treatment.add_overlap(overlap_perc)
                this_experiment['signal_treatment'] = treatment
                this_experiment['min_required_overlap'] = overlap_perc
                
                # Get a PerformanceResult instance with this
                # overlap percentage for the gated wav file
                # of this experiment. The resulting deque
                # will only have one element, b/c we only pass in
                # one file at a time (generate_prec_recall() could
                # handle multiple at a time):
                
                prec_recall_res = self.generate_prec_recall(this_experiment)
                this_experiment['experiment_res'] = prec_recall_res

                if not started_tsv_output:
                    #************
                    #print(f"Pid {os.getpid()}: preparing tsv")
                    #************

                    # Derive the experiment outfile name from the
                    # gated file name:
                    exp_res_file = DSPUtils.prec_recall_file_name(gated_outfile_name,
                                                                 PrecRecFileTypes.EXPERIMENT)
                    # Start fresh file, and add column header:
                    
                    #************
                    #print(f"Pid: {os.getpid()}): new exp file {exp_res_file}")
                    #************
                    
                    this_experiment.to_flat_tsv(include_col_header=True,
                                                append=False, 
                                                outfile=exp_res_file)
                    # Next experiment should get appended to the same tsv file:
                    started_tsv_output = True
                    
                else:
                    #************
                    #print(f"Pid {os.getpid()}: continue write to {exp_res_file}")
                    #************
                    this_experiment.to_flat_tsv(include_col_header=False,
                                                append=True, 
                                                outfile=exp_res_file)
                    
                # Save the experiment as a pickle for complete
                # recovery needs later:
                exp_pickle_file = DSPUtils.prec_recall_file_name(gated_outfile_name,
                                                                 PrecRecFileTypes.PICKLE,
                                                                 f"_{overlap_perc}perc"
                                                                 )
                this_experiment.save(exp_pickle_file)

        self.log.info("Done generating precision/recall measures.")
        
        #************
        #print(f"Pid {os.getpid()}: exiting __init__")
        #************

                
    #------------------------------------
    # generate_prec_recall
    #-------------------
    
    def generate_prec_recall(self, experiment):
        '''
        Takes one experiment, whose signal_treatment specifies
        the noise-gated wav file to examine, the label file, and
        the overlap percentage required for an event to count as
        discovered.
        
        Returns a PerformanceResult instance.
            
        @param experiment: experiment instance with all information
        @type experiment: PerformanceResult
        @return: one PerformanceResult instance
        @rtype: PerformanceResult
        '''

        filtered_wavfile = experiment['gated_outfile']
        overlap_perc     = experiment['signal_treatment'].min_required_overlap
        self.log.info(f"Compute prec/recall for {filtered_wavfile}...")
        precrec_computer = PrecRecComputer(experiment['signal_treatment'], 
                                           filtered_wavfile, 
                                           experiment['labelfile'], 
                                           overlap_perc,
                                           print_res=False     #***********
                                           )
        self.log.info(f"Done compute prec/recall for {filtered_wavfile}.")
        # PrecRecComputer can take a deque of overlap_perc 
        # requirements, and therefore for generality holds
        # a deque of performance results. We only ever pass
        # in one overlap percentage, so the result will always
        # have just one element:
        # 
        perf_res = precrec_computer.performance_results[0]
        return perf_res

    #------------------------------------
    # generate_outfiles
    #-------------------
    
    def generate_outfiles(self, 
                          in_wav_file, 
                          thresholds_db, 
                          low_freqs,
                          high_freqs,
                          outfile_names,
                          spectrogram_freq_cap=AmplitudeGater.spectrogram_freq_cap,
                          spectrogram=None):
        '''
        Run through each threshold voltage and lowpass filter
        cutoff frequency, and generate a wave file for each.
        Caller provides the output file names.
        
        @param in_wav_file: elephant wave file over which to 
            run each setting to produce cleaned .wav files.
        @type in_wav_file: str
        @param thresholds_db: voltages above which to set wav
            signals to zero. Values are in dB below peak. Thus
            always negative numbers.
        @type thresholds_db: [int]
        @param low_freqs: low frequencies to try for the font end
            bandpass filter.
        @type low_freqs: [int]
        @param high_freqs: high frequencies to try for the font end
            bandpass filter.
        @type high_freqs: [int]
        @param overlap_percentages: list of the minimum percentage
            overlap of detected with labeled burst required
        @type overlap_percentages: [float]
        @param outfile_names: list of full path filenames, one
            for each experiment.
        @type outfile_names: [str]
        @param spectrogram: if True, a spectrogram is created,
            and written to outdir, with the same file name as the 
            .wav file, but with an.npy extension. If False, no 
            spectrogram is created.
        @type spectrogram: bool
        @return: Dequeu of Experiment instances with all parameters used.
        @rtype: Dequeue(Experiment)
        '''

        experiments = deque()
        #************
        #print(f"Pid {os.getpid()}: in generate_outfiles: thres {thresholds_db}. lowfs: {low_freqs}. highfs: {high_freqs}")
        #************

        for threshold in thresholds_db:
            for low_freq in low_freqs:
                for high_freq in high_freqs:
                    outfile = outfile_names.popleft()
                    # Create a corresponding file name for spectrograms:
                    if spectrogram:
                        spectrogram_outfile = DSPUtils.prec_recall_file_name(outfile,
                                                                             PrecRecFileTypes.SPECTROGRAM)
                    else:
                        spectrogram_outfile = None
                    self.log.info(f"Generating [{threshold}dB, {low_freq}Hz, {high_freq}Hz]...")
                    try:
                        # Generate an Experiment instance to
                        # which caller can later add precision/recall
                        # results:
                        signal_treatment = SignalTreatmentDescriptor(threshold,low_freq,high_freq)
                        experiment = Experiment({'signal_treatment'      : signal_treatment,
                                                 'in_wav_file'           : in_wav_file,
                                                 'labelfile'             : None,            # Filled in later
                                	    		 'gated_outfile'         : outfile,
                                        		 'spectrogram_outfile'   : spectrogram_outfile,
                                        		 'threshold_db'          : threshold,
                                        		 'low_freq'              : low_freq,
                                                 'high_freq'             : high_freq,
                                        		 'spectrogram_freq_cap'  : spectrogram_freq_cap,
                                                 'min_required_overlap'  : None,  # Added when overlaps are run
                                                 'percent_zeroed'        : None,  # Get that from AmplitudeGater
                                        		 'experiment_res'        : None   # Get from AmplitudeGater
                                                })
                        # Compute one noise gated wav outfile:
                        #************
                        #print(f"Pid {os.getpid()}: about to gate")
                        #************
                        _gater = AmplitudeGater(in_wav_file,
                                                amplitude_cutoff=threshold,
                                                low_freq=low_freq,
                                                high_freq=high_freq,
                                                spectrogram_freq_cap=spectrogram_freq_cap,
                                                outfile=outfile
                                                )
                        #************
                        #print(f"Pid {os.getpid()}: done gating")
                        #************
    
                        experiment['percent_zeroed'] = _gater.percent_zeroed
                        experiments.append(experiment)
                    except FrequencyError as e:
                        self.log.err(f"Bad frequency; skipping it: {repr(e)}")
                        continue
                    self.log.info(f"Done generating [{threshold}dB, {low_freq}Hz, {high_freq}Hz] into {os.path.basename(outfile)}...")
        self.log.info("Done generating outfiles.")
        return experiments

    #------------------------------------
    # construct_outfile_names
    #-------------------
    
    def construct_outfile_names(self, 
                                thresholds_db, 
                                low_freqs,
                                high_freqs, 
                                outfile_dir):
        '''
        Construct a file names that contain the 
        passed-in parameters. Note that thresholds_db,
        low_freqs, and high_freqs are lists. So multiple names
        are constructed.
        
        @param thresholds_db: list of dB below which
            signals were clamped to 0
        @type thresholds_db: [int]
        @param low_freqs: list of low bandpass frequencies
        @type low_freqs: [int]
        @param high_freqs: list of high bandpass frequencies
        @type high_freqs: [int]
        @param outfile_dir: directory for which the paths 
            are to be constructed
        @type outfile_dir: str
        @return all outfile paths
        @rtype: dequeue
        '''
        
        out_files = deque()
        for threshold in thresholds_db:
            for low_freq in low_freqs:
                for high_freq in high_freqs:
                    timestamp = time.strftime("%Y%m%d_%H%M%S")
                    outfile = os.path.join(outfile_dir,
                                           f"filtered_wav_{threshold}dB_{low_freq}Hz_{high_freq}Hz_{timestamp}.wav")
                    # Add info that this is a gated wav file:
                    outfile = DSPUtils.prec_recall_file_name(outfile, PrecRecFileTypes.GATED_WAV)
                    out_files.append(outfile)

        return out_files
    
    #------------------------------------
    # list_outfiles_from_deque
    #-------------------
    
    def list_outfiles_from_deque(self, file_name_deque):
        '''
        Given a deque filled with full pathnames, return a 
        string that lists all files. But: the dir path is only
        listed once. Following lines are indented and only have the
        file names. Ex. output:
            Directory  /tmp:
                foo.txt,
                bar.txt,
        If deque is empty, return "No files in list."
                
        @param file_name_deque: Deque of path names
        @type file_name_deque: Deque[str]
        '''
        if len(file_name_deque) == 0:
            return "No files in list."
        dir_path = os.path.dirname(file_name_deque[0])
        res = f"Directory {dir_path}:"
        for file_name in file_name_deque:
            res += f"\n\t{file_name}"
        return res

# ---------------------------- Experiment Class ---------------

class Experiment(OrderedDict):

    # Name of all properties stored in instances
    # of this class. Needed when reading from
    # previously saved csv file of a PerformanceResult
    # instance:
    props = OrderedDict({'signal_treatment'      : SignalTreatmentDescriptor,
                         'in_wav_file'           : str,
                         'labelfile'             : str,
                    	 'gated_outfile'         : str,
                         'spectrogram_outfile'   : str,
                         'threshold_db'          : int,
                         'low_freq'              : int,
                         'high_freq'             : int,
                         'min_required_overlap'  : float,
                         'spectrogram_freq_cap'  : int,
                         'percent_zeroed'        : float,
                         'experiment_res'        : PerformanceResult
                        })
    
    # The properties when SignalTreatmentDescriptor and PerformanceResult
    # are expanded with their own props:
    flat_props = OrderedDict()
    for (prop_name, dest_type) in props.items():
        if dest_type in (str,int,float):
            flat_props[prop_name] = dest_type

        else:
            # Append to flat_props the dict of props
            # of the complex type (e.g. SignalTreatmentDescriptor).
            # Update works in place, and like array.extend():
            flat_props.update(dest_type.props) 
    
    #------------------------------------
    # Constructor
    #-------------------
    
    def __init__(self, all_results={}):
        # Put the passed-in dict into a logical order:
        self_dict = self.props.copy()
        for key in self_dict.keys():
            try:
                self_dict[key] = all_results[key]
            except KeyError:
                # Passed-in dict does not have result
                # the prop:
                self_dict[key] = None
        # Add any entries in all_results that are unexpected
        # to the end, preserving order:
        for key in all_results.keys():
            if key not in self_dict.keys():
                self_dict[key] = all_results[key]
         
        # Save the dict as who this instance is:
        super().__init__(self_dict)

    #------------------------------------
    # to_flat_tsv
    #-------------------

    def to_flat_tsv(self, include_col_header=False, outfile=None, append=True):
        '''
        Write an Experiment instance to .tsv file with all PerformanceResult
        instances flattened. 
        
        The purpose of this method is to make an 
        Experiment accessible to Tableau or Excel.
        Only the overlaps_summary stats remain as
        a dict.
        
        That is in contrast to method save(), which preserves
        the ability to reconstitute an Experiment instance via
        instances_from_saved()

        @param include_col_header:
        @type include_col_header:
        @param outfile:
        @type outfile:
        @param append:
        @type append:
        '''
        
        if include_col_header:
            # Create column header, but remove the 'experiment_res'
            # column name, because it will be expanded below into 
            # the col names of the PerformanceResult instance:
            
            col_header = '\t'.join([f"{col_name}" for col_name in self.keys() if col_name != 'experiment_res'])
        else:
            col_header = ''

        row_arr = []
        for prop_val in self.values():
            # Numpy arrays add a '\n' char after a certain
            # number of array elements, make that num huge:
            if isinstance(prop_val, np.ndarray):
                row_arr.append(np.array2string(prop_val,
                                               max_line_width=10000,
                                               separator=','))
            elif isinstance(prop_val, PerformanceResult):
                # Found a PerformanceResult object. Add its
                # col names to the Experiment class related
                # col names:
                flat_perf_res = prop_val.to_flat_dict()
                col_header += '\t' + '\t'.join([f"{col_name}" for col_name in flat_perf_res.keys()])
                
                # And add all the PerformanceResult attributes
                # to the row_arr:
                row_arr.extend(flat_perf_res.values())
                
            elif isinstance(prop_val, dict):
                # Found the overlaps_summary dict:
                col_header += '\t'.join([f"{col_name}" for col_name in prop_val.keys()])
                row_arr.extend(prop_val.values())
                
            elif isinstance(prop_val, SignalTreatmentDescriptor):
                row_arr.append(prop_val.to_flat_str())
            else:
                row_arr.append(str(prop_val))
            
        csv_line = '\t'.join([str(item) for item in row_arr])

        try:
            if outfile is not None:
                fd = open(outfile, 'a' if append else 'w')
            else:
                fd = sys.stdout
            if include_col_header:
                fd.write(col_header + '\n')
            fd.write(csv_line + '\n')
        finally:
            if outfile:
                fd.close()


    #------------------------------------
    # save
    #-------------------

    def save(self, outfile, append=True):
        '''
        Pickle an Exeriment instance, so that the load()
        method can reconstitute the instance from that
        file.
        
        May be called multiple times to save
        multiple experiments, if append is set
        to True. Always saves a list of experiment(s)
         
        @param outfile: name of destination file. Should end in .pickle
        @type outfile: str
        '''
        # Sometimes empty experiment files are left
        # around (need to fix that). Check whether
        # outfile is one of those, as indicated
        # by its length being zero:
        try:
            if Path(outfile).stat().st_size == 0:
                os.remove(outfile)
        except FileNotFoundError:
            pass
         
        if append and os.path.exists(outfile):
            # To append we need to read the current
            # list of Experiment instances, add self
            # to that list, and re-pickle:
            experiments_list = list(self.load(outfile))
        else:
            experiments_list = []
        experiments_list.append(self)
        with open(outfile, 'wb') as fd:
            pickle.dump(experiments_list,fd)

    #------------------------------------
    # load
    #-------------------
    
    @classmethod
    def load(cls, fd_or_path):
        '''
        Given an open fd_or_path to a pickeled
        file, return an iterator over all the 
        experiments saved in that file.
        Can be called multiple times to get 
        successive instances that were all

        Raises StopIteration when nothing left.
        
        @param fd_or_path: file object open for 
            binary read (br)
        @type fd_or_path: {str|fd}
        @return: one Experiment instance, if one is left.
        @rtype: Experiment
        @raise StopIteration: if no experiment left. 
        '''
        if isinstance(fd_or_path, str):
            fd = open(fd_or_path, 'br')
        try:
            experiments_list = pickle.load(fd)
        except Exception as e:
            raise IOError(f"Content of supposed Experiments list is not: {repr(e)}")
        try:
            yield from experiments_list
        finally:
            # If we opened the file, close it:
            if isinstance(fd_or_path, str):
                fd.close()

    #------------------------------------
    # instances_from_saved
    #-------------------

    @classmethod
    def instances_from_saved(cls, infile):
        
        with open(infile, 'rb') as fd:
            return pickle.load(fd)
            
    #------------------------------------
    # _make_res_obj
    #-------------------

    @classmethod
    def _make_res_obj(cls, values_arr_strings, prop_order):
    
        res_obj = Experiment()
        for (indx, prop_name) in enumerate(prop_order):
            # To which data type must this string be
            # coerced?:
            dest_type = Experiment.props[prop_name]
            # Does it call for a PerformanceResult?
            if dest_type == PerformanceResult:
                # Reconstitute the PerformanceResult
                # instance:
                perf_res_create_str = values_arr_strings[indx]
                typed_val = PerformanceResult.from_str(perf_res_create_str)
            elif dest_type == SignalTreatmentDescriptor:
                # Reconstitute the SignalTreatmentDescriptor
                # instance:
                sig_treat_desc_create_str = values_arr_strings[indx]
                typed_val = SignalTreatmentDescriptor.from_str(sig_treat_desc_create_str)
            else:
                typed_val = dest_type(values_arr_strings[indx])
            res_obj[prop_name] = typed_val
            
        return res_obj 

    #------------------------------------
    # __eq__
    #-------------------

    def __eq__(self, other):
        
        if not isinstance(other, self.__class__):
            return NotImplemented
        for (key, val) in self.items():
            # Use ==, rather than != in case
            # other has no __ne__
            if val == other[key]:
                continue
            else:
                return False
        return True

    #------------------------------------
    # print
    #-------------------
    
    def print(self, outfile=None):
        
        try:
            if outfile is None:
                out_fd = sys.stdout
            else:
                out_fd = open(outfile, 'w')
            
            print('Experiment settings:\n')
            # For nice col printing: find longest 
            # property name:
            col_width = max(len(prop_name) for prop_name in self.keys())
            for prop_name in self.keys():
                # The PerformanceResult instance has its own
                # printing method:
                if prop_name == 'experiment_res':
                    print("\nExperiment result:\n")
                    self[prop_name].print()
                    continue
                print(prop_name.ljust(col_width), self[prop_name])

        finally:
            if out_fd != sys.stdout:
                out_fd.close()

# ------------------------------ Main ------------------------

if __name__ == '__main__':
    
    parser = argparse.ArgumentParser(prog=os.path.basename(sys.argv[0]),
                                     formatter_class=argparse.RawTextHelpFormatter,
                                     description="Compute precision/recall for pairs of voltage cutoff, and lowpass frequencies."
                                     )

    parser.add_argument('-l', '--logfile',
                        help='fully qualified log file name to which info and error messages \n' +\
                             'are directed. Default: stdout.',
                        default=None);
    parser.add_argument('-d', '--outdir',
                        help='fully qualified directory for output wav files.',
                        default='/tmp');
    parser.add_argument('-o', '--overlaps',
                        type=int,
                        nargs='+',
                        help='percentage overlap of prediction with label to count as success; repeatable; default: 1perc.',
                        default=[1]);
    parser.add_argument('-t', '--threshold_dbs',
                        type=int,
                        nargs='+',
                        default=[-40],
                        help='Repeatable: db above which voltages are cut off; default: -40dB FS')
    parser.add_argument('-m', '--lowfreqs',
                        type=int,
                        nargs='+',
                        default=[10],
                        help='Repeatable: low frequency of front end bandpass filter; default: 10Hz')
    parser.add_argument('-i', '--highfreqs',
                        type=int,
                        nargs='+',
                        default=[50],
                        help='Repeatable: high frequency of front end bandpass filter; default: 50Hz')
    parser.add_argument('-s', '--spectrogram',
                        default=None,
                        action='store_true',
                        help='If provided, a spectrogram is created and written to outdir as .npy file')
    parser.add_argument('--plot',
                        nargs='+',
                        default=[],
                        choices=['gated_wave_excerpt','samples_plus_envelope','spectrogram_excerpts','low_pass_filter'],
                        help="Plots to produce; repeatable; default: no plots"
                        )
    parser.add_argument('wavefile',
                        help='fully qualified path to elephant wav file.',
                        default=None)
    parser.add_argument('labelfile',
                        help='fully qualified path to corresponding Raven label file.',
                        default=None)

    args = parser.parse_args();
    
    # Register the plots to produce:
    if args.plot is not None:
        for plot_name in args.plot:
            PlotterTasks.add_task(plot_name)

    PreprocessingCalibration(args.wavefile,
                             args.labelfile,
                             args.overlaps,
                             args.threshold_dbs,
                             args.lowfreqs,
                             args.highfreqs,
                             outfile_dir=args.outdir,
                             spectrogram=args.spectrogram,
                             logfile=args.logfile
                             )
    if len(args.plot) > 0:
        input("Press ENTER to close the figures and exit...")
