import matplotlib.pyplot as plt
import numpy as np
import torch
import aifc
from scipy import signal
from torch.utils import data
from torchvision import transforms
from scipy.misc import imresize
import pandas as pd
import os
from torch.utils.data.sampler import SubsetRandomSampler
from sklearn.preprocessing import StandardScaler, MinMaxScaler
import glob

Noise_Stats_Directory = "../elephant_dataset/eleph_dataset/Noise_Stats/"

def get_loader(data_dir,
               batch_size,
               random_seed=8,
               norm="norm",
               scale=False,
               augment=False,
               shuffle=True,
               num_workers=16,
               pin_memory=False):
    """
    Utility function for loading and returning train and valid
    multi-process iterators.
    If using CUDA, num_workers should be set to 1 and pin_memory to True.
    Params
    ------
    - data_dir: path directory to the dataset.
    - batch_size: how many samples per batch to load.
    - random_seed: fix seed for reproducibility.
    - augment: whether data augmentation scheme. Only applied on the train split.
    - valid_size: percentage split of the training set used for
      the validation set. Should be a float in the range [0, 1].
    - shuffle: whether to shuffle the train/validation indices.
    - num_workers: number of subprocesses to use when loading the dataset.
    - pin_memory: whether to copy tensors into CUDA pinned memory. Set it to
      True if using GPU.
    - data_file_paths: If you know what particular data file names you want to load, 
      pass them in as a list of strings.
    Returns
    -------
    - train_loader: training set iterator.
    - valid_loader: validation set iterator.
    """
    # Note here we could do some data preprocessing!
    # define transform
    dataset = ElephantDataset(data_dir, preprocess=norm, scale=scale)
    
    print('Size of dataset at {} is {} samples'.format(data_dir, len(dataset)))

    # Set the data_loader random seed for reproducibility.
    # Should do some checks on this
    def _init_fn(worker_id):
        # We probably do not want every worker to have 
        # the same random seed or else they may do the same 
        # thing?
        np.random.seed(int(random_seed) + worker_id)

    data_loader = torch.utils.data.DataLoader(dataset, batch_size=batch_size, 
        shuffle=shuffle, num_workers=num_workers, pin_memory=pin_memory, worker_init_fn=_init_fn)

    return data_loader

def get_loader_fuzzy(data_dir,
               batch_size,
               random_seed=8,
               norm="norm",
               scale=False,
               include_boundaries=False,
               augment=False,
               shuffle=True,
               num_workers=16,
               pin_memory=False):
    """
    Utility function for loading and returning train and valid
    multi-process iterators.
    If using CUDA, num_workers should be set to 1 and pin_memory to True.
    Params
    ------
    - data_dir: path directory to the dataset.
    - batch_size: how many samples per batch to load.
    - random_seed: fix seed for reproducibility.
    - augment: whether data augmentation scheme. Only applied on the train split.
    - valid_size: percentage split of the training set used for
      the validation set. Should be a float in the range [0, 1].
    - shuffle: whether to shuffle the train/validation indices.
    - num_workers: number of subprocesses to use when loading the dataset.
    - pin_memory: whether to copy tensors into CUDA pinned memory. Set it to
      True if using GPU.
    - data_file_paths: If you know what particular data file names you want to load, 
      pass them in as a list of strings.
    Returns
    -------
    - train_loader: training set iterator.
    - valid_loader: validation set iterator.
    """
    # Note here we could do some data preprocessing!
    # define transform
    dataset = ElephantDatasetFuzzy(data_dir, preprocess=norm, scale=scale, include_boundaries=include_boundaries)
    
    print('Size of dataset at {} is {} samples'.format(data_dir, len(dataset)))

    # Set the data_loader random seed for reproducibility.
    # Should do some checks on this
    def _init_fn(worker_id):
        # Assign each worker its own seed
        np.random.seed(int(random_seed) + worker_id)

    data_loader = torch.utils.data.DataLoader(dataset, batch_size=batch_size, 
        shuffle=shuffle, num_workers=num_workers, pin_memory=pin_memory, worker_init_fn=_init_fn)

    return data_loader

