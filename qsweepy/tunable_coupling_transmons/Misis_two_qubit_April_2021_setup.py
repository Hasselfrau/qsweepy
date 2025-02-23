import qsweepy.libraries.instruments as instruments
import qsweepy
from qsweepy.libraries.awg_channel2 import awg_channel
from qsweepy.libraries.awg_digital2 import awg_digital
import numpy as np
from qsweepy import zi_scripts

device_settings = {
                   'vna_address': 'TCPIP0::10.20.61.68::inst0::INSTR', #ZVB
                   'rf_switch_address': '10.20.61.91',
                   'use_rf_switch': False,
                   'hdawg_address': 'hdawg-dev8108',
                   'sa_address': 'TCPIP0::10.20.61.56::inst0::INSTR',
                   'adc_timeout': 10,
                   'adc_trig_rep_period': 10,  # 12.5 MHz rate period
                   'adc_trig_width': 2,  # 32 ns trigger length
                   }

cw_settings = { 'mixer_thru': 0.5 }

pulsed_settings = {#'lo1_power': 18,
                   'vna_power': 16,
                   'ex_clock': 2400e6,  # 1 GHz - clocks of some devices
                   'ro_clock': 1000e6,
                   'hdawg_ch0_amplitude': 0.8,
                   'hdawg_ch1_amplitude': 0.8,
                   'hdawg_ch2_amplitude': 0.8,
                   'hdawg_ch3_amplitude': 0.8,
                   'hdawg_ch4_amplitude': 0.8,
                   'hdawg_ch5_amplitude': 0.8,
                   'hdawg_ch6_amplitude': 0.8,
                   'hdawg_ch7_amplitude': 0.8,
                   'lo1_freq': 3.70e9,
                   'pna_freq': 7.195e9, #7.2111e9 7.257e9 7.232e9 7.2275e9 7.1e9
                   #'calibrate_delay_nop': 65536,
                   'calibrate_delay_nums': 200,
                   'trigger_readout_length': 200e-9,
                   'modem_dc_calibration_amplitude': 1.0,
                   }


