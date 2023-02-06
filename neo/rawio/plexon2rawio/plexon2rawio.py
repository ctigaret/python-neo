"""
ExampleRawIO is a class of a  fake example.
This is to be used when coding a new RawIO.


Rules for creating a new class:
  1. Step 1: Create the main class
    * Create a file in **neo/rawio/** that endith with "rawio.py"
    * Create the class that inherits from BaseRawIO
    * copy/paste all methods that need to be implemented.
    * code hard! The main difficulty is `_parse_header()`.
      In short you have to create a mandatory dict that
      contains channel informations::

            self.header = {}
            self.header['nb_block'] = 2
            self.header['nb_segment'] = [2, 3]
            self.header['signal_streams'] = signal_streams
            self.header['signal_channels'] = signal_channels
            self.header['spike_channels'] = spike_channels
            self.header['event_channels'] = event_channels

  2. Step 2: RawIO test:
    * create a file in neo/rawio/tests with the same name with "test_" prefix
    * copy paste neo/rawio/tests/test_examplerawio.py and do the same

  3. Step 3 : Create the neo.io class with the wrapper
    * Create a file in neo/io/ that ends with "io.py"
    * Create a class that inherits both your RawIO class and BaseFromRaw class
    * copy/paste from neo/io/exampleio.py

  4.Step 4 : IO test
    * create a file in neo/test/iotest with the same previous name with "test_" prefix
    * copy/paste from neo/test/iotest/test_exampleio.py



"""
import warnings
import numpy as np
from ..baserawio import (BaseRawIO, _signal_channel_dtype, _signal_stream_dtype,
                _spike_channel_dtype, _event_channel_dtype)


