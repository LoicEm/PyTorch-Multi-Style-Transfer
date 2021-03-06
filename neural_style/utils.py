##+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
## Created by: Hang Zhang
## ECE Department, Rutgers University
## Email: zhang.hang@rutgers.edu
## Copyright (c) 2017
##
## This source code is licensed under the MIT-style license found in the
## LICENSE file in the root directory of this source tree 
##+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

import os

import numpy as np
import torch
from PIL import Image
from torch.autograd import Variable
from torch.utils.serialization import load_lua

from neural_style.net import Vgg16

def tensor_load_rgbimage(filename, size=None, scale=None, keep_asp=False):
    """"Load an image as Torch.FloatTensor object
    filename : path to the file
    size : width of the resized image
    scale : if no size is specified, rescale the image to the given ratio.
    keep_asp : whether or not to keep the aspect ratio when resizing for a given size.
    If False, the resized image will be the same width and length"""
    img = Image.open(filename).convert('RGB')
    if size is not None:
        if keep_asp:
            size2 = int(size * 1.0 / img.size[0] * img.size[1])
            img = img.resize((size, size2), Image.ANTIALIAS)
        else:
            img = img.resize((size, size), Image.ANTIALIAS)

    elif scale is not None:
        img = img.resize((int(img.size[0] / scale), int(img.size[1] / scale)), Image.ANTIALIAS)
    img = np.array(img).transpose(2, 0, 1)
    img = torch.from_numpy(img).float()
    return img


def tensor_save_rgbimage(tensor, filename, cuda=False):
    if cuda:
        img = tensor.clone().cpu().clamp(0, 255).numpy()
    else:
        img = tensor.clone().clamp(0, 255).numpy()
    img = img.transpose(1, 2, 0).astype('uint8')
    img = Image.fromarray(img)
    img.save(filename)


def tensor_save_bgrimage(tensor, filename, cuda=False):
    (b, g, r) = torch.chunk(tensor, 3)
    tensor = torch.cat((r, g, b))
    tensor_save_rgbimage(tensor, filename, cuda)


def gram_matrix(y):
    (b, ch, h, w) = y.size()
    features = y.view(b, ch, w * h)
    features_t = features.transpose(1, 2)
    gram = features.bmm(features_t) / (ch * h * w)
    return gram


def subtract_imagenet_mean_batch(batch):
    """Subtract ImageNet mean pixel-wise from a BGR image."""
    tensortype = type(batch.data)
    mean = tensortype(batch.data.size())
    mean[:, 0, :, :] = 103.939
    mean[:, 1, :, :] = 116.779
    mean[:, 2, :, :] = 123.680
    return batch - Variable(mean)


def add_imagenet_mean_batch(batch):
    """Add ImageNet mean pixel-wise from a BGR image."""
    tensortype = type(batch.data)
    mean = tensortype(batch.data.size())
    mean[:, 0, :, :] = 103.939
    mean[:, 1, :, :] = 116.779
    mean[:, 2, :, :] = 123.680
    return batch + Variable(mean)

def imagenet_clamp_batch(batch, low, high):
    batch[:,0,:,:].data.clamp_(low-103.939, high-103.939)
    batch[:,1,:,:].data.clamp_(low-116.779, high-116.779)
    batch[:,2,:,:].data.clamp_(low-123.680, high-123.680)


def preprocess_batch(batch):
    """Preprocess the batch into a BGR image"""
    batch = batch.transpose(0, 1)
    (r, g, b) = torch.chunk(batch, 3)
    batch = torch.cat((b, g, r))
    batch = batch.transpose(0, 1)
    return batch


def init_vgg16(model_folder):
    """load the vgg16 model feature"""
    if not os.path.exists(os.path.join(model_folder, 'vgg16.weight')):
        if not os.path.exists(os.path.join(model_folder, 'vgg16.t7')):
            os.system(
                'wget http://cs.stanford.edu/people/jcjohns/fast-neural-style/models/vgg16.t7 -O ' + os.path.join(model_folder, 'vgg16.t7'))
        vgglua = load_lua(os.path.join(model_folder, 'vgg16.t7'))
        vgg = Vgg16()
        for (src, dst) in zip(vgglua.parameters()[0], vgg.parameters()):
            dst.data[:] = src
        torch.save(vgg.state_dict(), os.path.join(model_folder, 'vgg16.weight'))


class StyleLoader():
    def __init__(self, style_folder, style_size, cuda=True):
        self.folder = style_folder
        self.style_size = style_size
        self.files = os.listdir(style_folder)
        self.cuda = cuda
    
    def get(self, i):
        idx = i%len(self.files)
        filepath = os.path.join(self.folder, self.files[idx])
        style = tensor_load_rgbimage(filepath, self.style_size)    
        style = style.unsqueeze(0)
        style = preprocess_batch(style)
        if self.cuda:
            style = style.cuda()
        style_v = Variable(style, requires_grad=False)
        return style_v

    def size(self):
        return len(self.files)

def matSqrt(x):
    U,D,V = torch.svd(x)
    return U * (D.pow(0.5).diag()) * V.t()

def color_match(src, dst, cuda=False):
    src_flat = src.view(3,-1)
    dst_flat = dst.view(3,-1)

    src_mean = src_flat.mean(1, True)
    src_std = src_flat.std(1, True)
    src_norm = (src_flat - src_mean) / src_std

    dst_mean = dst_flat.mean(1, True) 
    dst_std = dst_flat.std(1, True)
    dst_norm = (dst_flat - dst_mean) / dst_std

    # Load on cuda if available otherwise not
    cud = cuda and torch.cuda.is_available() # TODO add this as an argument

    if cud :
        src_flat_cov_eye = src_norm @ src_norm.t() + Variable(torch.eye(3).cuda())
        dst_flat_cov_eye = dst_norm @ dst_norm.t() + Variable(torch.eye(3).cuda())
    else : # Without cuda
        src_flat_cov_eye = src_norm @ src_norm.t() + Variable(torch.eye(3))
        dst_flat_cov_eye = dst_norm @ dst_norm.t() + Variable(torch.eye(3))

    src_flat_nrom_trans = matSqrt(dst_flat_cov_eye) * matSqrt(src_flat_cov_eye).inverse() @ src_norm
    src_flat_transfer = src_flat_nrom_trans * dst_std + dst_mean
    return src_flat_transfer.view_as(src)
