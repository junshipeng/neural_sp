#! /usr/bin/env python
# -*- coding: utf-8 -*-

"""Evaluate the hierarchical ASR model."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from os.path import join, abspath
import sys
import argparse
from distutils.util import strtobool

sys.path.append(abspath('../../../'))
from src.models.load_model import load
from src.dataset.loader_hierarchical import Dataset
from src.metrics.character import eval_char
from src.metrics.word import eval_word
from src.utils.config import load_config
from src.utils.evaluation.logging import set_logger

parser = argparse.ArgumentParser()
parser.add_argument('--corpus', type=str,
                    help='the name of corpus')
parser.add_argument('--eval_sets', type=str, nargs='+',
                    help='evaluation sets')
parser.add_argument('--data_save_path', type=str,
                    help='path to saved data')
parser.add_argument('--model_path', type=str,
                    help='path to the model to evaluate')
parser.add_argument('--epoch', type=int, default=-1,
                    help='the epoch to restore')
parser.add_argument('--eval_batch_size', type=int, default=1,
                    help='the size of mini-batch in evaluation')
parser.add_argument('--beam_width', type=int, default=1,
                    help='the size of beam in the main task')
parser.add_argument('--beam_width_sub', type=int, default=1,
                    help='the size of beam in the sub task')
parser.add_argument('--length_penalty', type=float, default=0,
                    help='length penalty')
parser.add_argument('--coverage_penalty', type=float, default=0,
                    help='coverage penalty')
parser.add_argument('--rnnlm_weight', type=float, default=0,
                    help='the weight of RNNLM score of the main task')
parser.add_argument('--rnnlm_weight_sub', type=float, default=0,
                    help='the weight of RNNLM score of the sub task')
parser.add_argument('--rnnlm_path', type=str, default=None, nargs='?',
                    help='path to the RMMLM of the main task')
parser.add_argument('--rnnlm_path_sub', type=str, default=None, nargs='?',
                    help='path to the RMMLM of the sub task')
parser.add_argument('--resolving_unk', type=strtobool, default=False)
parser.add_argument('--a2c_oracle', type=strtobool, default=False)
parser.add_argument('--joint_decoding', type=strtobool, default=False)
parser.add_argument('--score_sub_weight', type=float, default=0)
args = parser.parse_args()

# corpus depending
if args.corpus == 'csj':
    MAX_DECODE_LEN_WORD = 100
    MIN_DECODE_LEN_WORD = 1
    MAX_DECODE_LEN_RATIO_WORD = 1
    MIN_DECODE_LEN_RATIO_WORD = 0

    MAX_DECODE_LEN_CHAR = 200
    MIN_DECODE_LEN_CHAR = 1
    MAX_DECODE_LEN_RATIO_CHAR = 1
    MIN_DECODE_LEN_RATIO_CHAR = 0.2

elif args.corpus == 'swbd':
    MAX_DECODE_LEN_WORD = 100
    MIN_DECODE_LEN_WORD = 1
    MAX_DECODE_LEN_RATIO_WORD = 1
    MIN_DECODE_LEN_RATIO_WORD = 0

    MAX_DECODE_LEN_CHAR = 300
    MIN_DECODE_LEN_CHAR = 1
    MAX_DECODE_LEN_RATIO_CHAR = 1
    MIN_DECODE_LEN_RATIO_CHAR = 0.2

elif args.corpus == 'librispeech':
    MAX_DECODE_LEN_WORD = 200
    MIN_DECODE_LEN_WORD = 1
    MAX_DECODE_LEN_RATIO_WORD = 1
    MIN_DECODE_LEN_RATIO_WORD = 0

    MAX_DECODE_LEN_CHAR = 600
    MIN_DECODE_LEN_CHAR = 1
    MAX_DECODE_LEN_RATIO_CHAR = 1
    MIN_DECODE_LEN_RATIO_CHAR = 0.2

elif args.corpus == 'wsj':
    MAX_DECODE_LEN_WORD = 32
    MIN_DECODE_LEN_WORD = 2
    MAX_DECODE_LEN_RATIO_WORD = 1
    MIN_DECODE_LEN_RATIO_WORD = 0

    MAX_DECODE_LEN_CHAR = 199
    MIN_DECODE_LEN_CHAR = 10
    MAX_DECODE_LEN_RATIO_CHAR = 1
    MIN_DECODE_LEN_RATIO_CHAR = 0.2

    # NOTE:
    # dev93 (char): 10-199
    # test_eval92 (char): 16-195
    # dev93 (word): 2-32
    # test_eval92 (word): 3-30

else:
    raise ValueError


def main():

    # Load a ASR config file
    config = load_config(join(args.model_path, 'config.yml'), is_eval=True)

    # Setting for logging
    logger = set_logger(args.model_path)

    wer_mean, wer_sub_mean, cer_sub_mean = 0, 0, 0
    for i, data_type in enumerate(args.eval_sets):
        # Load dataset
        eval_set = Dataset(
            corpus=args.corpus,
            data_save_path=args.data_save_path,
            input_freq=config['input_freq'],
            use_delta=config['use_delta'],
            use_double_delta=config['use_double_delta'],
            data_size=config['data_size'] if 'data_size' in config.keys(
            ) else '',
            data_type=data_type,
            label_type=config['label_type'],
            label_type_sub=config['label_type_sub'],
            batch_size=args.eval_batch_size,
            tool=config['tool'])

        if i == 0:
            config['num_classes'] = eval_set.num_classes
            config['num_classes_sub'] = eval_set.num_classes_sub

            if args.corpus == 'swbd':
                eval_set.glm_path = join(
                    args.data_save_path, 'eval2000', 'glm')

            # For cold fusion
            if config['rnnlm_fusion_type'] and config['rnnlm_path']:
                # Load a RNNLM config file
                config['rnnlm_config'] = load_config(
                    join(args.model_path, 'config_rnnlm.yml'))
                assert config['label_type'] == config['rnnlm_config']['label_type']
                assert args.rnnlm_weight > 0
                config['rnnlm_config']['num_classes'] = eval_set.num_classes
                logger.info('RNNLM path (main): %s' % config['rnnlm_path'])
                logger.info('RNNLM weight (main): %.3f' % args.rnnlm_weight)
            else:
                config['rnnlm_config'] = None

            if config['rnnlm_fusion_type'] and config['rnnlm_path_sub']:
                # Load a RNNLM config file
                config['rnnlm_config_sub'] = load_config(
                    join(args.model_path, 'config_rnnlm_sub.yml'))
                assert config['label_type_sub'] == config['rnnlm_config_sub']['label_type']
                assert args.rnnlm_weight_sub > 0
                config['rnnlm_config_sub']['num_classes'] = eval_set.num_classes_sub
                logger.info('RNNLM path (sub): %s' % config['rnnlm_path_sub'])
                logger.info('RNNLM weight (sub): %.3f' % args.rnnlm_weight_sub)
            else:
                config['rnnlm_config_sub'] = None

            # Load the ASR model
            model = load(model_type=config['model_type'],
                         config=config,
                         backend=config['backend'])

            # Restore the saved parameters
            epoch, _, _, _ = model.load_checkpoint(
                save_path=args.model_path, epoch=args.epoch)

            # For shallow fusion
            if not (config['rnnlm_fusion_type'] and config['rnnlm_path']) and args.rnnlm_path is not None and args.rnnlm_weight > 0:
                # Load a RNNLM config file
                config_rnnlm = load_config(
                    join(args.rnnlm_path, 'config.yml'), is_eval=True)
                assert config['label_type'] == config_rnnlm['label_type']
                config_rnnlm['num_classes'] = eval_set.num_classes

                # Load the pre-trianed RNNLM
                rnnlm = load(model_type=config_rnnlm['model_type'],
                             config=config_rnnlm,
                             backend=config_rnnlm['backend'])
                rnnlm.load_checkpoint(save_path=args.rnnlm_path, epoch=-1)
                rnnlm.rnn.flatten_parameters()
                model.rnnlm_0_fwd = rnnlm
                logger.info('RNNLM path (main): %s' % args.rnnlm_path)
                logger.info('RNNLM weight (main): %.3f' % args.rnnlm_weight)

            if not (config['rnnlm_fusion_type'] and config['rnnlm_path_sub']) and args.rnnlm_path_sub is not None and args.rnnlm_weight_sub > 0:
                # Load a RNNLM config file
                config_rnnlm_sub = load_config(
                    join(args.rnnlm_path_sub, 'config.yml'), is_eval=True)
                assert config['label_type_sub'] == config_rnnlm_sub['label_type']
                config_rnnlm_sub['num_classes'] = eval_set.num_classes_sub

                # Load the pre-trianed RNNLM
                rnnlm_sub = load(model_type=config_rnnlm_sub['model_type'],
                                 config=config_rnnlm_sub,
                                 backend=config_rnnlm_sub['backend'])
                rnnlm_sub.load_checkpoint(
                    save_path=args.rnnlm_path_sub, epoch=-1)
                rnnlm_sub.rnn.flatten_parameters()
                model.rnnlm_1_fwd = rnnlm_sub
                logger.info('RNNLM path (sub): %s' % args.rnnlm_path_sub)
                logger.info('RNNLM weight (sub): %.3f' % args.rnnlm_weight_sub)

            # GPU setting
            model.set_cuda(deterministic=False, benchmark=True)

            logger.info('beam width (main): %d' % args.beam_width)
            logger.info('beam width (sub) : %d' % args.beam_width_sub)
            logger.info('epoch: %d' % (epoch - 1))
            logger.info('a2c oracle: %s' % str(args.a2c_oracle))
            logger.info('resolving_unk: %s' % str(args.resolving_unk))
            logger.info('joint_decoding: %s' % str(args.joint_decoding))
            logger.info('score_sub_weight : %f' % args.score_sub_weight)

        wer, df = eval_word(
            models=[model],
            dataset=eval_set,
            eval_batch_size=args.eval_batch_size,
            beam_width=args.beam_width,
            max_decode_len=MAX_DECODE_LEN_WORD,
            min_decode_len=MIN_DECODE_LEN_WORD,
            min_decode_len_ratio=MIN_DECODE_LEN_RATIO_WORD,
            beam_width_sub=args.beam_width_sub,
            max_decode_len_sub=MAX_DECODE_LEN_CHAR,
            min_decode_len_sub=MIN_DECODE_LEN_CHAR,
            min_decode_len_ratio_sub=MIN_DECODE_LEN_RATIO_CHAR,
            length_penalty=args.length_penalty,
            coverage_penalty=args.coverage_penalty,
            rnnlm_weight=args.rnnlm_weight,
            rnnlm_weight_sub=args.rnnlm_weight_sub,
            progressbar=True,
            resolving_unk=args.resolving_unk,
            a2c_oracle=args.a2c_oracle,
            joint_decoding=args.joint_decoding,
            score_sub_weight=args.score_sub_weight)
        wer_mean += wer
        logger.info('  WER (%s, main): %.3f %%' % (data_type, wer))
        logger.info(df)

        wer, cer, df = eval_char(
            models=[model],
            dataset=eval_set,
            eval_batch_size=args.eval_batch_size,
            beam_width=args.beam_width_sub,
            max_decode_len=MAX_DECODE_LEN_CHAR,
            min_decode_len=MIN_DECODE_LEN_CHAR,
            min_decode_len_ratio=MIN_DECODE_LEN_RATIO_CHAR,
            length_penalty=args.length_penalty,
            coverage_penalty=args.coverage_penalty,
            rnnlm_weight=args.rnnlm_weight_sub,
            progressbar=True)
        wer_sub_mean += wer
        cer_sub_mean += cer
        logger.info(' WER / CER (%s, sub): %.3f / %.3f %%' %
                    (data_type, wer, cer))
        logger.info(df)

    logger.info('  WER (mean, main): %.3f %%' % (wer_mean / 3))
    logger.info('  WER / CER (mean, sub): %.3f / %.3f %%' %
                (wer_sub_mean / 3, cer_sub_mean / 3))


if __name__ == '__main__':
    main()