class Plexon2RawIO(BaseRawIO):
    """
    Class for "reading" fake data from an imaginary file.

    For the user, it gives access to raw data (signals, event, spikes) as they
    are in the (fake) file int16 and int64.

    For a developer, it is just an example showing guidelines for someone who wants
    to develop a new IO module.

    Two rules for developers:
      * Respect the :ref:`neo_rawio_API`
      * Follow the :ref:`io_guiline`

    This fake IO:
        * has 2 blocks
        * blocks have 2 and 3 segments
        * has  2 signals streams  of 8 channel each (sample_rate = 10000) so 16 channels in total
        * has 3 spike_channels
        * has 2 event channels: one has *type=event*, the other has
          *type=epoch*


    Usage:
        >>> import neo.rawio
        >>> r = neo.rawio.ExampleRawIO(filename='itisafake.nof')
        >>> r.parse_header()
        >>> print(r)
        >>> raw_chunk = r.get_analogsignal_chunk(block_index=0, seg_index=0,
                            i_start=0, i_stop=1024,  channel_names=channel_names)
        >>> float_chunk = reader.rescale_signal_raw_to_float(raw_chunk, dtype='float64',
                            channel_indexes=[0, 3, 6])
        >>> spike_timestamp = reader.spike_timestamps(spike_channel_index=0,
                            t_start=None, t_stop=None)
        >>> spike_times = reader.rescale_spike_timestamp(spike_timestamp, 'float64')
        >>> ev_timestamps, _, ev_labels = reader.event_timestamps(event_channel_index=0)

    """
    extensions = ['pl2']
    rawmode = 'one-file'

    def __init__(self, filename='', pl2_dll_path=None):
        from .pypl2lib import PyPL2FileReader, PL2FileInfo, PL2AnalogChannelInfo, \
            PL2DigitalChannelInfo, PL2SpikeChannelInfo


        BaseRawIO.__init__(self)
        # note that this filename is ued in self._source_name
        self.filename = filename

        self.pl2reader = PyPL2FileReader(pl2_dll_path=pl2_dll_path)


    def _source_name(self):
        # this function is used by __repr__
        # for general cases self.filename is good
        # But for URL you could mask some part of the URL to keep
        # the main part.
        return self.filename

    def _parse_header(self):
        # This is the central part of a RawIO
        # we need to collect from the original format all
        # information required for fast access
        # at any place in the file
        # In short `_parse_header()` can be slow but
        # `_get_analogsignal_chunk()` need to be as fast as possible

        # create fake signals stream information

        # Create an instance of PyPL2FileReader.
        p = PyPL2FileReader()

        # Verify that the file passed exists first.
        # Open the file.
        handle = p.pl2_open_file(str(self.filename))

        # If the handle is 0, print error message and return 0.
        if (handle == 0):
            ValueError(f'Can not open pl2 file: {self.filename}')

        # Create instance of PL2FileInfo.
        self.file_info = PL2FileInfo()

        res = p.pl2_get_file_info(self.file_info)

        # If res is 0, print error message and return 0.
        if (res == 0):
            ValueError(f'Can not read file information of pl2 file: {self.filename}')

        # Lists that will be filled with tuples
        spike_counts = []
        event_counts = []
        ad_counts = []

        # self.pl2reader.pl2_get_analog_channel_info()

        # 'm_NumberOFRecordedAnalogChannels',
        # 'm_NumberOfChannelHeaders',
        # 'm_NumberOfDigitalChannels',
        # 'm_NumberOfNonOmniPlexSources',
        # 'm_NumberOfRecordedSpikeChannels',
        # 'm_TotalNumberOfSpikeChannels',
        # 'm_TotalNumberOfAnalogChannels'

        signal_streams = []

        # The real signal will be evaluated as `(raw_signal * gain + offset) * pq.Quantity(units)`
        signal_channels = []
        stream_characteristics = []
        for c in range(self.file_info.m_TotalNumberOfAnalogChannels):
            achannel_info = PL2AnalogChannelInfo()
            res = p.pl2_get_analog_channel_info(c, achannel_info)

            # If res is 0 the channel info could not be loaded
            if res == 0:
                warnings.warn(f'Could not extract analog channel information of channel {c}')
                continue

            # only consider active channels
            if not achannel_info.m_ChannelEnabled:
                continue

            # assign to matching stream or create new stream based on signa characteristics
            stream_characteristic = (achannel_info.m_SamplesPerSecond, achannel_info.m_NumberOfValues)
            if stream_characteristic in stream_characteristics:
                stream_id = stream_characteristics.index((stream_characteristic))
            else:
                stream_id = len(stream_characteristics)
                stream_characteristics.append(stream_characteristic)

            ch_name = achannel_info.m_Name
            chan_id = achannel_info.m_Channel
            sr = achannel_info.m_SamplesPerSecond  # Hz
            dtype = 'int16' # TODO: Check if this is the correct correspondance to c_short
            units = achannel_info.m_Units.decode()
            gain = achannel_info.m_CoeffToConvertToUnits
            offset = 0.
            stream_id = stream_id
            signal_channels.append((ch_name, chan_id, sr, dtype, units, gain, offset, stream_id))

        signal_channels = np.array(signal_channels, dtype=_signal_channel_dtype)
        signal_streams = np.array(signal_streams, dtype=_signal_stream_dtype)
        _signal_stream_characteristics_dtype = [('sampling_rate','float64'), ('n_samples','int32'), ('id', 'U64')]
        self.signal_stream_characteristics = np.array(stream_characteristics, dtype=_signal_stream_characteristics_dtype)

        # create fake units channels
        # This is mandatory!!!!
        # Note that if there is no waveform at all in the file
        # then wf_units/wf_gain/wf_offset/wf_left_sweep/wf_sampling_rate
        # can be set to any value because _spike_raw_waveforms
        # will return None
        spike_channels = []
        for c in range(self.file_info.m_TotalNumberOfSpikeChannels):
            schannel_info = PL2SpikeChannelInfo()
            res = p.pl2_get_spike_channel_info(c, schannel_info)

            if res == 0:
                warnings.warn(f'Can not load information of spike channel {c}')
                continue

            # only consider active channels
            if not schannel_info.m_ChannelEnabled:
                continue

            for channel_unit_id in range(schannel_info.m_NumberOfUnits):
                unit_name = f'{schannel_info.m_Name}-{channel_unit_id}'
                unit_id = f'#{schannel_info.m_Channel}-{channel_unit_id}'
                wf_units = schannel_info.m_Units
                wf_gain = schannel_info.m_CoeffToConvertToUnits
                wf_offset = 0.
                wf_left_sweep = schannel_info.m_PreThresholdSamples
                wf_sampling_rate = schannel_info.SamplesPerSecond
                spike_channels.append((unit_name, unit_id, wf_units, wf_gain,
                                      wf_offset, wf_left_sweep, wf_sampling_rate))
        spike_channels = np.array(spike_channels, dtype=_spike_channel_dtype)

        # creating event/epoch channel

        event_channels = []
        for i in range(self.file_info.m_NumberOfDigitalChannels):
            echannel_info = PL2DigitalChannelInfo()
            res = p.pl2_get_digital_channel_info(i, echannel_info)
            # If res is 0 information for this digital event channel could not be loaded
            if res == 0:
                warnings.warn(f'Can not load information of spike channel {c}')
                continue

            # only consider active channels
            if not echannel_info.m_ChannelEnabled:
                continue

            # event channels are characterized by (name, id, type), with type in ['event', 'epoch']
            event_channels.append((echannel_info.m_Name, echannel_info.m_Channel, 'event'))

        event_channels = np.array(event_channels, dtype=_event_channel_dtype)

        # fill into header dict
        self.header = {}
        self.header['nb_block'] = 1
        self.header['nb_segment'] = [1] # TODO: Check if pl2 format can contain multiple segments
        self.header['signal_streams'] = signal_streams
        self.header['signal_channels'] = signal_channels
        self.header['spike_channels'] = spike_channels
        self.header['event_channels'] = event_channels

        # insert some annotations/array_annotations at some place
        # at neo.io level. IOs can add annotations
        # to any object. To keep this functionality with the wrapper
        # BaseFromRaw you can add annotations in a nested dict.

        # `_generate_minimal_annotations()` must be called to generate the nested
        # dict of annotations/array_annotations
        self._generate_minimal_annotations()
        # this pprint lines really help for understand the nested (and complicated sometimes) dict
        from pprint import pprint
        pprint(self.raw_annotations)


        # TODO: file_info.m_ReprocessorDateTime seems to be empty. Check with original implementation

        # Until here all mandatory operations for setting up a rawio are implemented.
        # The following lines provide additional, recommended annotations for the
        # final neo objects.
        block_index = 0
        bl_ann = self.raw_annotations['blocks'][block_index]
        bl_ann['name'] = 'Block containing PL2 data#{}'.format(block_index)
        bl_ann['file_origin'] = self.filename
        pl2_file_info = {attr: getattr(self.file_info, attr) for attr in dir(self.file_info)
                         if not attr.startswith('_')}
        bl_ann.update(pl2_file_info)
        for seg_index in range(1): # TODO: Check if PL2 file can contain multiple segments
            seg_ann = bl_ann['segments'][seg_index]
            # seg_ann['name'] = 'Seg #{} Block #{}'.format(
            #     seg_index, block_index)
            # seg_ann['seg_extra_info'] = 'This is the seg {} of block {}'.format(
            #     seg_index, block_index)
            # for c in range(2):
            #     sig_an = seg_ann['signals'][c]['nickname'] = \
            #         f'This stream {c} is from a subdevice'
            #     # add some array annotations (8 channels)
            #     sig_an = seg_ann['signals'][c]['__array_annotations__']['impedance'] = \
            #         np.random.rand(8) * 10000
            # for c in range(3):
            #     spiketrain_an = seg_ann['spikes'][c]
            #     spiketrain_an['quality'] = 'Good!!'
            #     # add some array annotations
            #     num_spikes = self.spike_count(block_index, seg_index, c)
            #     spiketrain_an['__array_annotations__']['amplitudes'] = \
            #         np.random.randn(num_spikes)

            # for c in range(2):
            #     event_an = seg_ann['events'][c]
            #     if c == 0:
            #         event_an['nickname'] = 'Miss Event 0'
            #         # add some array annotations
            #         num_ev = self.event_count(block_index, seg_index, c)
            #         event_an['__array_annotations__']['button'] = ['A'] * num_ev
            #     elif c == 1:
            #         event_an['nickname'] = 'MrEpoch 1'

    def _segment_t_start(self, block_index, seg_index):
        # this must return an float scale in second
        # this t_start will be shared by all object in the segment
        # except AnalogSignal
        return self.file_info.m_StartRecordingTime / self.file_info.m_TimestampFrequency

    def _segment_t_stop(self, block_index, seg_index):
        # this must return an float scale in second
        return (self.file_info.m_StartRecordingTime + self.file_info.m_DurationOfRecording) / self.file_info.m_TimestampFrequency


    def _get_signal_size(self, block_index, seg_index, stream_index):
        # We generate fake data in which the two stream signals have the same shape
        # across all segments (10.0 seconds)
        # This is not the case for real data, instead you should return the signal
        # size depending on the block_index and segment_index
        # this must return an int = the number of sample

        # Note that channel_indexes can be ignored for most cases
        # except for several sampling rate.
        stream_id = self.header['signal_streams'][stream_index]['stream_id']
        stream_char = self.signal_stream_characteristics[stream_id]
        assert stream_char[stream_char['stream_id'] == stream_id]['n_samples']
        return stream_char['n_samples']

    def _get_signal_t_start(self, block_index, seg_index, stream_index):
        # This give the t_start of signals.
        # this must return an float scale in second

        return self._segment_t_start(block_index, seg_index)

    def _get_analogsignal_chunk(self, block_index, seg_index, i_start, i_stop,
                                stream_index, channel_indexes):
        # this must return a signal chunk in a signal stream
        # limited with i_start/i_stop (can be None)
        # channel_indexes can be None (=all channel in the stream) or a list or numpy.array
        # This must return a numpy array 2D (even with one channel).
        # This must return the original dtype. No conversion here.
        # This must as fast as possible.
        # To speed up this call all preparatory calculations should be implemented
        # in _parse_header().

        # Here we are lucky:  our signals is always zeros!!
        # it is not always the case :)
        # internally signals are int16
        # conversion to real units is done with self.header['signal_channels']

        if i_start is None:
            i_start = 0
        if i_stop is None:
            i_stop = 100000

        if i_start < 0 or i_stop > 100000:
            # some check
            raise IndexError("I don't like your jokes")

        if channel_indexes is None:
            nb_chan = 8
        elif isinstance(channel_indexes, slice):
            channel_indexes = np.arange(8, dtype='int')[channel_indexes]
            nb_chan = len(channel_indexes)
        else:
            channel_indexes = np.asarray(channel_indexes)
            if any(channel_indexes < 0):
                raise IndexError('bad boy')
            if any(channel_indexes >= 8):
                raise IndexError('big bad wolf')
            nb_chan = len(channel_indexes)

        raw_signals = np.zeros((i_stop - i_start, nb_chan), dtype='int16')
        return raw_signals

    def _spike_count(self, block_index, seg_index, spike_channel_index):
        # Must return the nb of spikes for given (block_index, seg_index, spike_channel_index)
        # we are lucky:  our units have all the same nb of spikes!!
        # it is not always the case
        nb_spikes = 20
        return nb_spikes

    def _get_spike_timestamps(self, block_index, seg_index, spike_channel_index, t_start, t_stop):
        # In our IO, timestamp are internally coded 'int64' and they
        # represent the index of the signals 10kHz
        # we are lucky: spikes have the same discharge in all segments!!
        # incredible neuron!! This is not always the case

        # the same clip t_start/t_start must be used in _spike_raw_waveforms()

        ts_start = (self._segment_t_start(block_index, seg_index) * 10000)

        spike_timestamps = np.arange(0, 10000, 500) + ts_start

        if t_start is not None or t_stop is not None:
            # restrict spikes to given limits (in seconds)
            lim0 = int(t_start * 10000)
            lim1 = int(t_stop * 10000)
            mask = (spike_timestamps >= lim0) & (spike_timestamps <= lim1)
            spike_timestamps = spike_timestamps[mask]

        return spike_timestamps

    def _rescale_spike_timestamp(self, spike_timestamps, dtype):
        # must rescale to second a particular spike_timestamps
        # with a fixed dtype so the user can choose the precision he want.
        spike_times = spike_timestamps.astype(dtype)
        spike_times /= 10000.  # because 10kHz
        return spike_times

    def _get_spike_raw_waveforms(self, block_index, seg_index, spike_channel_index,
                                 t_start, t_stop):
        # this must return a 3D numpy array (nb_spike, nb_channel, nb_sample)
        # in the original dtype
        # this must be as fast as possible.
        # the same clip t_start/t_start must be used in _spike_timestamps()

        # If there there is no waveform supported in the
        # IO them _spike_raw_waveforms must return None

        # In our IO waveforms come from all channels
        # they are int16
        # conversion to real units is done with self.header['spike_channels']
        # Here, we have a realistic case: all waveforms are only noise.
        # it is not always the case
        # we 20 spikes with a sweep of 50 (5ms)

        # trick to get how many spike in the slice
        ts = self._get_spike_timestamps(block_index, seg_index,
                                        spike_channel_index, t_start, t_stop)
        nb_spike = ts.size

        np.random.seed(2205)  # a magic number (my birthday)
        waveforms = np.random.randint(low=-2**4, high=2**4, size=nb_spike * 50, dtype='int16')
        waveforms = waveforms.reshape(nb_spike, 1, 50)
        return waveforms

    def _event_count(self, block_index, seg_index, event_channel_index):
        # event and spike are very similar
        # we have 2 event channels
        if event_channel_index == 0:
            # event channel
            return 6
        elif event_channel_index == 1:
            # epoch channel
            return 10

    def _get_event_timestamps(self, block_index, seg_index, event_channel_index, t_start, t_stop):
        # the main difference between spike channel and event channel
        # is that for here we have 3 numpy array timestamp, durations, labels
        # durations must be None for 'event'
        # label must a dtype ='U'

        # in our IO event are directly coded in seconds
        seg_t_start = self._segment_t_start(block_index, seg_index)
        if event_channel_index == 0:
            timestamp = np.arange(0, 6, dtype='float64') + seg_t_start
            durations = None
            labels = np.array(['trigger_a', 'trigger_b'] * 3, dtype='U12')
        elif event_channel_index == 1:
            timestamp = np.arange(0, 10, dtype='float64') + .5 + seg_t_start
            durations = np.ones((10), dtype='float64') * .25
            labels = np.array(['zoneX'] * 5 + ['zoneZ'] * 5, dtype='U12')

        if t_start is not None:
            keep = timestamp >= t_start
            timestamp, labels = timestamp[keep], labels[keep]
            if durations is not None:
                durations = durations[keep]

        if t_stop is not None:
            keep = timestamp <= t_stop
            timestamp, labels = timestamp[keep], labels[keep]
            if durations is not None:
                durations = durations[keep]

        return timestamp, durations, labels

    def _rescale_event_timestamp(self, event_timestamps, dtype, event_channel_index):
        # must rescale to second a particular event_timestamps
        # with a fixed dtype so the user can choose the precision he want.

        # really easy here because in our case it is already seconds
        event_times = event_timestamps.astype(dtype)
        return event_times

    def _rescale_epoch_duration(self, raw_duration, dtype, event_channel_index):
        # really easy here because in our case it is already seconds
        durations = raw_duration.astype(dtype)
        return durations