"""
    Notes
    - Preprocess = Norm, Scale = False ===> seems bad
    - Preprocess = Norm, Scale = True ===> Works well on small dataset!
    - Preprocess = Scale, Scale = False ===> Has quite a bit of trouble over fitting small dataset compared to other but eventually can
    - Preprocess = Scale, Scale = True ===> Has quite a bit of trouble over fitting small dataset compared to other and bad val acc!
    - Preprocess = ChunkNorm, Scale = False ===> Very slow and bad
    - Preprocess = ChunkNorm, Scale = True ===> Similar to Norm with scale
    - Preprocess = None, Scale = True ====> No worky
    - Preprocess = Scale range (-1, 1), Scale = True ===> Overfit but huge variance issue
"""
class ElephantDataset(data.Dataset):
    def __init__(self, data_path, transform=None, preprocess="norm", scale=False):
        # Plan: Load in all feature and label names to create a list
        self.data_path = data_path
        self.user_transforms = transform
        self.preprocess = preprocess
        self.scale = scale

        # Probably should not have + "**/" after data_path? It seems like 
        # we are passing the exact datapths anyways! Also why recursive?
        self.features = glob.glob(data_path + "/" + "*features*", recursive=False)
        self.initialize_labels()

        assert len(self.features) == len(self.labels)

        print("Dataset from path {}".format(data_path))
        print("ElephantDataset number of features {} and number of labels {}".format(len(self.features), len(self.labels)))
        print('Normalizing with {} and scaling {}'.format(preprocess, scale))
        print("Shape of a feature is {} and a label is {}".format(self[0][0].shape, self[0][1].shape))

    def initialize_labels(self):
        self.labels = []
        for feature_path in self.features:
            feature_parts = feature_path.split("features")
            self.labels.append(glob.glob(feature_parts[0] + "labels" + feature_parts[1])[0])


    def __len__(self):
        return len(self.features)

    """
    Return a single element at provided index
    """
    def __getitem__(self, index):
        feature = np.load(self.features[index])
        label = np.load(self.labels[index])

        feature = self.apply_transforms(feature)
        if self.user_transforms:
            feature = self.user_transforms(feature)
            
        # Honestly may be worth pre-process this
        feature = torch.from_numpy(feature).float()
        label = torch.from_numpy(label).float()


        return feature, label, self.features[index] # Include the data file

    def apply_transforms(self, data):
        if self.scale:
            data = 10 * np.log10(data)

        # Normalize Features
        if self.preprocess == "norm":
            data = (data - np.mean(data)) / np.std(data)
        elif self.preprocess == "globalnorm":
            data = (data - 132.228) / 726.319 # Calculated these over the training dataset 

        return data

        # elif self.preprocess == "Scale":
        #     scaler = MinMaxScaler()
        #     # Scale features for each training example
        #     # to be within a certain range. Preserves the
        #     # relative distribution of each feature. Here
        #     # each feature is the different frequency band
        #     for i in range(self.features.shape[0]):
        #         self.features[i, :, :] = scaler.fit_transform(self.features[i,:,:].astype(np.float32))
        #     #num_ex = self.features.shape[0]
        #     #seq_len = self.features.shape[1]
        #     #self.features = self.features.reshape(num_ex * seq_len, -1)
        #     #self.features = scaler.fit_transform(self.features)
        #     #self.features = self.features.reshape(num_ex, seq_len, -1)
        # elif self.preprocess == "ChunkNorm":
        #     for i in range(self.features.shape[0]):
        #         self.features[i, :, :] = (self.features[i, :, :] - np.mean(self.features[i, :, :])) / np.std(self.features[i, :, :])
        # elif self.preprocess == "BackgroundS":
        #     # Load in the pre-calculated mean,std,etc.
        #     if not scale:
        #         mean_noise = np.load(Noise_Stats_Directory + "mean.npy")
        #         std_noise = np.load(Noise_Stats_Directory + "std.npy")
        #     else:
        #         mean_noise = np.load(Noise_Stats_Directory + "mean_log.npy")
        #         std_noise = np.load(Noise_Stats_Directory + "std_log.npy")

        #     self.features = (self.features - mean_noise) / std_noise
        # elif self.preprocess == "BackgroundM":
        #     # Load in the pre-calculated mean,std,etc.
        #     if not scale:
        #         mean_noise = np.load(Noise_Stats_Directory + "mean.npy")
        #         median_noise = np.load(Noise_Stats_Directory + "median.npy")
        #     else:
        #         mean_noise = np.load(Noise_Stats_Directory + "mean_log.npy")
        #         median_noise = np.load(Noise_Stats_Directory + "median_log.npy")

        #     self.features = (self.features - mean_noise) / median_noise
        # elif self.preprocess == "FeatureNorm":
        #     self.features = (self.features - np.mean(self.features, axis=(0, 1))) / np.std(self.features, axis=(0,1))


