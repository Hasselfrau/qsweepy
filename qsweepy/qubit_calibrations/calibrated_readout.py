from qsweepy.qubit_calibrations.readout_pulse import *
from qsweepy.libraries import readout_classifier
from qsweepy.qubit_calibrations import channel_amplitudes
from qsweepy.qubit_calibrations import excitation_pulse
from qsweepy.libraries import single_shot_readout
import numpy as np

import traceback


def get_confusion_matrix(device, qubit_ids, pause_length=0, recalibrate=True, force_recalibration=False):
    qubit_readout_pulse, readout_device = get_calibrated_measurer(device, qubit_ids)
    excitation_pulses = {qubit_id: excitation_pulse.get_excitation_pulse(device, qubit_id, rotation_angle=np.pi) for
                         qubit_id in qubit_ids}
    references = {('excitation_pulse', qubit_id): pulse.id for qubit_id, pulse in excitation_pulses.items()}
    references['readout_pulse'] = qubit_readout_pulse.id
    metadata = {'qubit_ids': qubit_readout_pulse.metadata['qubit_ids'], 'pause_length': str(pause_length)}
    try:
        assert not force_recalibration
        confusion_matrix = device.exdir_db.select_measurement(measurement_type='confusion_matrix',
                                                              references_that=references, metadata=metadata)
    except:
        if not recalibrate:
            raise
        confusion_matrix = calibrate_preparation_and_readout_confusion(device =device, qubit_readout_pulse = qubit_readout_pulse,
                                                                       readout_device = readout_device,
                                                                       pause_length = pause_length)

    return qubit_readout_pulse, readout_device, confusion_matrix


def calibrate_preparation_and_readout_confusion(device, qubit_readout_pulse, readout_device, *extra_sweep_args,
                                                pause_length=0, middle_seq_generator = None,
                                                additional_references = {}, additional_metadata = {}):
    qubit_ids = qubit_readout_pulse.metadata['qubit_ids'].split(',')
    target_qubit_states = [0] * len(qubit_ids)
    excitation_pulses = {qubit_id: excitation_pulse.get_excitation_pulse(device, qubit_id, rotation_angle=np.pi) for
                         qubit_id in qubit_ids}
    references = {('excitation_pulse', qubit_id): pulse.id for qubit_id, pulse in excitation_pulses.items()}
    references['readout_pulse'] = qubit_readout_pulse.id

    def set_target_state(state):
        excitation_sequence = []
        for _id, qubit_id in enumerate(qubit_ids):
            qubit_state = (1 << _id) & state
            if qubit_state:
                excitation_sequence.extend(excitation_pulses[qubit_id].get_pulse_sequence(0))
        if middle_seq_generator is not None:
            middle_pulse = middle_seq_generator()
        else:
            middle_pulse = []
        device.pg.set_seq(device.pre_pulses + excitation_sequence + middle_pulse + [
            device.pg.pmulti(pause_length)] + device.trigger_readout_seq + qubit_readout_pulse.get_pulse_sequence())

    if middle_seq_generator is not None:
        measurement_type = 'confusion_matrix_middle_seq'
    else:
        measurement_type = 'confusion_matrix'
    metadata = {'qubit_ids': qubit_readout_pulse.metadata['qubit_ids'],
                'pause_length': str(pause_length)}
    references.update(additional_references)
    metadata.update(additional_metadata)

    return device.sweeper.sweep(readout_device,
                                *extra_sweep_args,
                                (np.arange(2 ** len(qubit_ids)), set_target_state, 'Target state', ''),
                                measurement_type=measurement_type,
                                references=references,
                                metadata=metadata)


def get_calibrated_measurer(device, qubit_ids, qubit_readout_pulse=None, recalibrate=True, force_recalibration=False):
    from .readout_pulse import get_multi_qubit_readout_pulse
    if qubit_readout_pulse is None:
        qubit_readout_pulse = get_multi_qubit_readout_pulse(device, qubit_ids)
    features = []
    thresholds = []

    references = {'readout_pulse': qubit_readout_pulse.id,
                  'delay_calibration': device.modem.delay_measurement.id}
    for qubit_id in qubit_ids:
        metadata = {'qubit_id': qubit_id}
        try:
            if force_recalibration:
                raise ValueError('Forcing recalibration')
            measurement = device.exdir_db.select_measurement(measurement_type='readout_calibration', metadata=metadata,
                                                             references_that=references)
        except Exception as e:
            print(traceback.print_exc())
            if not recalibrate:
                raise
            measurement = calibrate_readout(device, qubit_id, qubit_readout_pulse)

        features.append(measurement.datasets['feature'].data)
        thresholds.append(measurement.datasets['threshold'].data.ravel()[0])

    readout_device = device.set_adc_features_and_thresholds(features, thresholds, disable_rest=True)
    nums = int(device.get_sample_global(name='calibrated_readout_nums'))
    readout_device.set_adc_nums(nums)
    readout_device.set_adc_nop(int(device.get_sample_global('readout_adc_points')))

    #readout_device.output_raw = False
    #readout_device.output_result = False
    #readout_device.output_resnum = True

    return qubit_readout_pulse, readout_device  # , features, thresholds


