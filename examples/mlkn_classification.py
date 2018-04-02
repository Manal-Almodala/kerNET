# -*- coding: utf-8 -*-
# torch 0.3.1

from __future__ import division, print_function

import numpy as np
import torch
from torch.autograd import Variable
from sklearn.datasets import load_iris, load_breast_cancer, load_digits
from sklearn.preprocessing import StandardScaler

import sys
sys.path.append('../kernet')
import backend as K
from models.mlkn import MLKNClassifier
from layers.kerlinear import kerLinear

torch.manual_seed(1234)

if __name__=='__main__':
    """
    This example demonstrates how a MLKN classifier works. Everything in here
    strictly follows this paper: https://arxiv.org/pdf/1802.03774.pdf.
    """
    # x, y = load_breast_cancer(return_X_y=True)
    x, y = load_digits(return_X_y=True)
    # x, y = load_iris(return_X_y=True)

    # standardize features to zero-mean and unit-variance
    normalizer = StandardScaler()
    x = normalizer.fit_transform(x)
    n_class = int(np.amax(y) + 1)

    dtype = torch.FloatTensor
    if torch.cuda.is_available():
        dtype = torch.cuda.FloatTensor
    X = Variable(torch.from_numpy(x).type(dtype), requires_grad=False)
    Y = Variable(torch.from_numpy(y).type(dtype), requires_grad=False)

    # randomly permute data
    new_index = torch.randperm(X.shape[0])
    X, Y = X[new_index], Y[new_index]

    # split data evenly into training and test
    index = len(X)//2
    x_train, y_train = X[:index], Y[:index]
    x_test, y_test = X[index:], Y[index:]

    mlkn = MLKNClassifier()
    # add layers to the model, see layers/kerlinear for details on kerLinear
    mlkn.add_layer(
        kerLinear(ker_dim=x_train.shape[0], out_dim=15, sigma=5, bias=True)
        )
    mlkn.add_layer(
        kerLinear(ker_dim=x_train.shape[0], out_dim=n_class, sigma=.1, bias=True)
        )
    # add optimizer for each layer, this works with any torch.optim.Optimizer
    mlkn.add_optimizer(
        torch.optim.Adam(params=mlkn.parameters(), lr=1e-3, weight_decay=0.1)
        )
    mlkn.add_optimizer(
        torch.optim.Adam(params=mlkn.parameters(), lr=1e-3, weight_decay=.1)
        )
    # specify loss function for the output layer, this works with any
    # PyTorch loss function but it is recommended that you use CrossEntropyLoss
    mlkn.add_loss(torch.nn.CrossEntropyLoss())
    # fit the model
    mlkn.fit(
        n_epoch=(30, 30),
        batch_size=30,
        shuffle=True,
        X=x_train,
        Y=y_train,
        n_class=n_class
        )
    # make a prediction on the test set and print error
    y_pred = mlkn.predict(X_test=x_test, X=x_train, batch_size=15)
    err = mlkn.get_error(y_pred, y_test)
    print('error rate: {:.2f}%'.format(err.data[0] * 100))
