'''
Created on Jul 14, 2020

@author: paepcke
'''
import os, sys
import shutil
import unittest
import glob
from pathlib import Path

import pandas as pd

sys.path.append(os.path.join(os.path.dirname(__file__), '.'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from spectrogram_dataset import SpectrogramDataset, AudioType
from DSP.dsp_utils import FileFamily

TEST_ALL = True
#TEST_ALL = False


class Test(unittest.TestCase):

    #------------------------------------
    # setUpClass
    #-------------------
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Create Sqlite3 db for spectrogram snippet info:
        cls.test_db_path = os.path.join(os.path.dirname(__file__),
                                        'SamplesTests.sqlite')
        # Start with a fresh Samples db/table:
        try:
            os.remove(cls.test_db_path)
        except Exception:
            # Wasn't there:
            pass

        # Path to a small Raven label file:
        cls.label_file = os.path.join(os.path.dirname(__file__),
                                      'labels_for_testing.txt')

        # Path where we sometimes pretend a 24 hour spectrogram resides:
        cls.snippet_outdir = os.path.dirname(__file__)

    #------------------------------------
    # tearDownClass
    #-------------------
    
    @classmethod
    def tearDownClass(cls):
        
        for file in glob.glob('test_spectro*.pickle'):
            os.remove(file)
            
        for file in glob.glob('test_spectro*.sqlite'):
            os.remove(file)
            
        for file in glob.glob('labels_for_testing_*.pickle'):
            os.remove(file)
        
        try:
            os.remove('test_spectroA.txt')
        except Exception:
            pass
        try:
            os.remove('test_spectroB.txt')
        except Exception:
            pass
        try:
            os.remove('SamplesTests.sqlite')
        except Exception:
            pass

    #------------------------------------
    # setUp 
    #-------------------

    def setUp(self):


        self.db = SpectrogramDataset.get_db(self.test_db_path)
        # Empty the test db Samples table:
        self.db.execute("DELETE FROM Samples;")
        self.db.commit()

        self.files_to_delete = self.prepare_kfolds_test()

        rows = self.db.execute("SELECT sample_id FROM Samples;")
        self.sample_ids = [row['sample_id'] for row in rows]
        
        # Instance of a SpectrogramDataset that
        # does nothing in its init method
        self.spectr_dataset = SpectrogramDataset(testing=True,
                                                 test_db=self.db)
        
        # Make the snippet width narrower so the tests
        # below can work with narrow dataframes, yet get
        # multiple snippets:
        
        self.spectr_dataset.SNIPPET_WIDTH = 5 # seconds
        
        # The frequency bands in which energy means
        # are computed are usually betwen 0 and 60,
        # But our test dfs only have three lines with
        # index 1,2,3. So artificially change the 
        # dataset instance's freq ranges:
        
        self.spectr_dataset.LOW_FREQ_BAND = pd.Interval(left=0, right=1)
        self.spectr_dataset.MED_FREQ_BAND = pd.Interval(left=1, right=2)
        self.spectr_dataset.HIGH_FREQ_BAND = pd.Interval(left=2, right=3)
        
    #------------------------------------
    # tearDown 
    #-------------------


    def tearDown(self):
        self.db.close()
        for file in glob.glob('test_spectro*.sqlite'):
            os.remove(file)

    #------------------------------------
    # testLabelForSnippet 
    #-------------------

    @unittest.skipIf(TEST_ALL != True, 'skipping temporarily')
    def testLabelForSnippet(self):
        
        # No overlap:
        snippet_interval = pd.Interval(left=50.1, right=55.5)
        is_ele_call = self.spectr_dataset.label_for_snippet(snippet_interval,
                                                       self.label_file,
                                                       required_overlap_percentage=None
                                                       )
        self.assertFalse(is_ele_call)
        
        # Partial overlap:
        snippet_interval = pd.Interval(left=60.3, right=70)
        is_ele_call = self.spectr_dataset.label_for_snippet(snippet_interval,
                                                       self.label_file,
                                                       required_overlap_percentage=None
                                                       )
        self.assertTrue(is_ele_call)

        # Full overlap, i.e. containment:
        snippet_interval = pd.Interval(left=93, right=94)
        is_ele_call = self.spectr_dataset.label_for_snippet(snippet_interval,
                                                       self.label_file,
                                                       required_overlap_percentage=None
                                                       )
        self.assertTrue(is_ele_call)
        
        # Percentage requirement percent as fraction 0-1:
        snippet_interval = pd.Interval(left=93, right=94)
        required = 0.5 # %
        is_ele_call = self.spectr_dataset.label_for_snippet(
            snippet_interval,
            self.label_file,
            required_overlap_percentage=required
            )
        
        if is_ele_call:
            self.assertTrue(1/(92.793 - 95.41599999999232) >= required)
        else:
            self.assertTrue(1/(92.793 - 95.41599999999232) < 0.5)
        
        
        # Percentage requirement zero percent:
        snippet_interval = pd.Interval(left=93, right=94)
        required = 0
        is_ele_call = self.spectr_dataset.label_for_snippet(
            snippet_interval,
            self.label_file,
            required_overlap_percentage=required
            )
        if is_ele_call:
            self.assertTrue(1/(95.41599999999232 - 92.793) >= required)
        else:
            self.assertTrue(1/(95.41599999999232 - 92.793) < required)

    #------------------------------------
    # testDecodeFilename 
    #-------------------

    # Needs update to decode_filename() returning
    # a FileFamily instance. Also: Move to tests for
    # DSPUtils.

#     @unittest.skipIf(TEST_ALL != True, 'skipping temporarily')
#     def testDecodeFilename(self):
#         
#         res_dict = self.spectr_dataset.decode_filename('/foo/bar.txt')
#         expected = {'file_type': AudioType.LABEL,
#                     'file_root': 'bar',
#                     'path': '/foo',
#                     'wav': 'bar.wav',
#                     'label': 'bar.txt',
#                     'spectro': 'bar_spectrogram.pickle'}
#         self.assertDictContainsSubset(expected, res_dict)
#         
#         res_dict = self.spectr_dataset.decode_filename('bar.txt')
#         expected = {'file_type': AudioType.LABEL,
#                     'file_root': 'bar',
#                     'path': None,
#                     'wav': 'bar.wav',
#                     'label': 'bar.txt',
#                     'spectro': 'bar_spectrogram.pickle',
#                     'snippet_id': None
#                     }
#         self.assertDictContainsSubset(expected, res_dict)
# 
#         res_dict = self.spectr_dataset.decode_filename('bar_spectrogram.pickle')
#         expected = {'file_type': AudioType.SPECTRO,
#                     'file_root': 'bar',
#                     'path': None,
#                     'wav': 'bar.wav',
#                     'label': 'bar.txt',
#                     'spectro': 'bar_spectrogram.pickle',
#                     'snippet_id': None
#                     }
# 
#         self.assertDictContainsSubset(expected, res_dict)
#    
#         res_dict = self.spectr_dataset.decode_filename('/foo/fum/bar.wav')
#         expected = {'file_type': AudioType.WAV,
#                     'file_root': 'bar',
#                     'path': '/foo/fum',
#                     'wav': 'bar.wav',
#                     'label': 'bar.txt',
#                     'spectro': 'bar_spectrogram.pickle',
#                     'snippet_id': None
#                     }
# 
#         self.assertDictContainsSubset(expected, res_dict)
#         
#         res_dict = self.spectr_dataset.decode_filename('bar_2_spectrogram.pickle')
#         expected = {'file_type': AudioType.SNIPPET,
#                     'file_root': 'bar',
#                     'path': None,
#                     'wav': 'bar.wav',
#                     'label': 'bar.txt',
#                     'spectro': 'bar_spectrogram.pickle',
#                     'snippet_id': 2
#                     }
#         
#         self.assertDictContainsSubset(expected, res_dict)
        
    #------------------------------------
    # testChopOneSpectrogram 
    #-------------------
    
    @unittest.skipIf(TEST_ALL != True, 'skipping temporarily')
    def testChopOneSpectrogram(self):
        
        self.db.execute("DELETE FROM Samples;")
        spectrogram = pd.DataFrame([[  1,  2,  3,  4,  5,  6,  7],
                                    [ 10, 20, 30, 40, 50, 60, 70],
                                    [100,200,300,400,500,600,700],
                                    ], dtype=int,
                                    columns=[0,2,4,6,8,10,12],
                                    index=[0,1,2]
                                    )
        curr_file_family = FileFamily(self.label_file)
        parent_freq_energies = {}
        parent_freq_energies['parent_low_freqs_energy'] = spectrogram.iloc[0,].mean()
        parent_freq_energies['parent_med_freqs_energy'] = spectrogram.iloc[1,].mean()
        parent_freq_energies['parent_high_freqs_energy'] = spectrogram.iloc[2,].mean()
        self.spectr_dataset.chop_one_spectrogram(spectrogram,
                                                 self.label_file,
                                                 self.snippet_outdir,
                                                 parent_freq_energies,
                                                 curr_file_family
                                                 )
        # Times 0,4 sec
        #   Matches label 1.293    6.464999999991385
        # ==> Label: 1
        
        # Should have 2 rows in Sample table:
        rows = self.db.execute("SELECT * FROM Samples;").fetchall()
        self.assertEqual(len(rows), 2)
        # First snippet:
        row = rows[0]
        self.assertEqual(row['sample_id'], 1)
        self.assertEqual(row['label'], 1)
        self.assertEqual(row['start_time_tick'], 0)
        self.assertEqual(row['end_time_tick'], 2)
        self.assertEqual(row['start_time'], 0)
        self.assertEqual(row['end_time'], 4)
        self.assertEqual(row['parent_low_freqs_energy'], 4.0)
        self.assertEqual(row['parent_med_freqs_energy'], 40.0)
        self.assertEqual(row['parent_high_freqs_energy'], 400.0)
        self.assertEqual(row['snippet_low_freqs_energy'], 1.5)
        self.assertEqual(row['snippet_med_freqs_energy'], 15.0)
        self.assertEqual(row['snippet_high_freqs_energy'], 150.0)
        
        self.assertTrue(row['snippet_filename'].endswith('labels_for_testing_1_spectrogram.pickle'))

        # Second snippet:
        row = rows[1]
        self.assertEqual(row['sample_id'], 2)
        self.assertEqual(row['label'], 1)
        self.assertEqual(row['start_time_tick'], 2)
        self.assertEqual(row['end_time_tick'], 4)
        self.assertEqual(row['start_time'], 4)
        self.assertEqual(row['end_time'], 8)
        self.assertEqual(row['parent_low_freqs_energy'], 4.0)
        self.assertEqual(row['parent_med_freqs_energy'], 40.0)
        self.assertEqual(row['parent_high_freqs_energy'], 400.0)
        self.assertEqual(row['snippet_low_freqs_energy'], 3.5)
        self.assertEqual(row['snippet_med_freqs_energy'], 35.0)
        self.assertEqual(row['snippet_high_freqs_energy'], 350.0)
        
        self.assertTrue(row['snippet_filename'].endswith('labels_for_testing_2_spectrogram.pickle'))
        
    #------------------------------------
    # testChopMultipleSpectrograms
    #-------------------
     
    @unittest.skipIf(TEST_ALL != True, 'skipping temporarily')
    def testChopMultipleSpectrograms(self):
        
        self.db.execute("DELETE FROM Samples;")
        
        spectro1 = pd.DataFrame([[  1,  2,  3,  4,  5,  6,  7],
                                 [ 10, 20, 30, 40, 50, 60, 70],
                                 [100,200,300,400,500,600,700],
                                 ], dtype=float,
                                 columns=[0,2,4,6,8,10,12],
                                 index=[0,1,2]
                                 )
                                  
        spectro2 = pd.DataFrame([[1000,2000,3000,4000,5000,6000,7000],
                                 [2000,3000,4000,5000,6000,7000,8000],
                                 [3000,4000,5000,6000,7000,8000,9000],
                                 ], dtype=float,
                                 columns=[0,2,4,6,8,10,12],
                                 index=[0,1,2]
                                 )
    
        curr_dir = os.path.dirname(__file__)
        spectroA_file = os.path.join(curr_dir, 
                                     'test_spectroA_spectrogram.pickle')
        spectroB_file = os.path.join(curr_dir,
                                     'test_spectroB_spectrogram.pickle')
        spectro1.to_pickle(spectroA_file)
        spectro2.to_pickle(spectroB_file)

        spectroA_label_file = os.path.join(curr_dir, 'test_spectroA.txt')
        spectroB_label_file = os.path.join(curr_dir, 'test_spectroB.txt')
        
        # Use the same label file for both spectrograms:
        shutil.copyfile(self.label_file, spectroA_label_file)
        shutil.copyfile(self.label_file, spectroB_label_file)

        spectro_labels_dict = {spectroA_file : spectroA_label_file,
                               spectroB_file : spectroB_label_file
                               }
    
        self.spectr_dataset.chop_spectograms(spectro_labels_dict)
        # DB should have:
        #      1|test_spectroA|1|0|2|0.0|4.0|.../src/CNN/Tests/test_spectroA_1_spectrogram.pickle
        #      2|test_spectroA|1|2|4|4.0|8.0|.../src/CNN/Tests/test_spectroA_2_spectrogram.pickle
        #      3|test_spectroB|1|0|2|0.0|4.0|.../src/CNN/Tests/test_spectroB_3_spectrogram.pickle
        #      4|test_spectroB|1|2|4|4.0|8.0|.../src/CNN/Tests/test_spectroB_4_spectrogram.pickle
        # With row dict keys:
        #      ['sample_id', 'recording_site',
        #       'label', 'start_time_tick',
        #       'end_time_tick', 'start_time',
        #       'end_time', 'snippet_filename']
        
        snippet_rows = self.db.execute('SELECT * FROM Samples').fetchall()
        self.assertEqual(len(snippet_rows), 4)
        
        for row in snippet_rows:
            if row['sample_id'] == 1:
                self.assertEqual(row['label'], 1)
                self.assertEqual(row['start_time_tick'], 0)
                self.assertEqual(row['end_time_tick'], 2)
                self.assertEqual(row['start_time'], 0.0)
                self.assertEqual(row['end_time'], 4.0)
                
                self.assertEqual(row['parent_low_freqs_energy'], 4.0)
                self.assertEqual(row['parent_med_freqs_energy'], 40.0)
                self.assertEqual(row['parent_high_freqs_energy'], 400.0)
                self.assertEqual(row['snippet_low_freqs_energy'], 1.5)
                self.assertEqual(row['snippet_med_freqs_energy'], 15.0)
                self.assertEqual(row['snippet_high_freqs_energy'], 150.0)
                
                self.assertTrue(row['snippet_filename'].endswith('test_spectroA_1_spectrogram.pickle'))

            elif row['sample_id'] == 2:
                self.assertEqual(row['label'], 1)
                self.assertEqual(row['start_time_tick'], 2)
                self.assertEqual(row['end_time_tick'],4 )
                self.assertEqual(row['start_time'], 4.0)
                self.assertEqual(row['end_time'], 8.0)
                
                self.assertEqual(row['parent_low_freqs_energy'], 4.0)
                self.assertEqual(row['parent_med_freqs_energy'], 40.0)
                self.assertEqual(row['parent_high_freqs_energy'], 400.0)
                
                self.assertEqual(row['snippet_low_freqs_energy'], 3.5)
                self.assertEqual(row['snippet_med_freqs_energy'], 35.0)
                self.assertEqual(row['snippet_high_freqs_energy'], 350.0)
                
                self.assertTrue(row['snippet_filename'].endswith('test_spectroA_2_spectrogram.pickle'))

            if row['sample_id'] == 3:
                self.assertEqual(row['label'], 1)
                self.assertEqual(row['start_time_tick'], 0)
                self.assertEqual(row['end_time_tick'], 2)
                self.assertEqual(row['start_time'], 0.0)
                self.assertEqual(row['end_time'], 4.0)

                self.assertEqual(row['parent_low_freqs_energy'], 4000.0)
                self.assertEqual(row['parent_med_freqs_energy'], 5000.0)
                self.assertEqual(row['parent_high_freqs_energy'],6000.0)
                self.assertEqual(row['snippet_low_freqs_energy'], 1500.0)
                self.assertEqual(row['snippet_med_freqs_energy'], 2500.0)
                self.assertEqual(row['snippet_high_freqs_energy'],3500.0)
                
                self.assertTrue(row['snippet_filename'].endswith('test_spectroB_3_spectrogram.pickle'))

            elif row['sample_id'] == 4:
                self.assertEqual(row['label'], 1)
                self.assertEqual(row['start_time_tick'], 2)
                self.assertEqual(row['end_time_tick'],4 )
                self.assertEqual(row['start_time'], 4.0)
                self.assertEqual(row['end_time'], 8.0)
                
                self.assertEqual(row['parent_low_freqs_energy'], 4000.0)
                self.assertEqual(row['parent_med_freqs_energy'], 5000.0)
                self.assertEqual(row['parent_high_freqs_energy'],6000.0)
                self.assertEqual(row['snippet_low_freqs_energy'], 3500.0)
                self.assertEqual(row['snippet_med_freqs_energy'], 4500.0)
                self.assertEqual(row['snippet_high_freqs_energy'],5500.0)
                

                self.assertTrue(row['snippet_filename'].endswith('test_spectroB_4_spectrogram.pickle'))

    #------------------------------------
    # testSimpleKfold 
    #-------------------
    
    
    @unittest.skipIf(TEST_ALL != True, 'skipping temporarily')
    def testSimpleKfold(self):
        '''
        Examine just the first result of a
        first of five folds
        '''

        try:
            # Simple kfold with k=5, no repeat:

            self.spectr_dataset.kfold(
                   n_splits=5,
                   n_repeats=0,
                   shuffle=False,
                   random_state=None
                   )
            # Cannot check the precise content of train and
            # validate queues, b/c they may vary. Also: sklearn
            # plays with fold lengths to make them come out even.
            
            # Just ensure that train and validate sets are
            # disjoint, and that only numbers for which we have
            # sample_ids are present:
            
            train_set = set(self.spectr_dataset.train_queue)
            val_set   = set(self.spectr_dataset.val_queue)
            all_set   = train_set.union(val_set)
            self.assertEqual(len(train_set.intersection(val_set)), 0)

            # Overlap of train + val sets should be
            # equal to the set of all sample_ids:
            fold_samples_intersect = all_set.intersection(set(self.sample_ids))
            self.assertEqual(fold_samples_intersect, set(self.sample_ids))

            # Test next() method on test set. Get
            # dict {'spectrogram' : ..., 'label : ...}:
            spectro_label_dict = next(self.spectr_dataset)
            spectro_df = spectro_label_dict['spectrogram']
            # The fake spectrograms all add to zero when
            # all elements are summed:
            sum_total = sum(sum(spectro_df.iloc[:,:].to_numpy()))
            self.assertEqual(sum_total, 0)
            
            # Due to clever setup by the author, each 
            # fake spectrogram dataframe's [0,0] element
            # corresponds to the snippet_id of the record
            # whence the row came:
            snippet_id = spectro_df.iloc[0,0]
            true_label = self.spectr_dataset.labels_from_db([snippet_id])
            self.assertEqual(spectro_label_dict['label'], true_label[0])
            
            
            # Check validation set:
            self.spectr_dataset.switch_to_split('validate')
            
            spectro_label_dict = next(self.spectr_dataset)
            sum_total = sum(sum(spectro_df.iloc[:,:].to_numpy()))
            self.assertEqual(sum_total, 0)
        finally:
            for file in self.files_to_delete:
                os.remove(file)

    #------------------------------------
    # testExhaustFolds 
    #-------------------
    
    @unittest.skipIf(TEST_ALL != True, 'skipping temporarily')
    def testExhaustFolds(self):
        '''
        Pulling all samples from all of five
        folds; check validity and termination.
        '''
        try:

            # Do 5 folds again, and pull sample-dfs/labels
            # until all folds have been exhausted:

            self.spectr_dataset.kfold(
                   n_splits=5,
                   n_repeats=0,
                   shuffle=False,
                   random_state=None
                   )
            # Have 16 samples in each of the five folds.
            # Should be able to draw 5*16=80 samples.
            # Make the loop larger than that to see whether
            # the StopIteration comes as expected. One
            # the way, collect all snippet_id so we can
            # check coverage later. We do that by knowing
            # that each fake spectrogram's element [0,0]
            # holds the snippet_id in this test setup:
            
            all_snippet_ids = set()
            for _i in range(1000):
                try:
                    df_label_dict = next(self.spectr_dataset)
                    spectrogram = df_label_dict['spectrogram']
                    # Add snippet_id to accumulation set:
                    all_snippet_ids.add(spectrogram.iloc[0,0])
                except StopIteration:
                    coverage = all_snippet_ids.intersection(set(self.sample_ids))
                    self.assertEqual(coverage, all_snippet_ids)
                    
                    # The train queue should now be empty:
                    self.assertEqual(len(self.spectr_dataset.train_queue), 0)
                    break

        finally:
            for file in self.files_to_delete:
                os.remove(file)

    #------------------------------------
    # testPullMultipleFold
    #-------------------
    
    @unittest.skipIf(TEST_ALL != True, 'skipping temporarily')
    def testPullMultipleFold(self):
        '''
        Ask for 5 folds, exhaust them all
        '''
        
        try:

            # Next: do 5 folds again, and pull sample-dfs/labels
            # until all folds have been exhausted:

            self.spectr_dataset.kfold(
                   n_splits=5,
                   n_repeats=0,
                   shuffle=False,
                   random_state=None
                   )
            # Collect snippet ids on the way (see comment
            # in analogous spot of testExhaustFolds():
            all_snippet_ids = set()
            for _i in range(1000):
                try:
                    df_label_dict = next(self.spectr_dataset)
                    spectrogram = df_label_dict['spectrogram']
                    # Add snippet_id to accumulation set:
                    all_snippet_ids.add(spectrogram.iloc[0,0])
                except StopIteration:
                    coverage = all_snippet_ids.intersection(set(self.sample_ids))
                    self.assertEqual(coverage, all_snippet_ids)
                    
                    # The train queue should now be empty:
                    self.assertEqual(len(self.spectr_dataset.train_queue), 0)
                    break
        finally:
            for file in self.files_to_delete:
                os.remove(file)

    #------------------------------------
    # testRepeatedKfolds 
    #-------------------
    
    @unittest.skipIf(TEST_ALL != True, 'skipping temporarily')
    def testRepeatedKfolds(self):
        '''
        Ask for 5 folds, repeated twice; exhaust them all
        '''
        try:

            self.spectr_dataset.kfold(
                   n_splits=5,
                   n_repeats=2,
                   shuffle=False,
                   random_state=None
                   )
            
            # To avoid clutter:
            dataset     = self.spectr_dataset
            train_queue = dataset.train_queue
            
            # Track number of folds (one was
            # consumed as part of the call to
            # kfold:
            num_folds_consumed = 1
            
            # We 'intuit' that a new fold has been
            # loaded in SpectrogramDataset's next()
            # method by observing the train_queue
            # suddenly more full than before.
            
            observed_train_queue_len = len(train_queue) 
            for _i in range(1000):
                try:
                    # Grab a spectrogram/label pair:
                    next(dataset)['label']
                    curr_train_queue_len = len(train_queue) 
                    if curr_train_queue_len >= observed_train_queue_len:
                        num_folds_consumed += 1
                        observed_train_queue_len = curr_train_queue_len
                except StopIteration:
                    break
            # We should have consumed 2 repetitions * 5 folds-per-rep = 10
            # Folds 0 to 9:
            self.assertEqual(num_folds_consumed, 9) 
        finally:
            for file in self.files_to_delete:
                os.remove(file)        

    #------------------------------------
    # testRepeatedStratified 
    #-------------------
    
    @unittest.skipIf(TEST_ALL != True, 'skipping temporarily')
    def testRepeatedStratified(self):
        '''
        Ask for 5 folds, exhaust them all.
        Each time, the number of yes and no labels must
        be the same (for even number of samples)
        '''
        
        try:

            # Do 5 folds, repeated and pull sample-dfs/labels
            # until all folds have been exhausted:

            self.spectr_dataset.kfold_stratified(
                   n_splits=5,
                   n_repeats=0,
                   shuffle=False,
                   random_state=None
                   )
            
            # To avoid clutter:
            dataset     = self.spectr_dataset
            train_queue = dataset.train_queue
            saved_train_queue = dataset.train_queue.copy()
            
            for _i in range(1000):
                try:
                    # Grab a spectrogram/label pair:
                    spectro_label_dict = next(dataset)
                    # Did we receive a new fold?
                    if self.spectr_dataset.new_train_fold_len is not None:
                        
                        # Is it truly new? Compare to the one we
                        # saved. Which sample_id did we just get?
                        spectrogram = spectro_label_dict['spectrogram']
                        
                        # Sample id is encoded in element 0,0, b/c
                        # we set the fake spectrograms up that way:
                        sample_id = spectrogram.iloc[0,0]
                        
                        # Put that sample id back into a copy of 
                        # the current train queue to get the complete
                        # fold (the next() call above already popped one:
                        
                        new_fold_train_queue = [sample_id] + list(train_queue.copy())
                        self.assertNotEqual(new_fold_train_queue, 
                                            saved_train_queue)
                        saved_train_queue = new_fold_train_queue
                        
                        # New fold; is it balanced?
                        labels = self.spectr_dataset.labels_from_db(train_queue)
                        self.assertEqual(sum(labels), len(labels) / 2)
                        
                except StopIteration:
                    break
        finally:
            for file in self.files_to_delete:
                os.remove(file)        

    #------------------------------------
    # testLen 
    #-------------------

    @unittest.skipIf(TEST_ALL != True, 'skipping temporarily')
    def testLen(self):
        self.assertEqual(len(self.spectr_dataset), len(self.sample_ids))

    #------------------------------------
    # testGetNSplit 
    #-------------------
    
    @unittest.skipIf(TEST_ALL != True, 'skipping temporarily')
    def testGetNSplit(self):
        try:
            # Next: do 5 folds, repeated and pull sample-dfs/labels
            # until all folds have been exhausted:

            self.spectr_dataset.kfold_stratified(
                   n_splits=5,
                   n_repeats=2,
                   shuffle=False,
                   random_state=None
                   )
            num_folds = self.spectr_dataset.get_n_splits()
            # Should be 10 folds: 2 repetitions * 5 folds-per-rep
            self.assertEqual(num_folds, 10)
            
        finally:
            for file in self.files_to_delete:
                os.remove(file)        



# ----------------- Utils -------------

    #------------------------------------
    # prepare_kfolds_test 
    #-------------------
    
    def prepare_kfolds_test(self):
        
        # Create 20 fake spectrogram snippet files:

        curr_dir = os.path.dirname(__file__)
        files_to_delete = []
        for i in range(0,21):
            spectro_filename = Path(curr_dir).joinpath(f'fake_spectro{i}_spectrogram.pickle')
            df = pd.DataFrame({'foo' : i, 'bar' : -i}, index=[0,1])
            df.to_pickle(spectro_filename)
            files_to_delete.append(spectro_filename)
            
        self.create_samples_in_db(files_to_delete)
        
        return files_to_delete


    #------------------------------------
    # create_samples_in_db 
    #-------------------

    def create_samples_in_db(self, files_to_delete):
            self.db.execute("DELETE FROM Samples")
            cmd = f'''INSERT INTO Samples (
                 sample_id,
                 recording_site,
                 label,
                 start_time_tick,
                 end_time_tick,
                 start_time,
                 end_time,
                 parent_low_freqs_energy,
                 parent_med_freqs_energy,
                 parent_high_freqs_energy,
                 snippet_low_freqs_energy,
                 snippet_med_freqs_energy,
                 snippet_high_freqs_energy,
                 snippet_filename
                 )
                 VALUES (0, "nouab", 1, 20, 30, 40, 50, 100, 200, 300, 400, 500, 600, "{files_to_delete[0]}"),
                        (1, "nouab", 0, 20, 30, 40, 50, 100, 200, 300, 400, 500, 600, "{files_to_delete[1]}"),
                        (2, "nouab", 1, 20, 30, 40, 50, 100, 200, 300, 400, 500, 600, "{files_to_delete[2]}"),
                        (3, "nouab", 0, 20, 30, 40, 50, 100, 200, 300, 400, 500, 600, "{files_to_delete[3]}"),
                        (4, "nouab", 1, 20, 30, 40, 50, 100, 200, 300, 400, 500, 600, "{files_to_delete[4]}"),
                        (5, "nouab", 0, 20, 30, 40, 50, 100, 200, 300, 400, 500, 600, "{files_to_delete[5]}"),
                        (6, "nouab", 1, 20, 30, 40, 50, 100, 200, 300, 400, 500, 600, "{files_to_delete[6]}"),
                        (7, "nouab", 0, 20, 30, 40, 50, 100, 200, 300, 400, 500, 600, "{files_to_delete[7]}"),
                        (8, "nouab", 1, 20, 30, 40, 50, 100, 200, 300, 400, 500, 600, "{files_to_delete[8]}"),
                        (9, "nouab", 0, 20, 30, 40, 50, 100, 200, 300, 400, 500, 600, "{files_to_delete[9]}"),
                        (10, "nouab", 1, 20, 30, 40, 50, 100, 200, 300, 400, 500, 600, "{files_to_delete[10]}"),
                        (11, "nouab", 0, 20, 30, 40, 50, 100, 200, 300, 400, 500, 600, "{files_to_delete[11]}"),
                        (12, "nouab", 1, 20, 30, 40, 50, 100, 200, 300, 400, 500, 600, "{files_to_delete[12]}"),
                        (13, "nouab", 0, 20, 30, 40, 50, 100, 200, 300, 400, 500, 600, "{files_to_delete[13]}"),
                        (14, "nouab", 1, 20, 30, 40, 50, 100, 200, 300, 400, 500, 600, "{files_to_delete[14]}"),
                        (15, "nouab", 0, 20, 30, 40, 50, 100, 200, 300, 400, 500, 600, "{files_to_delete[15]}"),
                        (16, "nouab", 1, 20, 30, 40, 50, 100, 200, 300, 400, 500, 600, "{files_to_delete[16]}"),
                        (17, "nouab", 0, 20, 30, 40, 50, 100, 200, 300, 400, 500, 600, "{files_to_delete[17]}"),
                        (18, "nouab", 1, 20, 30, 40, 50, 100, 200, 300, 400, 500, 600, "{files_to_delete[18]}"),
                        (19, "nouab", 0, 20, 30, 40, 50, 100, 200, 300, 400, 500, 600, "{files_to_delete[19]}"),
                        (20, "nouab", 1, 20, 30, 40, 50, 100, 200, 300, 400, 500, 600, "{files_to_delete[20]}");
            '''
            self.db.execute(cmd)


# ----------------- Main --------------


if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()