def calibrate_readout(device, qubit_id, qubit_readout_pulse, transition='01', ignore_other_qubits=None):
    adc, mnames = device.setup_adc_reducer_iq(qubit_id, raw=True)
    nums = int(device.get_qubit_constant(qubit_id=qubit_id, name='readout_background_nums'))
    old_nums = adc.get_adc_nums()
    adc.set_adc_nop(int(device.get_sample_global('readout_adc_points')))
    if ignore_other_qubits is None:
        ignore_other_qubits = (device.get_qubit_constant(qubit_id=qubit_id, name='readout_calibration_ignore_other_qubits') == 'True')
    print ('ignore_other_qubits', ignore_other_qubits)

    other_qubit_pulse_sequence = []
    references = {}
    if not ignore_other_qubits:
        for other_qubit_id in device.get_qubit_list():
            if other_qubit_id != qubit_id:
                half_excited_pulse = excitation_pulse.get_excitation_pulse(device, other_qubit_id,
                                                                           rotation_angle=np.pi / 2.)
                references[('other_qubit_pulse', other_qubit_id)] = half_excited_pulse.id
                other_qubit_pulse_sequence.extend(half_excited_pulse.get_pulse_sequence(0))

    qubit_excitation_pulse = excitation_pulse.get_excitation_pulse(device, qubit_id, rotation_angle=np.pi)
    metadata = {'qubit_id': qubit_id,
                'averages': nums,
                'ignore_other_qubits': ignore_other_qubits}

    references.update({'readout_pulse': qubit_readout_pulse.id,
                       'excitation_pulse': qubit_excitation_pulse.id,
                       'delay_calibration': device.modem.delay_measurement.id})

    classifier = single_shot_readout.single_shot_readout(adc=adc,
                                                         prepare_seqs=[device.pre_pulses + other_qubit_pulse_sequence,
                                                                       device.pre_pulses + other_qubit_pulse_sequence + qubit_excitation_pulse.get_pulse_sequence(
                                                                           0)],
                                                         ro_seq=device.trigger_readout_seq + qubit_readout_pulse.get_pulse_sequence(),
                                                         pulse_generator=device.pg,
                                                         ro_delay_seq=None,
                                                         _readout_classifier=readout_classifier.binary_linear_classifier(),
                                                         adc_measurement_name='Voltage')

    classifier.readout_classifier.cov_mode = 'equal'

    try:
        adc.set_adc_nums(nums)
        measurement = device.sweeper.sweep(classifier,
                                           measurement_type='readout_calibration',
                                           metadata=metadata,
                                           references=references)
    except:
        raise
    finally:
        adc.set_adc_nums(old_nums)

    return measurement
    # classifier.repeat_samples = 2


