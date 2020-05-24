"""
©Copyright 2020 University of Florida Research Foundation, Inc. All rights reserved.
Licensed under the CC BY-NC-SA 4.0 license (https://creativecommons.org/licenses/by-nc-sa/4.0/legalcode).

Modular training example.
"""
import torch

import kernet_future.utils as utils
import kernet_future.models as models
import kernet_future.layers.loss as losses
import kernet_future.datasets as datasets
from kernet_future.parsers import TrainParser
from kernet_future.trainers.trainer import Trainer
from kernet_future.engines import train_hidden, train_output
from kernet_future.trainers.adversarial_trainer import AdversarialTrainer


loss_names = ['srs_raw', 'srs_nmse', 'srs_alignment', 'srs_upper_tri_alignment', 'srs_contrastive', 'srs_log_contrastive']


def modify_commandline_options(parser, **kwargs):
  parser.add_argument('--hidden_objective',
                      choices=loss_names + [_ + '_neo' for _ in loss_names],
                      default='srs_alignment',
                      help='Proxy hidden objective.')
  parser.add_argument('--use_proj_head', type=utils.str2bool,
                      nargs='?', const=True, default=False,
                      help='Whether to attach a trainable two-layer MLP projection head to the ' + \
                           'output of the hidden modules during training. If added, the heads project ' + \
                      'all activations to the same Euclidean space with dimension determined by head_size.')
  parser.add_argument('--split_mode', type=int, default=1,
                      help='The mode to perform the split. Effective only for certain networks.')
  parser.add_argument('--head_size', type=int, default=512,
                      help='Output size of the projection head.')
  n_parts = kwargs["n_parts"]
  for i in range(1, n_parts + 1):
    parser.add_argument('--lr{}'.format(i), type=float, default=1e-3,
                      help='Initial learning rate for part {}.'.format(i))
    parser.add_argument('--momentum{}'.format(i), type=float, default=.9,
                      help='Momentum for the SGD optimizer for part {}.'.format(i))
    parser.add_argument('--weight_decay{}'.format(i), type=float, default=5e-4,
                      help='L2 regularization on the model weights for part {}.'.format(i))
    parser.add_argument('--n_epochs{}'.format(i), type=int, default=200,
                      help='The number of training epochs for part {}.'.format(i))
  return parser


def main():
  opt = TrainParser().parse()

  # set up logger
  utils.set_logger(opt=opt, filename='train.log', filemode='w')

  if opt.seed:
    utils.make_deterministic(opt.seed)
  loader = datasets.get_dataloaders(opt)

  # TODO a hacky way to load some dummy validation data
  opt.is_train = False
  val_loader = datasets.get_dataloaders(opt)
  opt.is_train = True

  model = models.get_model(opt)
  model = model.to(device)
  modules, params = model.split(n_parts=opt.n_parts, mode=opt.split_mode)

  trainer_cls = AdversarialTrainer if opt.adversarial else Trainer

  output_layer = list(model.children())[-1]
  hidden_criterion = getattr(losses, opt.hidden_objective)(output_layer.phi, opt.n_classes)
  output_criterion = torch.nn.CrossEntropyLoss()

  optimizers, trainers = [], []
  for i in range(1, opt.n_parts + 1):
    optimizers.append(utils.get_optimizer(
      opt,
      params=params[i - 1],
      lr=getattr(opt, 'lr{}'.format(i)),
      weight_decay=getattr(opt, 'weight_decay{}'.format(i)),
      momentum=getattr(opt, 'momentum{}'.format(i))
      ))
    trainer = trainer_cls(
      opt=opt,
      model=modules[i - 1],
      set_eval=modules[i - 2] if i > 1 else None,
      optimizer=optimizers[i - 1],
      val_metric_name=opt.hidden_objective if i < opt.n_parts else 'acc',
      val_metric_obj='max'
      )
    trainers.append(trainer)

    if opt.load_model:
      if i < opt.n_parts: # load hidden layer
        trainers[i - 1].load('net_part{}.pth'.format(i))
      else: # load output layer
        trainers[i - 1].load('net.pth')

  # save init model
  trainers[0].save(
    epoch=trainers[0].start_epoch - 1,
    val_metric_value=trainers[0].best_val_metric,
    model_name='net_part{}.pth'.format(1),
    force_save=True
  )
  # train the first hidden module
  train_hidden(opt, n_epochs=opt.n_epochs1, trainer=trainers[0],
      loader=loader, val_loader=val_loader, criterion=hidden_criterion, part_id=1, device=device)

  # train other hidden modules
  for i in range(2, opt.n_parts):
    # save init model
    trainers[i - 1].save(
      epoch=trainers[i - 1].start_epoch - 1,
      val_metric_value=trainers[i - 1].best_val_metric,
      model_name='net_part{}.pth'.format(i),
      force_save=True
    )
    # prepare centers
    utils.update_centers_eval(model)
    # exclude certain network part(s) from the graph to make things faster
    utils.exclude_during_backward(modules[i - 2])
    train_hidden(
      opt,
      n_epochs=getattr(opt, 'n_epochs{}'.format(i)),
      trainer=trainers[i - 1],
      loader=loader,
      val_loader=val_loader,
      criterion=hidden_criterion,
      part_id=i,
      device=device
    )

  # save init model
  trainers[-1].save(
    epoch=trainers[-1].start_epoch - 1,
    val_metric_value=trainers[-1].best_val_metric,
    model_name='net.pth',
    force_save=True
  )
  # train output layer
  utils.update_centers_eval(model)
  utils.exclude_during_backward(modules[-2])
  train_output(
    opt,
    n_epochs=getattr(opt, 'n_epochs{}'.format(opt.n_parts)),
    trainer=trainers[-1],
    loader=loader,
    val_loader=val_loader,
    criterion=output_criterion,
    part_id=opt.n_parts,
    device=device
  )
  utils.include_during_backward(modules[-2])


if __name__=='__main__':
  device = 'cuda' if torch.cuda.is_available() else 'cpu'
  if device == 'cuda':
    torch.backends.cudnn.benchmark = True
  main()
