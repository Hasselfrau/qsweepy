from  qsweepy.instrument_drivers.Keysight_M3202A import *
from  qsweepy.instrument_drivers.Keysight_M3202A import Keysight_M3202A_Base
import numpy as np

# CREATE AND OPEN MODULE IN
class Keysight_M3202A_S(Keysight_M3202A_Base):
	def __init__(self, name, chassis, slot):
		super().__init__(name, chassis, slot)
		self.master_channel = None
		self.repetition_period = 100000-500
		self.trigger_source_types = [0]*4
		self.trigger_source_channels = [0]*4
		self.trigger_delays = [0]*4
		self.trigger_behaviours = [0]*4
		self.waveforms = [None]*4
		self.waiting_waveforms = [[None, None]]*4
		self.waveform_ids = [None]*4
		self.waiting_waveform_ids = [None]*4
		self.marker_delay = [None]*4
		self.marker_length = [None]*4
	
	def prepare_set_waveform_async(self, waveform, channel):
		wave = keysightSD1.SD_Wave()
		if self.waiting_waveform_ids[channel] is None:
			wave.newFromArrayDouble(0, np.zeros((self.repetition_period,)).tolist()) # WAVE_ANALOG_32
			self.module.waveformLoad(wave, channel)
			wave = keysightSD1.SD_Wave()
			self.waiting_waveform_ids[channel] = channel
		waveform_id = self.waiting_waveform_ids[channel];
		
		waveform_data = np.asarray(waveform).tolist()
		wave.newFromArrayDouble(0, waveform_data) # WAVE_ANALOG_32
		self.module.waveformReLoad(wave, waveform_id, 0)
		
		self.waiting_waveforms[channel] = waveform_data
	
	### infinite cycles of a single waveform mode with synchronisation across channels
	def set_waveform(self, waveform, channel):
		from time import sleep
		self.stop()
		#self.stop()
		already_set = False
		if type(self.waveforms[channel]) != type(None):
			already_set = np.sum(np.abs(np.asarray(self.waveforms[channel]) - np.asarray(waveform)))<1e-5
			#print (channel, np.sum(np.abs(np.asarray(self.waveforms[channel]) - np.asarray(waveform))))
		
		if already_set:
			waveform_id = self.waveform_ids[channel]
			return
		else:
			if self.waiting_waveforms[channel] != waveform: # if the current waveform has not been preloaded by prepare_set_waveform_async
				wave = keysightSD1.SD_Wave()
				if self.waveform_ids[channel] is None:
					#print ('Loading waveform with waveformLoad')
					wave.newFromArrayDouble(0, np.zeros((self.repetition_period,)).tolist()) # WAVE_ANALOG_32
					self.module.waveformLoad(wave, channel)
					wave = keysightSD1.SD_Wave()
					self.waveform_ids[channel] = channel
				waveform_id = self.waveform_ids[channel];
		
				waveform_data = np.asarray(waveform).tolist()
				wave.newFromArrayDouble(0, waveform_data) # WAVE_ANALOG_32
				#print (waveform_data)
				error_code = self.module.waveformReLoad(wave, waveform_id, 0)
				sleep(0.1)
				#print ('First waveformReLoad:', error_code)
				#error_code = self.module.waveformReLoad(wave, waveform_id, 0)
				#print('Second waveformReLoad:', error_code)
				self.waveforms[channel] = waveform
			else: # in case the waveform has been preloaded, exchange the current waveform for the waiting_waveform
				waveform_id = self.waiting_waveform_ids[channel]
				waveform = self.waiting_waveforms[channel]
				self.waiting_waveform_ids[channel] = self.waveform_ids[channel]
				self.waiting_waveforms[channel] = self.waveforms[channel]
				self.waveform_ids[channel] = waveform_id
				self.waveforms[channel] = waveform

		trigger_source_type = self.trigger_source_types[channel]
		trigger_source_channel = self.trigger_source_channels[channel]
		trigger_delay = self.trigger_delays[channel]
		trigger_behaviour = self.trigger_behaviours[channel]
		self.module.AWGflush(channel)
		self.module.AWGtriggerExternalConfig(channel, trigger_source_channel, trigger_behaviour)
		self.module.AWGqueueConfig(channel, 1) # inifnite cycles
		self.module.AWGqueueWaveform(channel, 
											waveform_id, 
											trigger_source_type,#keysightSD1.SD_TriggerModes.AUTOTRIG, 
											trigger_delay, 
											1, 
											0)
		if self.marker_delay[channel]:
			self.module.AWGqueueMarkerConfig(channel, # nAWG
											2, # each cycle
											1<<channel, # PXI channels
											1 if channel == 0 else 0, #trigIOmask
											1, #value (0 is low, 1 is high)
											0, #syncmode
											self.marker_length[channel], #length5Tclk 
											self.marker_delay[channel]); #delay5Tclk
		self.module.AWGqueueSyncMode(channel, 1)
		
		#self.run()
		self.run()
		#time.sleep(0.05)
		
	def set_marker(self, delay, length, channel, pxi_channels=0, external=1):
		self.module.AWGflush(channel)
		self.marker_length[channel] = length
		self.marker_delay[channel] = delay

		trigger_source_type = self.trigger_source_types[channel]
		trigger_source_channel = self.trigger_source_channels[channel]
		trigger_delay = self.trigger_delays[channel]
		if self.waveforms[channel] is not None:		
			self.module.AWGqueueConfig(channel, 1) # infnite cycles
			#self.module.AWGfromArray(channel, trigger, 0, 0, 0, keysightSD1.SD_WaveformTypes.WAVE_ANALOG, waveform[:32576])
			self.module.AWGqueueWaveform(channel, 
												channel, 
												trigger_source_type,#keysightSD1.SD_TriggerModes.AUTOTRIG, 
												trigger_delay, 
												1, 
												0)
			#(self, nAWG, markerMode, trgPXImask, trgIOmask, value, syncMode, length, delay)
			#print(self.marker_length[channel], self.marker_delay[channel])
			self.module.AWGqueueMarkerConfig(channel, # nAWG
											2, # each cycle
											pxi_channels, # PXI channels
											external, #trigIOmask
											1, #value (0 is low, 1 is high)
											0, #syncmode
											self.marker_length[channel], #length5Tclk 
											self.marker_delay[channel]); #delay5Tclk
			self.module.AWGqueueSyncMode(channel, 1)
		
	## TODO: this function is broken
	def do_set_repetition_period(self, repetition_period):
		pass
	## TODO: this function is broken
	def get_repetition_period(self):
		return self.repetition_period*1e9
	## TODO: this function is broken
	def set_nop(self, nop):
		pass
	def get_nop(self):
		return self.repetition_period 
	## TODO: this function is broken
	def set_nop(self, repetition_period):
		pass
		