class ElephantDatasetFuzzy(data.Dataset):
    def __init__(self, data_path, preprocess="norm", scale=False, transform=None, include_boundaries=False):
        # Plan: Load in all feature and label names to create a list
        self.data_path = data_path
        self.user_transforms = transform
        self.preprocess = preprocess
        self.scale = scale
        self.include_boundaries = include_boundaries

        #self.features = glob.glob(data_path + "/" + "*features*", recursive=True)
        #self.initialize_labels()
        self.pos_features = glob.glob(data_path + "/" + "*_features_*", recursive=True)
        self.neg_features = glob.glob(data_path + "/" + "*_neg-features_*", recursive=True)
        self.intialize_data(init_pos=True, init_neg=True)

        assert len(self.features) == len(self.labels)
        if self.include_boundaries:
            assert len(self.features) == len(self.boundary_masks)

        print("ElephantDataset number of features {} and number of labels {}".format(len(self.features), len(self.labels)))
        print('Normalizing with {} and scaling {}'.format(preprocess, scale))

    def initialize_labels(self):
        self.labels = []
        self.boundary_masks = []
        for feature_path in self.features:
            feature_parts = feature_path.split("features")
            # Just out of curiosity
            self.labels.append(glob.glob(feature_parts[0] + "labels" + feature_parts[1])[0])
            if self.include_boundaries:
                self.boundary_masks.append(glob.glob(feature_parts[0] + "boundary-masks" + feature_parts[1])[0])

    def set_pos_features(self, pos_features):
        print("Length of pos_features was {} and is now {} ".format(len(self.pos_features), len(pos_features)))
        self.pos_features = pos_features
        self.intialize_data(init_pos=True, init_neg=False)

    def set_neg_features(self, neg_features):
        print("Length of neg_features was {} and is now {} ".format(len(self.neg_features), len(neg_features)))
        self.neg_features = neg_features
        self.intialize_data(init_pos=False, init_neg=True)

    def set_featues(self, pos_features, neg_features):
        print("Length of pos_features was {} and is now {} ".format(len(self.pos_features), len(pos_features)))
        print("Length of neg_features was {} and is now {} ".format(len(self.neg_features), len(neg_features)))
        self.pos_features = pos_features
        self.neg_features = neg_features
        self.intialize_data(init_pos=True, init_neg=True)

    def intialize_data(self, init_pos=True, init_neg=True):
        """
            Initialize both the positive and negative label and boundary
            mask data arrays if indicated by the initialization flags 
            'init_pos' and 'init_neg'. After initializing any necessary
            data, combine the positive and negative examples!
        """
        # Initialize the positive examples
        if init_pos:
            self.pos_labels = []
            self.pos_boundary_masks = []
            for feature_path in self.pos_features:
                feature_parts = feature_path.split("features")
                # Just out of curiosity
                self.pos_labels.append(glob.glob(feature_parts[0] + "labels" + feature_parts[1])[0])
                if self.include_boundaries:
                    self.pos_boundary_masks.append(glob.glob(feature_parts[0] + "boundary-masks" + feature_parts[1])[0])

        # Initialize the negative examples
        if init_neg:
            self.neg_labels = []
            self.neg_boundary_masks = []
            for feature_path in self.neg_features:
                feature_parts = feature_path.split("features")
                # Just out of curiosity
                self.neg_labels.append(glob.glob(feature_parts[0] + "labels" + feature_parts[1])[0])
                if self.include_boundaries:
                    self.neg_boundary_masks.append(glob.glob(feature_parts[0] + "boundary-masks" + feature_parts[1])[0])

        # Combine the positive and negative examples!
        self.features = self.pos_features + self.neg_features
        self.labels = self.pos_labels + self.neg_labels
        if self.include_boundaries:
            self.boundary_masks = self.pos_boundary_masks + self.neg_boundary_masks


    def __len__(self):
        return len(self.features)

    """
    Return a single element at provided index
    """
    def __getitem__(self, index):
        feature = np.load(self.features[index])
        label = np.load(self.labels[index])

        feature = self.apply_transforms(feature)
        if self.user_transforms:
            feature = self.user_transforms(feature)
            
        # Honestly may be worth pre-process this
        feature = torch.from_numpy(feature).float()
        label = torch.from_numpy(label).float()

        # Return the boundary masks
        if self.include_boundaries:
            masks = np.load(self.boundary_masks[index])
            # Cast to a bool tensor to allow for array masking
            masks = torch.from_numpy(masks) == 1

            return feature, label, masks, self.features[index]
        else:
            return feature, label, self.features[index] # Include the data file

    def apply_transforms(self, data):
        if self.scale:
            data = 10 * np.log10(data)

        # Normalize Features
        if self.preprocess == "norm":
            data = (data - np.mean(data)) / np.std(data)
        elif self.preprocess == "globalnorm":
            data = (data - 132.228) / 726.319 # Calculated these over the training dataset 

        return data


