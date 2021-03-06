'''
Idea is to iterate through data, find call, get the length of the call,
then make a single training chunk as a 1/2 time before call call then 1/2 time
after call. Thus dataset will be equal
'''
'''
Try for now to make all of the calls the same length
'''

import os,math
import numpy as np
from sklearn.model_selection import train_test_split
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
import matplotlib.cm
import matplotlib
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
import matplotlib.ticker as plticker
import matplotlib.patches as patches
from mpl_toolkits.axes_grid1 import make_axes_locatable, axes_size
import random
from random import shuffle 
import math
import multiprocessing
import time
from functools import partial


MFCC_Data = './Processed_data_MFCC/'
Spect_Data = './Processed_data/'
# Quatro
#Spect_Data = '/home/ndemir/ElephantCallAI/elephant_dataset/Processed_data/'
full_call_directory = 'call/'
activate_directory = 'activate/'

test_directory = './Test'
train_directory = './Train'

#feature_set = []
#label_set = []

seed = 8
random.seed(seed)
TEST_SIZE = 0.2

# Determines the size of the chunks that we are creating around the elephant
# Call. This refers to number of columns in the spectogram. Based on the 
# Creation of the spectogram this equates to 25.5 second windows
# Definitely should do some padding then on both sides and do a random crop
# so the call is not always centered! 
FRAME_LENGTH = 256

# Define whether we label the call itself
# or label when the call ends. If True labels
# when the call ends
USE_POST_CALL_LABEL = False
# Number of time steps to add the 1
ACTIVATE_TIME = 5 if USE_POST_CALL_LABEL else 0

USE_MFCC_FEATURES = False

VERBOSE = False

NEG_FACT = 2


def makeChunk(start_index,feat_mat,label_mat):
    # 1. Determine length of call in number of indices
    length_of_call = 0

    for j in range(start_index,label_mat.shape[0]):
        if label_mat[j] != 1:
            break
        length_of_call += 1

    # Figure out how much to go before and after. We do not want to got .5 
    # because then the chunks are of different sizes
    # Randomly place the call in the window for now? Should use data_augmentation later
    # We want the whole call to be in there plus the labeling of the "activate"
    padding_frame = FRAME_LENGTH - length_of_call #- ACTIVATE_TIME
    # if padding_frame is neg skip call
    # but still want to go to the next!!
    if padding_frame < 0:
        print ("skipping")
        return start_index + length_of_call + 1, None, None

    
    # Randomly split the pad to before and after
    split = np.random.randint(0, padding_frame + 1)

    # Do some stuff to avoid the front and end!
    chunk_start_index = start_index - split
    chunk_end_index  = start_index + length_of_call + ACTIVATE_TIME + padding_frame - split
    # Do some quick voodo - assume cant have issue where 
    # the window of 64 frames is lareger than the sound file!
    if (chunk_start_index < 0):
        # Amount to transfer to end
        chunk_start_index = 0
        chunk_end_index = FRAME_LENGTH
    if (chunk_end_index >= label_mat.shape[0]):
        chunk_end_index = label_mat.shape[0]
        chunk_start_index = label_mat.shape[0] - FRAME_LENGTH

    if (chunk_end_index - chunk_start_index != FRAME_LENGTH):
        print ("fuck")
        quit()
    return_features = feat_mat[chunk_start_index: chunk_end_index, :]
    return_labels = label_mat[chunk_start_index: chunk_end_index]

    if VERBOSE:
        display_call(return_features, return_labels)

    # Note make sure that we skip over the call and the activate labels
    return start_index + length_of_call + 1, return_features, return_labels

def generate_empty_chunks(n, features, labels):
    """
        Generate n empty data chunks by uniformally sampling 
        time sections with no elephant calls present
    """
    # Step through the labels vector and collect the indeces from
    # which we can define a window with now elephant call
    # i.e. all start indeces such that the window (start, start + window_sz)
    # does not contain an elephant call
    valid_starts = []
    # Step backwards and keep track of how far away the
    # last elephant call was
    last_elephant = 0  # For now is the size of the window
    for i in range(labels.shape[0] - 1, -1, -1):
        last_elephant += 1

        # Check if we encounter an elephant call
        if (labels[i] == 1):
            last_elephant = 0

        # If we haven't seen an elephant call
        # for a chunk size than record this index
        if (last_elephant >= FRAME_LENGTH):
            valid_starts.append(i)

    # Generate num_empty uniformally random 
    # empty chunks
    empty_features = []
    empty_labels = []

    for i in range(n):
        # Generate a valid empty start chunk
        # index by randomly sampling from our
        # ground truth labels
        start = np.random.choice(valid_starts)

        spectrum = features[start: start + FRAME_LENGTH, :]
        data_labels = labels[start : start + FRAME_LENGTH]
        # Make sure that no call exists in the chunk
        assert(np.sum(data_labels) == 0)

        if VERBOSE:
            visualize(spectrum, labels=data_labels)

        # We want spectrograms to be time x freq
        empty_features.append(spectrum)
        empty_labels.append(data_labels)

    return empty_features, empty_labels


