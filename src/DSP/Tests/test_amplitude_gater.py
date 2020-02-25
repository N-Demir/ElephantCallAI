'''
Created on Feb 21, 2020

@author: paepcke
'''

import sys, os
import unittest

sys.path.append(os.path.dirname(__file__))
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from DSP.amplitude_gating import AmplitudeGater
import numpy as np
from tempfile import NamedTemporaryFile

from scipy.io import wavfile

TEST_ALL = True
#TEST_ALL = False

class Test(unittest.TestCase):

    def setUp(self):
        unittest.TestCase.setUp(self)
        
        self.samples_normal_immediate_start = np.array([1,0,0,10,11,0,0,0,0,20])
        self.samples_normal_immediate_start_sig_index = np.array([0,3,4,9])

        self.samples_for_attack_and_release = np.array([0,0,0,0,1,0.8,0,0,0,0,0,0,0,0,0.4])
        self.samples_for_attack_and_release_sig_index = np.array([4,14])
        
        # Compress everything down so we only need small vectors
        # like the ones above: we'll take 2msecs for the attack/release: 
        # Attacks and releases take 2msecs, rather than the default 50msec:
        AmplitudeGater.ATTACK_RELEASE_MSECS = 2
        self.gater = AmplitudeGater(None, # No .wav file 
                                    testing=True,
                                    framerate=2000 # frames per second
                                    )
    #------------------------------------
    # testNextBurst 
    #-------------------

    @unittest.skipIf(not TEST_ALL, "Temporarily skipping")
    def testNextBurst(self):
        sample_npa = self.samples_normal_immediate_start
        signal_index = self.samples_normal_immediate_start_sig_index
        self.gater.samples_na   = sample_npa
        self.gater.signal_index = signal_index

        burst1 = self.gater.next_burst(None)
        self.assertEqual(burst1.start, 0)
        self.assertEqual(burst1.stop, 1)
        self.assertEqual(burst1.signal_index_pt, 1)
        
        burst2 = self.gater.next_burst(burst1)
        self.assertEqual(burst2.start, 3)
        self.assertEqual(burst2.stop, 5)
        self.assertEqual(burst2.averaging_start, 0)
        self.assertEqual(burst2.averaging_stop, 3)
        self.assertEqual(burst2.signal_index_pt, 3)
        
        burst3 = self.gater.next_burst(burst2)
        self.assertEqual(burst3.start, 9)
        self.assertEqual(burst3.stop, 10)
        self.assertEqual(burst3.attack_start, 5)
        self.assertIsNone(burst3.signal_index_pt)
        
        print(burst1, burst2, burst3)
        
    #------------------------------------
    # testGapAveraging 
    #-------------------

    @unittest.skipIf(not TEST_ALL, "Temporarily skipping")
    def testGapAveraging(self):
        sample_npa = self.samples_normal_immediate_start
        signal_index = self.samples_normal_immediate_start_sig_index
        self.gater.samples_na   = sample_npa
        self.gater.signal_index = signal_index

        burst1 = self.gater.next_burst(None)
        burst2 = self.gater.next_burst(burst1)
        new_sample_na = self.gater.average_the_gap(burst2, sample_npa)
        
        self.assertEqual(new_sample_na.all(), 
                         np.array([ 1,  6,  6, 10, 11,  0,  0,  0,  0, 20]).all()
                         )        
    
    #------------------------------------
    # testPlaceAttack 
    #-------------------
      
    @unittest.skipIf(not TEST_ALL, "Temporarily skipping")
    def testPlaceAttack(self):
        
        sample_npa = self.samples_normal_immediate_start
        signal_index = self.samples_normal_immediate_start_sig_index
        self.gater.samples_na   = sample_npa
        self.gater.signal_index = signal_index

        burst1 = self.gater.next_burst(None)
        burst2 = self.gater.next_burst(burst1)
        burst3 = self.gater.next_burst(burst2)

        new_sample_na = self.gater.place_attack(burst3, sample_npa)
        
        
        self.assertEqual(new_sample_na.all(), 
                         np.array([ 1,  6,  6, 10, 11,  0,  7.86938681, 12.64241118, 15.5373968, 20]).all()
                         )        

    #------------------------------------
    # testPlaceRelease
    #-------------------
      
    @unittest.skipIf(not TEST_ALL, "Temporarily skipping")
    def testPlaceRelease(self):
        
        sample_npa = self.samples_normal_immediate_start
        signal_index = self.samples_normal_immediate_start_sig_index
        self.gater.samples_na   = sample_npa
        self.gater.signal_index = signal_index

        burst1 = self.gater.next_burst(None)
        burst2 = self.gater.next_burst(burst1)
        burst3 = self.gater.next_burst(burst2)

        new_sample_na = self.gater.place_attack(burst3, sample_npa)
        
        
        self.assertEqual(new_sample_na.all(), 
                         np.array([ 1,  6,  6, 10, 11,  0,  7.86938681, 12.64241118, 15.5373968, 20]).all()
                         )      
        
    #------------------------------------
    # testAttackAndRelease 
    #-------------------
    
    @unittest.skipIf(not TEST_ALL, "Temporarily skipping")
    def testAttackAndRelease(self):
        sample_npa   = self.samples_for_attack_and_release
        self.gater.samples_na   = sample_npa
        
        new_sample_na = self.gater.amplitude_gate(sample_npa, -20)
        
        self.assertEqual(new_sample_na.all(),
                        np.array([0.        , 0.39346934, 0.63212056, 0.77686984, 1.,
                                  0.8       , 0.0077687 , 0.00632121, 0.00393469, 0.,
                                  0.        , 0.15738774, 0.25284822, 0.31074794, 0.4]
                                  ).all()
                        )
 
    #------------------------------------
    # test_wav_read_write
    #-------------------

    @unittest.skipIf(not TEST_ALL, "Temporarily skipping")
    def test_wav_read_write(self):
        
        test_sound_path = os.path.join(os.path.dirname(__file__), 'testsound.wav')
        
        (framerate, sound_data) = wavfile.read(test_sound_path)
        
        # Get a tmp file and write the data back out:
        tmp_file_obj = NamedTemporaryFile(mode='w+b',
                                          prefix='test_amp_gate',
                                          suffix='.wav')
        tmp_file_obj.close()
        tmp_file_nm = tmp_file_obj.name
        
        wavfile.write(tmp_file_nm, framerate, sound_data) 
        
        # Original file and just-written file equal?
        
        orig_file_len = os.stat(test_sound_path).st_size
        tmp_file_len  = os.stat(tmp_file_nm).st_size

        try:
            self.assertEqual(tmp_file_len, orig_file_len)
            
            # Check the metadata:
            
            wave_read_obj = self.gater.wave_fd(tmp_file_nm)
            # Get all in one tuple:
            #(nchannels, sampwidth,framerate,nframes,comptype,compname)
            tmp_metadata = wave_read_obj.getparams()
            self.assertTupleEqual(tmp_metadata,
                                  (num_channels,
                                   sample_width,
                                   framerate,
                                   num_frames,
                                   compress_type,
                                   compress_name
                                   )
                                  )

        finally:
            os.remove(tmp_file_obj.name)

 
    #------------------------------------
    # testPlotting
    #-------------------

    @unittest.skipIf(not TEST_ALL, "Temporarily skipping")
    def testPlotting(self):
        
        sample_npa   = self.samples_for_attack_and_release
        self.gater.samples_na   = sample_npa
        
        new_sample_na = self.gater.amplitude_gate(sample_npa, -20)

        self.gater.plot(np.arange(new_sample_na.size),
                      new_sample_na,
                      title=f"Amplitude-Gated for {self.samples_for_attack_and_release}",
                      xlabel='Sample Index', 
                      ylabel='Voltage'
                      )


# --------------------------- Main ---------------
        
if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()