"""
    Dataset for full test length audio
    NEED TO FIX THIS!!
"""
class ElephantDatasetFull(data.Dataset):
    def __init__(self, spectrogram_files, label_files, gt_calls, preprocess="norm", scale=True):

        self.specs = spectrogram_files
        self.labels = label_files
        self.gt_calls = gt_calls # This is the .txt file that contains start and end times of calls
        self.preprocess = preprocess
        self.scale = scale
        
        print('Normalizing with {} and scaling {}'.format(preprocess, scale))


    def __len__(self):
        return len(self.specs)


    def transform(self, spectrogram): # We need to fix this probably!!!
        # Potentially include other transforms
        if self.scale:
            spectrogram = 10 * np.log10(spectrogram)

        # Quite janky, but for now we will do the normalization 
        # seperately!
        '''
        # Normalize Features
        if self.preprocess == "norm": # Only have one training example so is essentially chunk norm
            spectrogram = (spectrogram - np.mean(spectrogram)) / np.std(spectrogram)
        elif preprocess == "Scale":
            scaler = MinMaxScaler()
            # Scale features for each training example
            # to be within a certain range. Preserves the
            # relative distribution of each feature. Here
            # each feature is the different frequency band
            spectrogram = scaler.fit_transform(spectrogram.astype(np.float32))
        elif self.preprocess == "ChunkNorm":
            spectrogram = (spectrogram - np.mean(spectrogram)) / np.std(spectrogram)
        elif self.preprocess == "BackgroundS":
            # Load in the pre-calculated mean,std,etc.
            if not scale:
                mean_noise = np.load(Noise_Stats_Directory + "mean.npy")
                std_noise = np.load(Noise_Stats_Directory + "std.npy")
            else:
                mean_noise = np.load(Noise_Stats_Directory + "mean_log.npy")
                std_noise = np.load(Noise_Stats_Directory + "std_log.npy")

            spectrogram = (spectrogram - mean_noise) / std_noise
        elif self.preprocess == "BackgroundM":
            # Load in the pre-calculated mean,std,etc.
            if not scale:
                mean_noise = np.load(Noise_Stats_Directory + "mean.npy")
                median_noise = np.load(Noise_Stats_Directory + "median.npy")
            else:
                mean_noise = np.load(Noise_Stats_Directory + "mean_log.npy")
                median_noise = np.load(Noise_Stats_Directory + "median_log.npy")

            spectrogram = (spectrogram - mean_noise) / median_noise
        elif self.preprocess == "FeatureNorm":
            spectrogram = (spectrogram - np.mean(spectrogram, axis=1)) / np.std(spectrogram, axis=1)
        '''
        return spectrogram

    """
    Return a single element at provided index
    """
    def __getitem__(self, index):
        spectrogram_path = self.specs[index]
        label_path = self.labels[index]
        gt_call_path = self.gt_calls[index]

        spectrogram = np.load(spectrogram_path).transpose()
        label = np.load(label_path)

        spectrogram = self.transform(spectrogram)
        #spectrogram = np.expand_dims(spectrogram, axis=0) # Add the batch dimension so we can apply our lstm!
            
        # Honestly may be worth pre-process this
        #spectrogram = torch.from_numpy(spectrogram)
        #label = torch.from_numpy(label)

        return spectrogram, label, gt_call_path