def makeDataSet(featFile,labFile):
    # 1. Open both feature file and label file as np arrays
    feature_file = np.genfromtxt(featFile,delimiter=',').transpose()
    label_file = np.genfromtxt(labFile,delimiter=',')

    feature_set = []
    label_set = []
    # 2. Now iterate through label file, when find a call, pass to make chunk,
    # which will return new starting index, the feature chunk and label chunk
    skip_to_index = False
    for i in range(label_file.shape[0]):
        if skip_to_index:
            skip_to_index = False if i == skip else True
            continue
        if label_file[i] == 1:
            skip,feature_chunk, label_chunk = makeChunk(i,feature_file,label_file)
            # Skip this call because we are at the end of the file
            if (feature_chunk is not None):  
                feature_set.append(feature_chunk)
                label_set.append(label_chunk)
            skip_to_index = True

    # Add the negative samples
    empty_features, empty_labels = generate_empty_chunks(len(feature_set) * NEG_FACT,
            feature_file, label_file)
    feature_set.extend(empty_features)
    label_set.extend(empty_labels)

    return feature_set, label_set

# Assumes that we are making chunks going backwards
def makeChunkActivate(activate_index,feat_mat,label_mat):
    # 1. Determine length of call in number of indices
    start_index = label_mat[activate_index, 1]

    # Determine where the call actually ends
    # To ultimately get the length of the call
    i = activate_index
    while i >= 0 and label_mat[i, 1] == start_index:
        i -= 1

    call_end = i
    length_of_call = call_end - start_index

    # Skip a call at the very end if the activate labels can't fit
    if (start_index + length_of_call + ACTIVATE_TIME >= label_mat.shape[0]):
        return start_index - 1, None, None

    # Figure out how much to go before and after. We do not want to got .5 
    # because then the chunks are of different sizes
    # Randomly place the call in the window for now? Should use data_augmentation later
    # We want the whole call to be in there plus the labeling of the "activate"
    padding_frame = FRAME_LENGTH - length_of_call - ACTIVATE_TIME
    # if padding_frame is neg skip call
    # but still want to go to the next!!
    if padding_frame < 0:
        print ("skipping")
        return start_index - 1, None, None
    
    # Randomly split the pad to before and after
    split = np.random.randint(0, padding_frame + 1)

    # Do some stuff to avoid the front and end!
    chunk_start_index = start_index - split
    chunk_end_index  = start_index + length_of_call + ACTIVATE_TIME + (padding_frame - split)
    # Edge case if window is near the beginning or end of the file
    # the window of 64 frames is larger than the sound file!
    if (chunk_start_index < 0):
        # Make the window start at 0
        chunk_start_index = 0
        chunk_end_index = FRAME_LENGTH
    if (chunk_end_index >= label_mat.shape[0]):
        chunk_end_index = label_mat.shape[0]
        chunk_start_index = label_mat.shape[0] - FRAME_LENGTH

    chunk_start_index = int(chunk_start_index); chunk_end_index = int(chunk_end_index)

    if (chunk_end_index - chunk_start_index != 64):
        print ("fuck")
        quit()

    return_features = feat_mat[chunk_start_index: chunk_end_index, :]
    return_labels = label_mat[chunk_start_index: chunk_end_index, 0]

    if VERBOSE:
        display_call(return_features, return_labels)

    # Note make sure that we skip over the call and the activate labels
    return start_index - 1, return_features, return_labels


