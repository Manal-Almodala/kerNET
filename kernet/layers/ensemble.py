# -*- coding: utf-8 -*-
# torch 0.3.1

import torch
from torch.autograd import Variable

import sys
sys.path.append('../kernet')
import backend as K
from layers.kerlinear import kerLinear

torch.manual_seed(1234)

class _ensemble(torch.nn.Module):
    def __init__(self):
        super(_ensemble, self).__init__()
        self._comp_counter = 0
    def add(self,):
        raise NotImplementedError('Must be implemented by subclass.')
    def forward(self,):
        raise NotImplementedError('Must be implemented by subclass.')

class kerLinearEnsemble(_ensemble):

    def __init__(self):
        super(kerLinearEnsemble, self).__init__()
        self.X = self._X() # generator for X's
        self.weight = self._weight()
        self.bias = self._bias()

    def _X(self):
        """
        Generate an iterable of X's from each component kerLinear layer in this
        ensemble.
        """
        for i in range(self._comp_counter):
            comp = getattr(self, 'comp'+str(i))
            yield comp.X

    def _weight(self):
        """
        Generate weights of each component in the order in which the components
        were added.
        """
        for i in range(self._comp_counter):
            comp = getattr(self, 'comp'+str(i))
            yield comp.weight

    def _bias(self):
        """
        Generate bias of each component in the order in which the components
        were added.
        """
        for i in range(self._comp_counter):
            comp = getattr(self, 'comp'+str(i))
            yield comp.bias

    def add(self, component):
        assert isinstance(component, kerLinear)
        setattr(self, 'comp'+str(self._comp_counter), component)
        self._comp_counter += 1
        self.sigma = component.sigma # TODO: allow components to have different
        # sigma?

    def forward(self, x):
    # TODO: under shuffle mode, fit gives different
    # results if substitute normal layers with ensemble layers, checked that
    # the randperm vectors in K.rand_shuffle are different in two modes, why?
        out_dims = [(
            getattr(self, 'comp'+str(i)).out_dim
            ) for i in range(self._comp_counter)]
        # out_dims of all comps should be equal
        assert out_dims.count(out_dims[0])==len(out_dims)

        out_dim = out_dims[0]

        y = Variable(torch.FloatTensor(x.shape[0], out_dim).zero_())
        if x.is_cuda: y=y.cuda()

        for i in range(self._comp_counter):
            component = getattr(self, 'comp'+str(i))
            y = y.add(component.forward(x))
        self.out_dim = out_dim
        return y

if __name__=='__main__':
    dtype = torch.FloatTensor
    if torch.cuda.is_available():
        dtype = torch.cuda.FloatTensor

    x = Variable(torch.FloatTensor([[0, 7], [1, 2]]).type(dtype))
    X = Variable(torch.FloatTensor([[1, 2], [3, 4], [5, 6]]).type(dtype))
    y = Variable(torch.FloatTensor([[.3], [.9]]).type(dtype))

    linear_ens = kerLinearEnsemble()
    linear_ens.add(kerLinear(X[:2], out_dim=1, sigma=1, bias=True))
    linear_ens.add(kerLinear(X[2:], out_dim=1, sigma=1, bias=False))
    linear_ens.comp1.weight.data = torch.FloatTensor([[1.5]])
    linear_ens.comp0.weight.data = torch.FloatTensor([[.5, .6]])
    linear_ens.comp0.bias.data = torch.FloatTensor([[2.5]])
    y = linear_ens(x)
    print(y)

    l = kerLinear(X, out_dim=1, sigma=1, bias=True)
    l.weight.data = torch.FloatTensor([[.5, .6, 1.5]])
    l.bias.data = torch.FloatTensor([[2.5]])
    y = l(x)
    print(y)