def get_qubit_readout_pulse_from_fidelity_scan(device, fidelity_scan):
    from .readout_pulse import qubit_readout_pulse
    references = {'fidelity_scan': fidelity_scan.id}
    if 'channel_calibration' in fidelity_scan.metadata:
        references['channel_calibration'] = fidelity_scan.references['readout_channel_calibration']

    fidelity_dataset = fidelity_scan.datasets['fidelity']
    max_fidelity = np.unravel_index(np.argmax(fidelity_dataset.data.ravel()), fidelity_dataset.data.shape)
    pulse_parameters = {}
    for p, v_id in zip(fidelity_dataset.parameters, max_fidelity):
        pulse_parameters[p.name] = p.values[v_id]
    #   compression_1db = float(passthrough_measurement.metadata['compression_1db'])
    #   additional_noise_appears = float(passthrough_measurement.metadata['additional_noise_appears'])
    #   if np.isfinite(compression_1db):
    #       calibration_type = 'compression_1db'
    #       amplitude = compression_1db
    #   elif np.isfinite(additional_noise_appears):
    #       calibration_type = 'additional_noise_appears'
    #       amplitude = additional_noise_appears
    #   else:
    #       raise Exception('Compession_1db and additional_noise_appears not found on passthourgh scan!')
    readout_channel = fidelity_scan.metadata['channel']
    # length = float(fidelity_scan.metadata['length'])
    metadata = {'pulse_type': 'rect',
                'channel': readout_channel,
                'qubit_id': fidelity_scan.metadata['qubit_id'],
                # 'amplitude':amplitude,
                'calibration_type': 'fidelity_scan',
                # 'length': passthrough_measurement.metadata['length']
                }
    metadata.update(pulse_parameters)
    length = float(metadata['length'])
    amplitude = float(metadata['amplitude'])
    try:
        readout_pulse = qubit_readout_pulse(
            device.exdir_db.select_measurement(measurement_type='qubit_readout_pulse', references_that=references,
                                               metadata=metadata))
    except Exception as e:
        print(type(e), str(e))
        readout_pulse = qubit_readout_pulse(references=references, metadata=metadata,
                                            sample_name=device.exdir_db.sample_name)
        device.exdir_db.save_measurement(readout_pulse)
    readout_pulse.pulse_sequence = [device.pg.p(readout_channel, length, device.pg.rect, amplitude)]
    return readout_pulse


def readout_fidelity_scan(device, qubit_id, readout_pulse_lengths, readout_pulse_amplitudes,
                          recalibrate_excitation=True, ignore_other_qubits=False, channel_amplitudes=None):
    adc, mnames = device.setup_adc_reducer_iq(qubit_id, raw=True)
    nums = int(device.get_qubit_constant(qubit_id=qubit_id, name='readout_background_nums'))
    adc.set_adc_nop(int(device.get_sample_global('readout_adc_points')))
    old_nums = adc.get_adc_nums()

    readout_channel = [i for i in device.get_qubit_readout_channel_list(qubit_id).keys()][0]

    other_qubit_pulse_sequence = []
    references = {'frequency_controls': device.get_frequency_control_measurement_id(qubit_id=qubit_id)}
    if hasattr(device.awg_channels[readout_channel], 'get_calibration_measurement'):
        references['channel_calibration'] = device.awg_channels[readout_channel].get_calibration_measurement()

    if not ignore_other_qubits:
        for other_qubit_id in device.get_qubit_list():
            if other_qubit_id != qubit_id:
                half_excited_pulse = excitation_pulse.get_excitation_pulse(device, other_qubit_id,
                                                                           rotation_angle=np.pi / 2.,
                                                                           recalibrate=recalibrate_excitation)
                references[('other_qubit_pulse', other_qubit_id)] = half_excited_pulse.id
                other_qubit_pulse_sequence.extend(half_excited_pulse.get_pulse_sequence(0))

    qubit_excitation_pulse = excitation_pulse.get_excitation_pulse(device, qubit_id, rotation_angle=np.pi, channel_amplitudes_override=channel_amplitudes,
                                                                   recalibrate=recalibrate_excitation)
    metadata = {'qubit_id': qubit_id,
                'averages': nums,
                'channel': readout_channel,
                'ignore_other_qubits': ignore_other_qubits}

    # print ('len(readout_pulse_lengths): ', len(readout_pulse_lengths))
    if len(readout_pulse_lengths) == 1:
        metadata['length'] = str(readout_pulse_lengths[0])

    references.update({'excitation_pulse': qubit_excitation_pulse.id,
                       'delay_calibration': device.modem.delay_measurement.id})

    classifier = single_shot_readout.single_shot_readout(adc=adc,
                                                         prepare_seqs=[device.pre_pulses + other_qubit_pulse_sequence,
                                                                       device.pre_pulses + other_qubit_pulse_sequence +
                                                                       qubit_excitation_pulse.get_pulse_sequence(0)],
                                                         ro_seq=device.trigger_readout_seq,
                                                         pulse_generator=device.pg,
                                                         ro_delay_seq=None,
                                                         _readout_classifier=readout_classifier.binary_linear_classifier(),
                                                         adc_measurement_name='Voltage',
                                                         dbg_storage=False)

    classifier.readout_classifier.cov_mode = 'equal'

    # setters for sweep
    readout_amplitude = 0
    readout_length = 0

    def set_readout_amplitude(x):
        nonlocal readout_amplitude
        readout_amplitude = x
        classifier.ro_seq = device.trigger_readout_seq + [
            device.pg.p(readout_channel, readout_length, device.pg.rect, readout_amplitude)]

    def set_readout_length(x):
        nonlocal readout_length
        readout_length = x
        classifier.ro_seq = device.trigger_readout_seq + [
            device.pg.p(readout_channel, readout_length, device.pg.rect, readout_amplitude)]

    try:
        adc.set_adc_nums(nums)
        measurement = device.sweeper.sweep(classifier,
                                           (readout_pulse_lengths, set_readout_length, 'length', 's'),
                                           (readout_pulse_amplitudes, set_readout_amplitude, 'amplitude', ''),
                                           measurement_type='readout_fidelity_scan',
                                           metadata=metadata,
                                           references=references)
    except:
        raise
    finally:
        adc.set_adc_nums(old_nums)

    return measurement
    # classifier.repeat_samples = 2