def display_call(features, labels):
    """
        Assumes features is of shape (time, freq)
    """
    fig, (ax1, ax2) = plt.subplots(2,1)
    new_features = features.T
    if not USE_MFCC_FEATURES:
        new_features = np.flipud(10*np.log10(features).T)
    min_dbfs = new_features.flatten().mean()
    max_dbfs = new_features.flatten().mean()
    min_dbfs = np.maximum(new_features.flatten().min(),min_dbfs-2*new_features.flatten().std())
    max_dbfs = np.minimum(new_features.flatten().max(),max_dbfs+6*new_features.flatten().std())
    ax1.imshow(np.flipud(new_features), cmap="magma_r", vmin=min_dbfs, vmax=max_dbfs, interpolation='none', origin="lower", aspect="auto")
    print (labels)
    ax2.plot(np.arange(labels.shape[0]), labels)

    plt.show()
    

def extend_activate_label(labFile):
    """
        Make the activate label for each call have 
    """

    for i in reversed(range(labFile.shape[0])):
        # Extend the file label!
        if (labFile[i, 0] == 1):
            # Copy the start index 
            # So we know where the call 
            # started that is ending for
            # creating chunks
            start = labFile[i, 1]
            for j in range(ACTIVATE_TIME):
                if (i + j >= labFile.shape[0]):
                    break
                labFile[i + j, 0] = 1
                labFile[i + j, 1] = start

def makeDataSetActivate(featFile,labFile):
    # 1. Open both feature file and label file as np arrays
    feature_file = np.genfromtxt(featFile,delimiter=',').transpose()
    label_file = np.genfromtxt(labFile,delimiter=',')

    feature_set = []
    label_set = []
    # Extend our labels to have the right number of activate labels
    extend_activate_label(label_file)
    # 2. Now iterate through label file, when find a call, pass to make chunk,
    # which will return new starting index, the feature chunk and label chunk
    skip_to_index = False
    for i in reversed(range(label_file.shape[0])):
        if skip_to_index:
            skip_to_index = False if i == skip else True
            continue
        if label_file[i, 0] == 1:
            skip,feature_chunk, label_chunk = makeChunkActivate(i,feature_file,label_file)
            # Skip this call because we are at the end of the file
            if (feature_chunk is not None):  
                feature_set.append(feature_chunk)
                label_set.append(label_chunk)
            skip_to_index = True

    return feature_set, label_set

# 1. Iterate through all files in output
data_directory = MFCC_Data if USE_MFCC_FEATURES else Spect_Data
data_directory += activate_directory if USE_POST_CALL_LABEL else full_call_directory

datafiles = []
for i,fileName in enumerate(os.listdir(data_directory)):
    if fileName[0:4] == 'Data':
        datafiles.append(fileName)

# Shuffle the files before train test split
shuffle(datafiles)

split_index = math.floor(len(datafiles) * (1 - TEST_SIZE))
train_data_files = datafiles[:split_index]
test_data_files = datafiles[split_index:]

EXTRACT_TEST_AUDIO = False
if EXTRACT_TEST_AUDIO:
    # We want to save the entire audio files 
    # for test time!
    test_spects = []
    test_spects_labels = []
    for file in test_data_files:
        label_file = 'Label'+file[4:]
        feature_file = np.genfromtxt(data_directory+file,delimiter=',').transpose()
        label_file = np.genfromtxt(data_directory+label_file,delimiter=',')
        
        if (feature_file.shape[0] != 9374):
            # It is length 8593 - kinda hacky but whatevs
            # Just extend with 0s
            spec_zeros = np.zeros((781, 77))
            label_zeros = np.zeros((781, 2))

            feature_file = np.concatenate((feature_file, spec_zeros))
            label_file = np.concatenate((label_file, label_zeros))

            print (feature_file.shape[0])
            print ("Corrected")

        extend_activate_label(label_file)
        test_spects.append(feature_file)
        test_spects_labels.append(label_file[:, 0])

    # Should all be the same length!
    # Others we will see
    test_spects = np.stack(test_spects)
    test_spects_labels = np.stack(test_spects_labels)
    label_type = '/Activate_Full_test' if USE_POST_CALL_LABEL else "/Call_Full_test"
    np.save(test_directory + label_type + '/features.npy', test_spects)
    np.save(test_directory + label_type + '/labels.npy', test_spects_labels)
    quit()


# Make the training dataset
def wrapper_makeDataSet(directory, file):
    print(file)
    label_file = 'Label'+file[4:]

    if (ACTIVATE_TIME == 0):
        feature_set, label_set = makeDataSet(data_directory+file,data_directory+label_file)
    else:
        feature_set, label_set = makeDataSetActivate(data_directory + file, data_directory + label_file)

    for i in range(len(feature_set)):
        np.save(directory + '/' + file[:-4] + "_features_" + str(i), feature_set[i])
        np.save(directory + '/' + file[:-4] + "_labels_" + str(i), label_set[i])