class hardware_setup():
    def __init__(self, device_settings, pulsed_settings):
        self.device_settings = device_settings
        self.pulsed_settings = pulsed_settings
        self.cw_settings = cw_settings
        self.hardware_state = 'undefined'
        self.sa = None

        self.pna = None
        self.lo1 = None
        self.rf_switch = None
        self.coil_device = None
        self.hdawg = None
        self.adc_device = None
        self.adc = None

        self.ro_trg = None
        self.q1z = None
        self.cz = None
        self.q2z = None
        self.q3z = None
        self.iq_devices = None
        self.fast_controls = None

    def open_devices(self):
        # RF switch for making sure we know what sample we are measuring
        self.pna = instruments.RS_ZVB20('pna', address=self.device_settings['vna_address'])
        #self.pna = instruments.Agilent_N5242A('pna', address=self.device_settings['vna_address'])
        #self.lo1 = Agilent_E8257D('lo1', address=self.device_settings['lo1_address'])

        #self.lo1._visainstrument.timeout = self.device_settings['lo1_timeout']
        #self.lo1 = instruments.SignalCore_5502a()
        #self.lo1.search()
        #self.lo1.open()

        if self.device_settings['use_rf_switch']:
            self.rf_switch = instruments.nn_rf_switch('rf_switch', address=self.device_settings['rf_switch_address'])

        self.hdawg = instruments.ZIDevice(self.device_settings['hdawg_address'], devtype='HDAWG', clock=2e9, delay_int=0)

        for channel_id in range(8):
            self.hdawg.daq.setDouble('/' + self.hdawg.device + '/sigouts/%d/range' % channel_id, 1)
        #It is necessary if you want to use DIOs control features during pulse sequence
        self.hdawg.daq.setInt('/' + self.hdawg.device + '/dios/0/mode', 1)
        self.hdawg.daq.setInt('/' + self.hdawg.device + '/dios/0/drive', 1)
        self.hdawg.daq.sync()
        #
        # self.hdawg.daq.setDouble('/' + self.hdawg.device + '/sigouts/0/range', 0.8)
        # self.hdawg.daq.setDouble('/' + self.hdawg.device + '/sigouts/1/range', 0.8)
        # self.hdawg.daq.setDouble('/' + self.hdawg.device + '/sigouts/2/range', 0.8)
        # self.hdawg.daq.setDouble('/' + self.hdawg.device + '/sigouts/3/range', 0.8)
        # self.hdawg.daq.setDouble('/' + self.hdawg.device + '/sigouts/4/range', 0.8)
        # self.hdawg.daq.setDouble('/' + self.hdawg.device + '/sigouts/5/range', 0.8)
        # self.hdawg.daq.setDouble('/' + self.hdawg.device + '/sigouts/6/range', 0.8)
        # self.hdawg.daq.setDouble('/' + self.hdawg.device + '/sigouts/7/range', 0.8)

        self.coil_device = self.hdawg

        # Qubit lines should be connected with even channels
        self.q3z = awg_channel(self.hdawg, 6)  # coil control
        self.q2z = awg_channel(self.hdawg, 2)  # coil control
        self.cz = awg_channel(self.hdawg, 7)  # coil control
        self.q1z = awg_channel(self.hdawg, 0)  # coil control


        self.sa = instruments.Agilent_N9030A('pxa', address=self.device_settings['sa_address'])

        self.adc_device = instruments.TSW14J56_evm()
        self.adc_device.timeout = self.device_settings['adc_timeout']
        self.adc = instruments.TSW14J56_evm_reducer(self.adc_device)
        self.adc.output_raw = True
        self.adc.last_cov = False
        self.adc.avg_cov = False
        self.adc.resultnumber = False

        self.adc_device.set_trig_src_period(self.device_settings['adc_trig_rep_period'])  # 10 kHz period rate
        self.adc_device.set_trig_src_width(self.device_settings['adc_trig_width'])  # 80 ns trigger length

        self.hardware_state = 'undefined'

    def set_cw_mode(self, channels_off=None):
        if self.hardware_state == 'cw_mode':
            return
        self.hardware_state = 'cw_mode'

        self.cw_sequence = zi_scripts.CWSequence(awg=self.hdawg, sequencer_id=2)
        #self.hdawg.set_sequencer(self.cw_sequence)
        self.hdawg.set_sequence(2, self.cw_sequence)
        self.cw_sequence.set_amplitude_i(0)
        self.cw_sequence.set_amplitude_q(0)
        self.cw_sequence.set_phase_i(0)
        self.cw_sequence.set_phase_q(0)
        self.cw_sequence.set_offset_i(cw_settings['mixer_thru'])
        self.cw_sequence.set_offset_q(0)

        self.pna.set_sweep_mode("LIN")
        self.hardware_state = 'cw_mode'

    def set_spectroscopy_mode(self, channels_off=None):
        if self.hardware_state == 'cw_mode':
            return
        self.hardware_state = 'cw_mode'
        self.hdawg.stop()

        self.cw_sequence = zi_scripts.CWSequence(awg=self.hdawg, sequencer_id=2)
        # self.hdawg.set_sequencer(self.cw_sequence)
        self.hdawg.set_sequence(2, self.cw_sequence)
        self.cw_sequence.set_amplitude_i(0)
        self.cw_sequence.set_amplitude_q(0)
        self.cw_sequence.set_phase_i(0)
        self.cw_sequence.set_phase_q(0)
        self.cw_sequence.set_offset_i(cw_settings['mixer_thru'])
        self.cw_sequence.set_offset_q(0)

        self.hdawg.set_output(output=1, channel=0)
        self.hdawg.set_output(output=1, channel=1)
        self.hdawg.set_output(output=1, channel=2)
        self.hdawg.set_output(output=1, channel=3)
        self.hdawg.set_output(output=1, channel=4)
        self.hdawg.set_output(output=1, channel=5)
        self.hdawg.set_output(output=0, channel=6)
        self.hdawg.set_output(output=0, channel=7)
        if channels_off is not None:
            for channel_off in channels_off:
                self.hdawg.set_output(output=0, channel=channel_off)

        self.pna.set_sweep_mode("LIN")
        self.hardware_state = 'cw_mode'

    def set_pulsed_mode(self):
        if self.hardware_state == 'pulsed_mode':
            return
        self.hardware_state = 'undefined'

        #self.lo1.set_status(1)  # turn on lo1 output
        #self.lo1.set_power(self.pulsed_settings['lo1_power'])
        #self.lo1.set_frequency(self.pulsed_settings['lo1_freq'])

        self.pna.set_power(self.pulsed_settings['vna_power'])

        #self.pna.write("OUTP ON")
        self.pna.write("SOUR1:POW1:MODE ON")
        self.pna.write("SOUR1:POW2:MODE OFF")
        self.pna.set_sweep_mode("CW") # privet RS ZVB20
        #self.pna.set_trigger_source("ON")
        self.pna.set_frequency(self.pulsed_settings['pna_freq'])

        self.hdawg.stop()

        self.hdawg.set_clock(self.pulsed_settings['ex_clock'])
        self.hdawg.set_clock_source(0)

        self.hdawg.set_trigger_impedance_1e3()
        self.hdawg.set_dig_trig1_source([4, 4, 4, 4])
        self.hdawg.set_dig_trig1_slope([1, 1, 1, 1])  # 0 - Level sensitive trigger, 1 - Rising edge trigger,
                                                      # 2 - Falling edge trigger, 3 - Rising or falling edge trigger
        self.hdawg.set_dig_trig2_source([0, 0, 0, 0])
        self.hdawg.set_dig_trig2_slope([1, 1, 1,1])
        self.hdawg.set_trig_level(0.3)

        self.ro_trg = awg_digital(self.hdawg, 4, delay_tolerance=20e-9)  # triggers readout card
        self.ro_trg.adc = self.adc
        self.ro_trg.mode = 'waveform'
        self.hardware_state = 'pulsed_mode'

        # I don't know HOW but it works
        # For each exitation sequencers:
        # We need to set DIO slope as  Rise (0- off, 1 - rising edge, 2 - falling edge, 3 - both edges)
        for ex_seq_id in range(4):
            self.hdawg.daq.setInt('/' + self.hdawg.device + '/awgs/%d/dio/strobe/slope' % ex_seq_id, 1)
            # We need to set DIO valid polarity as High (0- none, 1 - low, 2 - high, 3 - both )
            self.hdawg.daq.setInt('/' + self.hdawg.device + '/awgs/%d/dio/valid/polarity' % ex_seq_id, 2)

        # For readout channels
        # For readout sequencer:
        read_seq_id = self.ro_trg.channel //2
        # We need to set DIO slope as  Fall (0- off, 1 - rising edge, 2 - falling edge, 3 - both edges)
        self.hdawg.daq.setInt('/' + self.hdawg.device + '/awgs/%d/dio/strobe/slope' % read_seq_id, 1)
        # We need to set DIO valid polarity as  None (0- none, 1 - low, 2 - high, 3 - both )
        self.hdawg.daq.setInt('/' + self.hdawg.device + '/awgs/%d/dio/valid/polarity' % read_seq_id, 0)
        self.hdawg.daq.setInt('/' + self.hdawg.device + '/awgs/%d/dio/strobe/index' % read_seq_id, 3)
        #self.hdawg.daq.setInt('/' + self.hdawg.device + '/awgs/%d/dio/mask/value' % read_seq_id, 2)
        #self.hdawg.daq.setInt('/' + self.hdawg.device + '/awgs/%d/dio/mask/shift' % read_seq_id, 1)
        # For readout channels


    def set_switch_if_not_set(self, value, channel):
        if self.rf_switch is not None:
            if self.rf_switch.do_get_switch(channel=channel) != value:
                self.rf_switch.do_set_switch(value, channel=channel)

    def setup_iq_channel_connections(self, exdir_db):
        # промежуточные частоты для гетеродинной схемы new:
        self.iq_devices = {'iq_ro':  qsweepy.libraries.awg_iq_multi2.AWGIQMulti(awg=self.hdawg, sequencer_id=2,
                                                                                  lo=self.pna, exdir_db=exdir_db)}
        self.iq_devices['iq_ro'].name = 'ro'
        self.iq_devices['iq_ro'].calibration_switch_setter = lambda: None
        self.iq_devices['iq_ro'].sa = self.sa

        self.fast_controls = {'q3z': awg_channel(self.hdawg, 6),
                              'q2z':awg_channel(self.hdawg, 2),
                              'cz': awg_channel(self.hdawg, 7),
                              'q1z': awg_channel(self.hdawg, 0)}  # coil control

    def get_modem_dc_calibration_amplitude(self):
        return self.pulsed_settings['modem_dc_calibration_amplitude']