def readout_Zgate_scan(device, qubit_id, qubit_readout_pulse, Zgate, amplitudes,  transition='01', ignore_other_qubits=None):
    adc, mnames = device.setup_adc_reducer_iq(qubit_id, raw=True)
    nums = int(device.get_qubit_constant(qubit_id=qubit_id, name='readout_background_nums'))
    old_nums = adc.get_adc_nums()
    adc.set_adc_nop(int(device.get_sample_global('readout_adc_points')))
    if ignore_other_qubits is None:
        ignore_other_qubits = (device.get_qubit_constant(qubit_id=qubit_id, name='readout_calibration_ignore_other_qubits') == 'True')
    print ('ignore_other_qubits', ignore_other_qubits)

    other_qubit_pulse_sequence = []
    references = {}
    if not ignore_other_qubits:
        for other_qubit_id in device.get_qubit_list():
            if other_qubit_id != qubit_id:
                half_excited_pulse = excitation_pulse.get_excitation_pulse(device, other_qubit_id,
                                                                           rotation_angle=np.pi / 2.)
                references[('other_qubit_pulse', other_qubit_id)] = half_excited_pulse.id
                other_qubit_pulse_sequence.extend(half_excited_pulse.get_pulse_sequence(0))

    qubit_excitation_pulse = excitation_pulse.get_excitation_pulse(device, qubit_id, rotation_angle=np.pi)
    metadata = {'qubit_id': qubit_id,
                'averages': nums,
                'ignore_other_qubits': ignore_other_qubits}

    references.update({'readout_pulse': qubit_readout_pulse.id,
                       'excitation_pulse': qubit_excitation_pulse.id,
                       'delay_calibration': device.modem.delay_measurement.id,
                      'Zgate': Zgate.id},
                      )

    classifier = single_shot_readout.single_shot_readout(adc=adc,
                                                         prepare_seqs=[
                                                             device.pre_pulses + other_qubit_pulse_sequence,
                                                             device.pre_pulses + other_qubit_pulse_sequence + qubit_excitation_pulse.get_pulse_sequence(
                                                                 0)],
                                                         ro_seq=device.trigger_readout_seq + qubit_readout_pulse.get_pulse_sequence(),
                                                         pulse_generator=device.pg,
                                                         ro_delay_seq=None,
                                                         _readout_classifier=readout_classifier.binary_linear_classifier(),
                                                         adc_measurement_name='Voltage')

    def set_Zgate_amplitude(x):
        channel_amplitudes1_ = channel_amplitudes.channel_amplitudes(device,
                                                                     **{Zgate.metadata[
                                                                            'carrier_name']: x})
        print(channel_amplitudes1_)

        pulse_seq1 = excitation_pulse.get_rect_cos_pulse_sequence(device=device,
                                                                  channel_amplitudes=channel_amplitudes1_,
                                                                  tail_length=float(Zgate.metadata['tail_length']),
                                                                  length=float(qubit_readout_pulse.metadata['length']),
                                                                  phase=0.0)

        classifier.ro_seq =  device.trigger_readout_seq + device.pg.parallel(pulse_seq1,qubit_readout_pulse.get_pulse_sequence())

    classifier.readout_classifier.cov_mode = 'equal'

    try:
        adc.set_adc_nums(nums)
        measurement = device.sweeper.sweep(classifier,
                                           (amplitudes, set_Zgate_amplitude, 'amplitude', 'Voltage'),
                                           measurement_type='readout_Zgate_scan',
                                           metadata=metadata,
                                           references=references)
    except:
        raise
    finally:
        adc.set_adc_nums(old_nums)

    return measurement
    # classifier.repeat_samples = 2