# Generate Train Set
train_directory += '/Neg_Samples_x' + str(NEG_FACT)
if not os.path.isdir(train_directory):
    os.mkdir(train_directory)

print ("Making Train Set")
print ("Size: ", len(train_data_files))

pool = multiprocessing.Pool()
print('Multiprocessing on {} CPU cores'.format(os.cpu_count()))
start_time = time.time()
pool.map(partial(wrapper_makeDataSet, train_directory), train_data_files)
pool.close()
print('Multiprocessed took {}'.format(time.time()-start_time))


# Generate Test Set
test_directory += '/Neg_Samples_x' + str(NEG_FACT)
if not os.path.isdir(test_directory):
    os.mkdir(test_directory)

print ("Making Test Set")
print ("Size: ", len(test_data_files))

pool = multiprocessing.Pool()
print('Multiprocessing on {} CPU cores'.format(os.cpu_count()))
start_time = time.time()
pool.map(partial(wrapper_makeDataSet, test_directory), test_data_files)
pool.close()
print('Multiprocessed took {}'.format(time.time()-start_time))

# label_type = '/Activate_Label/' if not USE_MFCC_FEATURES else '/MFCC_Activate_Label/'
# if (not USE_POST_CALL_LABEL):
#     label_type = "/Call_Label/" if not USE_MFCC_FEATURES else "/MFCC_Call_Label/"


# # Save the individual training files for visualization etc.
# for i in range(X_train.shape[0]):
#     np.save(train_directory + 'features_{}'.format(i+1), X_train[i])
#     np.save(train_directory + 'labels_{}'.format(i+1), y_train[i])

# for i in range(X_test.shape[0]):
#     np.save(test_directory  + 'features_{}'.format(i+1), X_test[i])
#     np.save(test_directory  + 'labels_{}'.format(i+1), y_test[i])


"""
# Some util code from downloading from box

from boxsdk import OAuth2

oauth = OAuth2(
    client_id='zofisutrx5cnbwcap5kmpvoszfc7a26r',
    client_secret='wA8KJlRsUOiwpE2pTO1Y3rliH8Z9DK7b',
)

from boxsdk import Client
client = Client(oauth)
me = client.user().get()
print('My user ID is {0}'.format(me.id))

from boxsdk import LoggingClient
client = LoggingClient(oauth)
import os
shared_folder = client.get_shared_item("https://cornell.box.com/s/lhymnsl28odm50u2qnx7xbrb5vfo733o")

def download(folder, path):
    # TODO: Make folder locally
    path += folder.name + '/'
    os.makedirs(path, exist_ok=True)
    items = folder.get_items()
    for item in items:
        if item.type == 'folder':
            download(item, path)
        elif item.type == 'file':
            output_file = open(path + item.name, 'wb')
            client.file(file_id=item.id).download_to(output_file)

download(shared_folder, "/home/data/elephants/rawdata/")
"""

"""
New approach, and one at a time

from boxsdk import OAuth2

oauth = OAuth2(
    client_id='zofisutrx5cnbwcap5kmpvoszfc7a26r',
    client_secret='wA8KJlRsUOiwpE2pTO1Y3rliH8Z9DK7b',
)

auth_url, csrf_token = oauth.get_authorization_url('https://nikitademir.com')

print(auth_url)

# This then needs to be manually done
from boxsdk import LoggingClient
access_token, refresh_token = oauth.authenticate('') # Enter auth code in here from redirect link

# Hoping passing in refresh token here means it gets used
oauth = OAuth2(
    client_id='zofisutrx5cnbwcap5kmpvoszfc7a26r',
    client_secret='wA8KJlRsUOiwpE2pTO1Y3rliH8Z9DK7b',
    access_token=access_token,
    refresh_token=refresh_token,
)

client = LoggingClient(oauth)
user = client.user().get()
print('User ID is {0}'.format(user.id))
import os
def download(folder, path):
    # TODO: Make folder locally
    path += folder.name + '/'
    os.makedirs(path, exist_ok=True)
    items = folder.get_items()
    for item in items:
        if item.type == 'file':
            output_file = open(path + item.name, 'wb')
            client.file(file_id=item.id).download_to(output_file)


shared_folder = client.get_shared_item("https://cornell.box.com/s/n0xesdrdrlq4ch96zl6zqwkkigfejrhw")

download(shared_folder, "/home/data/elephants/rawdata/DetectorDevelopment/")
"""



