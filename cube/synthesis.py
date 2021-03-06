#
# Author: Tiberiu Boros
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import dynet_config
import optparse
import sys
import numpy as np


def get_file_input_old(txt_file):
    fin = open(txt_file, 'r')
    line = fin.readline().strip().replace('\t', ' ')

    while True:
        nl = line.replace('  ', ' ')
        if nl == line:
            break
        line = nl

    fin.close()
    return line


def get_file_input(txt_file):
    with open(txt_file, 'rt', encoding='utf-8') as f:
        return ' '.join(' '.join(f.readlines()).split())


def get_phone_input_from_text(text, speaker_identity):
    from io_modules.dataset import PhoneInfo

    seq = [PhoneInfo('START', [], 0, 0)]

    for char in text:
        l_char = char.lower()
        style = 'CASE:lower'
        if l_char == l_char.upper():
            style = 'CASE:symb'
        elif l_char != char:
            style = 'CASE:upper'
        speaker = 'SPEAKER:' + speaker_identity
        seq.append(PhoneInfo(l_char, [speaker, style], 0, 0))

    seq.append(PhoneInfo('STOP', [], 0, 0))

    return seq


def create_lab_input(txt_file, speaker_ident):
    line = get_file_input(txt_file)

    return get_phone_input_from_text(line, speaker_ident)


def _render_spectrogram(mgc, output_file):
    bitmap = np.zeros((mgc.shape[1], mgc.shape[0], 3), dtype=np.uint8)
    # mgc_min = mgc.min()
    # mgc_max = mgc.max()

    for x in range(mgc.shape[0]):
        for y in range(mgc.shape[1]):
            val = np.clip(mgc[x, y] * 255, 0, 255)  # (mgc[x, y] - mgc_min) / (mgc_max - mgc_min)

            color = val
            bitmap[mgc.shape[1] - y - 1, x] = [color, color, color]
    import scipy.misc as smp

    img = smp.toimage(bitmap)
    img.save(output_file)


def load_encoder(params, base_path='data/models'):
    from io_modules.dataset import Encodings
    from models.encoder import Encoder

    encodings = Encodings()
    encodings.load('%s/encoder.encodings' % base_path)

    encoder = Encoder(params, encodings, runtime=True)
    encoder.load('%s/rnn_encoder' % base_path)

    return encoder


def load_vocoder(params, base_path='data/models'):
    from models.vocoder import ParallelVocoder
    from models.vocoder import Vocoder

    vocoder = Vocoder(params)
    vocoder.load('%s/nn_vocoder' % base_path)

    pvocoder = ParallelVocoder(params, vocoder=vocoder)
    pvocoder.load('%s/pnn_vocoder' % base_path)

    return pvocoder


def synthesize_text_old(text, encoder, vocoder, speaker, params, output_file):
    print("[Encoding]")
    seq = get_phone_input_from_text(text, speaker)
    mgc, att = encoder.generate(seq)
    _render_spectrogram(mgc, output_file + '.png')

    print("[Vocoding]")

    import time
    start = time.time()
    import torch
    with torch.no_grad():
        signal = vocoder.synthesize(mgc, batch_size=params.batch_size, temperature=params.temperature)
    stop = time.time()
    sys.stdout.write(" execution time=" + str(stop - start))
    sys.stdout.write('\n')
    sys.stdout.flush()

    return signal


def synthesize_text(text, encoder, vocoder, speaker_identity):
    seq = get_phone_input_from_text(text, speaker_identity)
    mgc, _ = encoder.generate(seq)

    import torch
    with torch.no_grad():
        signal = vocoder.synthesize(mgc, batch_size=32)

    return signal


def write_signal_to_file(signal, output_file, params):
    from io_modules.dataset import DatasetIO
    dio = DatasetIO()


    dio.write_wave(output_file, signal / 32768.0, params.target_sample_rate, dtype=signal.dtype)


def synthesize(speaker, input_file, output_file, params):
    from models.vocoder import device
    print(device)
    print(params)

    encoder = load_encoder(params)
    vocoder = load_vocoder(params)

    text = get_file_input(input_file)

    signal = synthesize_text_old(text, encoder, vocoder, speaker, params, output_file)

    write_signal_to_file(signal, output_file, params)


if __name__ == '__main__':
    parser = optparse.OptionParser()
    parser.add_option('--input-file', action='store', dest='txt_file',
                      help='Path to the text file that will be synthesized')
    parser.add_option('--speaker', action='store', dest='speaker',
                      help='Speaker identity')
    parser.add_option('--output-file', action='store', dest='output_file',
                      help='Output WAVE file')
    parser.add_option("--batch-size", action='store', dest='batch_size', default='32', type='int',
                      help='number of samples in a single batch (default=32)')
    parser.add_option("--set-mem", action='store', dest='memory', default='2048', type='int',
                      help='preallocate memory for batch training (default 2048)')
    parser.add_option("--use-gpu", action='store_true', dest='gpu',
                      help='turn on/off GPU support')
    parser.add_option("--sample", action='store_true', dest='sample',
                      help='Use random sampling')
    parser.add_option('--mgc-order', action='store', dest='mgc_order', type='int',
                      help='Order of MGC parameters (default=80)', default=80)
    parser.add_option('--temperature', action='store', dest='temperature', type='float',
                      help='Exploration parameter (max 1.0, default 0.7)', default=0.7)
    parser.add_option('--target-sample-rate', action='store', dest='target_sample_rate',
                      help='Resample input files at this rate (default=24000)', type='int', default=24000)

    (params, _) = parser.parse_args(sys.argv)

    if not params.speaker:
        print("Speaker identity is mandatory")
    elif not params.txt_file:
        print("Input file is mandatory")
    elif not params.output_file:
        print("Output file is mandatory")

    memory = int(params.memory)
    # for compatibility we have to add this paramater
    params.learning_rate = 0.0001
    dynet_config.set(mem=memory, random_seed=9)
    if params.gpu:
        dynet_config.set_gpu()

    synthesize(params.speaker, params.txt_file, params.output_file, params)
