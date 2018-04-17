#!/usr/bin/env python3

'''
The fits object gets access to a lib2dl object and performs fits and statistical tests to data or MC simulation
'''

__author__ = 'E. David-Bosne'
__email__ = 'eric.bosne@cern.ch'

from .lib2dl import lib2dl
from .patterncreator import PatternCreator, create_detector_mesh
from .MedipixMatrix import MedipixMatrix


import numpy as np
import numpy.ma as ma
import scipy.optimize as op
import scipy.stats as st
import math
import numdifftools as nd
from scipy.ndimage import gaussian_filter



class fits:
    def __init__(self,lib):
        assert isinstance(lib,lib2dl)
        self.lib = lib
        # self.pattern_1_n = 0
        # self.pattern_1_use = True
        # self.pattern_2_n = None
        # self.pattern_2_use = False
        # self.pattern_3_n = None
        # self.pattern_3_use = False
        self.n_events = None
        self.n_events_set = False
        # self.fit_n_events = False
        self.XXmesh = None
        self.YYmesh = None
        self.data_pattern = None
        self.sim_pattern = None
        self.data_pattern_is_set = False
        #self.p0 = (None,)
        #self.p0_scale = np.ones((8))
        self.results = None
        self.variance = None
        self.pattern_generator = None
        #self.sub_pixels = 1

        self.parameters_dict = None
        self._init_parameters_dict()
        self._parameters_order = ('dx', 'dy', 'phi', 'total_cts', 'sigma', 'f_p1', 'f_p2', 'f_p3')
        self._pattern_keys = ('pattern_1', 'pattern_2', 'pattern_3')
        self._ml_fit_options = {'disp': False, 'maxiter': 30, 'maxfun': 300, 'ftol': 1e-8,'maxcor': 100}
        self._chi2_fit_options = {'disp': False, 'maxiter': 30, 'maxfun': 300, 'ftol': 1e-4, 'maxcor': 100}

        self.verbose_graphics = False
        self.verbose_graphics_ax = None
        self.verbose_graphics_fg = None

    def _init_parameters_dict(self):
        parameter_template = \
            {'p0':None, 'value':None, 'use':False, 'variance':None, 'scale':1, 'bounds':(None,None)}
        # parameters are, site 1 2 and 3,dx,dy,phi,total_cts,f_p1,f_p2,f_p3
        # keys are 'pattern_1','pattern_2','pattern_3','sub_pixels','dx','dy','phi',
        # 'total_cts','sigma','f_p1','f_p2','f_p3'
        self.parameters_dict = {
            'pattern_1': parameter_template.copy(),  # site 1
            'pattern_2': parameter_template.copy(),  # site 2
            'pattern_3': parameter_template.copy(),  # site 3
            'sub_pixels': parameter_template.copy(),  # sub pixels for convolution
            'dx': parameter_template.copy(),  # delta x
            'dy': parameter_template.copy(),  # delta y
            'phi': parameter_template.copy(),  # rotation
            'total_cts': parameter_template.copy(), #total counts
            'sigma': parameter_template.copy(),  # sigma convolution
            'f_p1': parameter_template.copy(),  # fraction site 1
            'f_p2': parameter_template.copy(),  # fraction site 2
            'f_p3': parameter_template.copy(),  # fraction site 3
        }
        self.set_inicial_values()
        self.set_scale_values()
        self.set_bound_values()
        self.fix_parameters(dx=False, dy=False, phi=False, total_cts=False,
                            sigma=False, f_p1=False, f_p2=True, f_p3=True)

        self.parameters_dict['pattern_1']['value'] = 0
        self.parameters_dict['pattern_2']['value'] = 0
        self.parameters_dict['pattern_3']['value'] = 0
        self.parameters_dict['sub_pixels']['value'] = 1

    def set_inicial_values(self, dx=1, dy=1, phi=5, total_cts=1, sigma=0, f_p1=0.25, f_p2=0.25, f_p3=0.25):
        # parameter keys 'dx', 'dy', 'phi', 'total_cts', 'sigma', 'f_p1', 'f_p2', 'f_p3'
        self.parameters_dict['dx']['p0'] = dx
        self.parameters_dict['dy']['p0'] = dy
        self.parameters_dict['phi']['p0'] = phi
        self.parameters_dict['total_cts']['p0'] = total_cts
        self.parameters_dict['sigma']['p0'] = sigma
        self.parameters_dict['f_p1']['p0'] = f_p1
        self.parameters_dict['f_p2']['p0'] = f_p2
        self.parameters_dict['f_p3']['p0'] = f_p3

    def set_scale_values(self, dx=1, dy=1, phi=1, total_cts=1, sigma=1, f_p1=1, f_p2=1, f_p3=1):
        # parameter keys 'dx', 'dy', 'phi', 'total_cts', 'sigma', 'f_p1', 'f_p2', 'f_p3'
        self.parameters_dict['dx']['scale'] = dx
        self.parameters_dict['dy']['scale'] = dy
        self.parameters_dict['phi']['scale'] = phi
        self.parameters_dict['total_cts']['scale'] = total_cts
        self.parameters_dict['sigma']['scale'] = sigma
        self.parameters_dict['f_p1']['scale'] = f_p1
        self.parameters_dict['f_p2']['scale'] = f_p2
        self.parameters_dict['f_p3']['scale'] = f_p3

    def set_bound_values(self, dx=(-3, +3), dy=(-3, +3), phi=(None, None),
                         total_cts=(0, None), sigma=(0, None),
                         f_p1=(0, 1), f_p2=(0, 1), f_p3=(0, 1)):
        # parameter keys 'dx', 'dy', 'phi', 'total_cts', 'sigma', 'f_p1', 'f_p2', 'f_p3'
        self.parameters_dict['dx']['bounds'] = dx
        self.parameters_dict['dy']['bounds'] = dy
        self.parameters_dict['phi']['bounds'] = phi
        self.parameters_dict['total_cts']['bounds'] = total_cts
        self.parameters_dict['sigma']['bounds'] = sigma
        self.parameters_dict['f_p1']['bounds'] = f_p1
        self.parameters_dict['f_p2']['bounds'] = f_p2
        self.parameters_dict['f_p3']['bounds'] = f_p3

    def fix_parameters(self, dx, dy, phi, total_cts, sigma,
                       f_p1, f_p2, f_p3):
        # parameter keys 'dx', 'dy', 'phi', 'total_cts', 'sigma', 'f_p1', 'f_p2', 'f_p3'
        self.parameters_dict['dx']['use'] = not dx
        self.parameters_dict['dy']['use'] = not dy
        self.parameters_dict['phi']['use'] = not phi
        self.parameters_dict['total_cts']['use'] = not total_cts
        self.parameters_dict['sigma']['use'] = not sigma

        if self.parameters_dict['pattern_1']['use']:
            self.parameters_dict['f_p1']['use'] = not f_p1
        else:
            self.parameters_dict['f_p1']['use'] = False

        if self.parameters_dict['pattern_2']['use']:
            self.parameters_dict['f_p2']['use'] = not f_p2
        else:
            self.parameters_dict['f_p2']['use'] = False

        if self.parameters_dict['pattern_3']['use']:
            self.parameters_dict['f_p3']['use'] = not f_p3
        else:
            self.parameters_dict['f_p3']['use'] = False


    def set_optimization_profile(self,profile='default'):
        if profile == 'coarse':
            self._ml_fit_options =   {'disp':False, 'maxiter':15, 'maxfun':200, 'ftol':1e-7, 'maxcor':100}
            self._chi2_fit_options = {'disp':False, 'maxiter':15, 'maxfun':200, 'ftol':1e-3, 'maxcor':100}
        elif profile == 'default':
            self._ml_fit_options =   {'disp':False, 'maxiter':30, 'maxfun':300, 'ftol':1e-8, 'maxcor':100}
            self._chi2_fit_options = {'disp':False, 'maxiter':30, 'maxfun':300, 'ftol':1e-4, 'maxcor':100}
        elif profile == 'fine':
            self._ml_fit_options =   {'disp':False, 'maxiter':50, 'maxfun':600, 'ftol':1e-9, 'maxcor':100}
            self._chi2_fit_options = {'disp':False, 'maxiter':50, 'maxfun':600, 'ftol':1e-5, 'maxcor':100}
        else:
            raise ValueError('profile value should be set to: coarse, default or fine.')

    def _get_p0_scale(self):
        # order of params is dx,dy,phi,total_cts,f_p1,f_p2,f_p3
        p0_scale = ()
        for key in self._parameters_order:
            if self.parameters_dict[key]['use']:
                p0_scale += (self.parameters_dict[key]['scale'],)
        return np.array(p0_scale)

    def _get_p0(self):
        # order of params is dx,dy,phi,total_cts,f_p1,f_p2,f_p3
        p0 = ()
        for key in self._parameters_order:
            if self.parameters_dict[key]['use']:
                temp_p0 = self.parameters_dict[key]['p0'] / self.parameters_dict[key]['scale']
                p0 += (temp_p0,)
        return np.array(p0)

    def set_data_pattern(self, XXmesh, YYmesh, pattern):
        self.XXmesh = XXmesh.copy()
        self.YYmesh = YYmesh.copy()
        self.data_pattern = pattern.copy()
        self.data_pattern_is_set = True
        self.n_events = self.data_pattern.sum()
        self.n_events_set = True

    def set_patterns_to_fit(self, p1_n=None, p2_n=None, p3_n=None):
        if p1_n is not None:
            self.parameters_dict['pattern_1']['value'] = p1_n
            self.parameters_dict['pattern_1']['use'] = True
            self.parameters_dict['f_p1']['use'] = True
        else:
            self.parameters_dict['pattern_1']['use'] = False
            self.parameters_dict['f_p1']['use'] = False

        if p2_n is not None:
            self.parameters_dict['pattern_2']['value'] = p2_n
            self.parameters_dict['pattern_2']['use'] = True
            self.parameters_dict['f_p2']['use'] = True
        else:
            self.parameters_dict['pattern_2']['use'] = False
            self.parameters_dict['f_p2']['use'] = False

        if p3_n is not None:
            self.parameters_dict['pattern_3']['value'] = p3_n
            self.parameters_dict['pattern_3']['use'] = True
            self.parameters_dict['f_p3']['use'] = True
        else:
            self.parameters_dict['pattern_3']['use'] = False
            self.parameters_dict['f_p3']['use'] = False

    def print_variance(self,x,var):
        # TODO remove
        # order of params is dx,dy,phi,total_cts,f_p1,f_p2,f_p3
        params = x
        dx = params[0]
        d_dx = var[0]
        dy = params[1]
        d_dy = var[1]
        phi = params[2]
        d_phi = var[2]
        N_rand = params[3]
        d_N_rand = var[3]
        N_p1 = params[4] if self.pattern_1_use else 0
        d_N_p1 = var[4] if self.pattern_1_use else 0
        N_p2 = params[5] if self.pattern_2_use else 0
        d_N_p2 = var[5] if self.pattern_2_use else 0
        N_p3 = params[6] if self.pattern_3_use else 0
        d_N_p3 = var[6] if self.pattern_3_use else 0

        total_f = N_rand + N_p1 + N_p2 + N_p3
        f_rand = N_rand / total_f
        f_1 = N_p1 / total_f
        f_2 = N_p2 / total_f
        f_3 = N_p3 / total_f
        print('rand', N_rand, d_N_rand)
        print('p1', N_p1, d_N_p1)
        d_f_rand = np.abs(d_N_rand / total_f \
                          - N_rand * (
                          d_N_rand / total_f ** 2 + d_N_p1 / total_f ** 2 + d_N_p2 / total_f ** 2 + d_N_p3 / total_f ** 2))
        d_f_1 = np.abs(d_N_p1 / total_f \
                       - N_p1 * (
                       d_N_rand / total_f ** 2 + d_N_p1 / total_f ** 2 + d_N_p2 / total_f ** 2 + d_N_p3 / total_f ** 2))
        d_f_2 = np.abs(d_N_p2 / total_f \
                       - N_p2 * (
                       d_N_rand / total_f ** 2 + d_N_p1 / total_f ** 2 + d_N_p2 / total_f ** 2 + d_N_p3 / total_f ** 2))
        d_f_3 = np.abs(d_N_p3 / total_f \
                       - N_p3 * (
                       d_N_rand / total_f ** 2 + d_N_p1 / total_f ** 2 + d_N_p2 / total_f ** 2 + d_N_p3 / total_f ** 2))

        res = {'dx': dx, 'd_dx': d_dx,
               'dy': dy, 'd_dy': d_dy,
               'phi': phi, 'd_phi': d_phi,
               'f_rand': f_rand, 'd_f_rand': d_f_rand,
               'f_1': f_1, 'd_f_1': d_f_1,
               'f_2': f_2, 'd_f_2': d_f_2,
               'f_3': f_3, 'd_f_3': d_f_3}

        print(('dx     = {dx:.4f} +- {d_dx:.4f}\n' +
               'dy     = {dy:.4f} +- {d_dy:.4f}\n' +
               'phi    = {phi:.4f} +- {d_phi:.4f}\n' +
               'f_rand = {f_rand:.4f} +- {d_f_rand:.4f}\n' +
               'f_1    = {f_1:.4f} +- {d_f_1:.4f}\n' +
               'f_2    = {f_2:.4f} +- {d_f_2:.4f}\n' +
               'f_3    = {f_3:.4f} +- {d_f_3:.4f}').format(**res))

        return res

# methods for chi-square minimization
    def chi_square_fun(self, experimental_data, simlulation_data):
        # delta degrees of freedom
        # dx, dy, phi
        ddof = 3
        ddof += 1 if self.pattern_1_use else 0
        ddof += 1 if self.pattern_2_use else 0
        ddof += 1 if self.pattern_2_use else 0
        return st.chisquare(experimental_data, simlulation_data,ddof,axis=None)

    def chi_square(self, dx, dy, phi, total_events, fractions_sims, sigma=0):
        """
        Calculates the Pearson chi2 for the given conditions.
        :param dx: delta x in angles
        :param dy: delta y in angles
        :param phi: delta phi in anlges
        :param total_events: total number of events
        :param simulations: simulations id number
        :param fractions_sims: fractions of each simulated pattern
        :param sigma: sigma of the gaussian to convolute the pattern, smooting
        :return: Pearson's chi2
        """
        # set data pattern
        data_pattern = self.data_pattern
        fractions_sims = np.array(fractions_sims)
        rnd_events = np.array([1 - fractions_sims.sum()])
        # generate sim pattern
        gen = self.pattern_generator
        fractions = np.concatenate((rnd_events, fractions_sims))
        sim_pattern = gen.make_pattern(dx, dy, phi, fractions, total_events, sigma=sigma, type='ideal')
        self.sim_pattern = sim_pattern.copy()
        # chi2, pval = self.chi_square_fun(data_pattern,sim_pattern)
        chi2 = np.sum((data_pattern - sim_pattern) ** 2 / np.abs(sim_pattern))
        #print('chi2 - ', chi2)
        # print('p-value - ',pval)
        # =====
        if self.verbose_graphics:
            if self.verbose_graphics_ax is None or self.verbose_graphics_fg is None:
                fg = plt.figure()
                self.verbose_graphics_fg = fg
                ax = fg.add_subplot(111)
                self.verbose_graphics_ax = ax
                plt.show(block=False)
            plt.sca(self.verbose_graphics_ax)
            self.verbose_graphics_ax.clear()
            plt.ion()
            plt.contourf(self.XXmesh, self.YYmesh, sim_pattern) #(data_pattern-sim_pattern))
            self.verbose_graphics_fg.canvas.draw()
        # =====
        return chi2

    def chi_square_call(self, params, enable_scale=False):
        # order of params is dx,dy,phi,total_cts,f_p1,f_p2,f_p3
        # print('params ', params)
        p0_scale = self._get_p0_scale() if enable_scale else np.ones(len(params))
        #print('p0_scale ', p0_scale)
        params_temp = ()
        di = 0
        for key in self._parameters_order:
            if self.parameters_dict[key]['use']:
                params_temp += (params[di] * p0_scale[di],)
                di += 1
            else:
                params_temp += (self.parameters_dict[key]['p0'],)
        # print('params_temp - ',params_temp)

        dx, dy, phi, total_cts, sigma, f_p1, f_p2, f_p3 = params_temp
        fractions_sims = ()
        fractions_sims += (f_p1,) if self.parameters_dict['pattern_1']['use'] else ()  # pattern 1
        fractions_sims += (f_p2,) if self.parameters_dict['pattern_2']['use'] else ()  # pattern 2
        fractions_sims += (f_p3,) if self.parameters_dict['pattern_3']['use'] else ()  # pattern 3
        #print('fractions_sims - ', fractions_sims)
        return self.chi_square(dx, dy, phi, total_cts, fractions_sims=fractions_sims, sigma=sigma)

    def minimize_chi2(self):

        # order of params is dx,dy,phi,total_cts,sigma,f_p1,f_p2,f_p3
        p0 = self._get_p0()
        #print('p0 - ', p0)

        # Parameter bounds
        bnds = ()
        for key in self._parameters_order:
            if self.parameters_dict[key]['use']:
                bnds += (self.parameters_dict[key]['bounds'],)
                # print('bnds - ', bnds)

        # get patterns
        simulations = ()
        for key in self._pattern_keys:
            if self.parameters_dict[key]['use']:
                simulations += (self.parameters_dict[key]['value'],)
        # print('simulations - ', simulations)

        # generate sim pattern
        self.pattern_generator = PatternCreator(self.lib, self.XXmesh, self.YYmesh, simulations,
                                                mask=self.data_pattern.mask,
                                                sub_pixels=self.parameters_dict['sub_pixels']['value'])

        res = op.minimize(self.chi_square_call, p0, args=True, method='L-BFGS-B', bounds=bnds,\
                           options=self._chi2_fit_options) # dont change defaut eps

        di = 0
        for key in self._parameters_order:
            if self.parameters_dict[key]['use']:
                res['x'][di] *= self.parameters_dict[key]['scale']
                self.parameters_dict[key]['value'] = res['x'][di]
                di += 1
            else:
                self.parameters_dict[key]['value'] = self.parameters_dict[key]['p0']

        self.results = res

# methods for maximum likelihood
    def log_likelihood(self, dx, dy, phi, fractions_sims, sigma=0):
        """
        Calculates the Pearson chi2 for the given conditions.
        :param dx: delta x in angles
        :param dy: delta y in angles
        :param phi: delta phi in anlges
        :param simulations: simulations id number
        :param fractions_sims: fractions of each simulated pattern
        :param sigma: sigma of the gaussian to convolute the pattern, smooting
        :return: likelihood
        """
        # set data pattern
        data_pattern = self.data_pattern
        #if not len(simulations) == len(fractions_sims):
        #    raise ValueError("size o simulations is diferent than size o events")
        total_events = 1
        fractions_sims = np.array(fractions_sims)
        rnd_events = np.array([1 - fractions_sims.sum()])
        # generate sim pattern
        gen = self.pattern_generator
        # gen = PatternCreator(self.lib, self.XXmesh, self.YYmesh, simulations, mask=data_pattern.mask)
        fractions = np.concatenate((rnd_events, fractions_sims))
        sim_pattern = gen.make_pattern(dx, dy, phi, fractions, total_events, sigma=sigma, type='ideal')
        self.sim_pattern = sim_pattern.copy()
        # log likelihood
        ll = np.sum(data_pattern * np.log(sim_pattern))
        # extended log likelihood - no need to fit events
        #ll = -np.sum(events_per_sim) + np.sum(data_pattern * np.log(sim_pattern))
        #print('likelihood - ', ll)
        # =====
        if self.verbose_graphics:
            if self.verbose_graphics_ax is None or self.verbose_graphics_fg is None:
                fg = plt.figure()
                self.verbose_graphics_fg = fg
                ax = fg.add_subplot(111)
                self.verbose_graphics_ax = ax
                plt.show(block=False)
            plt.sca(self.verbose_graphics_ax)
            plt.ion()
            plt.contourf(self.XXmesh, self.YYmesh, sim_pattern)  # (data_pattern-sim_pattern))
            self.verbose_graphics_fg.canvas.draw()
        # =====
        return -ll

    def log_likelihood_call(self, params, enable_scale=False):
        # order of params is dx,dy,phi,total_cts,f_p1,f_p2,f_p3
        #print('params ', params)
        p0_scale = self._get_p0_scale() if enable_scale else np.ones(len(params))
        # print('p0_scale ', p0_scale)
        params_temp = ()
        di = 0
        for key in self._parameters_order:
            if self.parameters_dict[key]['use']:
                params_temp += (params[di] * p0_scale[di],)
                di += 1
            else:
                params_temp += (self.parameters_dict[key]['p0'],)
        #print('params_temp - ',params_temp)

        dx, dy, phi, total_cts, sigma, f_p1, f_p2, f_p3 = params_temp
        fractions_sims = ()
        fractions_sims += (f_p1,) if self.parameters_dict['pattern_1']['use'] else () # pattern 1
        fractions_sims += (f_p2,) if self.parameters_dict['pattern_2']['use'] else () # pattern 2
        fractions_sims += (f_p3,) if self.parameters_dict['pattern_3']['use'] else () # pattern 3
        #print('fractions_sims - ', fractions_sims)
        return self.log_likelihood(dx, dy, phi, fractions_sims, sigma=sigma)

    def maximize_likelyhood(self):

        # total counts is not used in maximum likelyhood
        self.parameters_dict['total_cts']['use'] = False

        # order of params is dx,dy,phi,sigma,f_p1,f_p2,f_p3
        p0 = self._get_p0()
        #print('p0 - ', p0)

        # Parameter bounds
        bnds = ()
        for key in self._parameters_order:
            if self.parameters_dict[key]['use']:
                bnds += (self.parameters_dict[key]['bounds'],)
        #print('bnds - ', bnds)

        # get patterns
        simulations = ()
        for key in self._pattern_keys:
            if self.parameters_dict[key]['use']:
                simulations += (self.parameters_dict[key]['value'],)
        #print('simulations - ', simulations)

        # generate sim pattern
        self.pattern_generator = PatternCreator(self.lib, self.XXmesh, self.YYmesh, simulations,
                                                mask=self.data_pattern.mask,
                                                sub_pixels=self.parameters_dict['sub_pixels']['value'])

        res = op.minimize(self.log_likelihood_call, p0, args=True, method='L-BFGS-B', bounds=bnds,\
                           options=self._ml_fit_options) #'eps': 0.0001,

        di = 0
        for key in self._parameters_order:
            if self.parameters_dict[key]['use']:
                res['x'][di] *= self.parameters_dict[key]['scale']
                self.parameters_dict[key]['value'] = res['x'][di]
                di += 1
            else:
                self.parameters_dict[key]['value'] = self.parameters_dict[key]['p0']

        self.results = res

# methods for calculating error
    def get_variance_from_hessian(self, x, enable_scale=False, func=''):
        x = np.array(x)
        x /= self._get_p0_scale() if enable_scale else np.ones(len(x))
        if func == 'likelihood':
            f = lambda xx: self.log_likelihood_call(xx, enable_scale)
        elif func == 'chi_square':
            f = lambda xx: self.chi_square_call(xx, enable_scale)
        else:
            raise ValueError('undefined function, should be likelihood or chi_square')
        H = nd.Hessian(f)  # ,step=1e-9)
        hh = H(x)
        if func == 'likelihood':
            hh_inv = np.linalg.inv(hh)
        elif func == 'chi_square':
            hh_inv = np.linalg.inv(0.5*hh)
        else:
            raise ValueError('undefined function, should be likelihood or chi_square')
        variance = np.sqrt(np.diag(hh_inv))
        variance *= self._get_p0_scale() if enable_scale else np.ones(len(x))
        self.variance = variance
        di = 0
        for key in self._parameters_order:
            if self.parameters_dict[key]['use']:
                self.parameters_dict[key]['variance'] = variance[di]
                di += 1
        return variance

    def get_location_errors(self, params, simulations, func='', first=None, last=None, delta=None):
        dx = params[0]
        dy = params[1]
        phi = params[2]
        events_rand = (params[3],)  # random
        events_per_sim = ()
        events_per_sim += (params[4],) if self.parameters_dict['pattern_1']['use'] else ()  # pattern 1
        events_per_sim += (params[5],) if self.parameters_dict['pattern_2']['use'] else ()  # pattern 2
        events_per_sim += (params[6],) if self.parameters_dict['pattern_3']['use'] else ()  # pattern 3
        # get patterns
        sims = ()
        sims += (simulations[0],) if self.parameters_dict['pattern_1']['use'] else ()
        sims += (simulations[1],) if self.parameters_dict['pattern_2']['use'] else ()
        sims += (simulations[2],) if self.parameters_dict['pattern_3']['use'] else ()
        print(events_rand, events_per_sim, sims)
        if first is None:
            first = 0
        if last is None:
            last = len(ft.lib.sim_list)
        if func == 'likelihood':
            if delta is None:
                delta = 0.5
            f = lambda s: -ft.log_likelihood(dx, dy, phi, events_rand, s, events_per_sim)
        elif func == 'chi_square':
            if delta is None:
                delta = 1.0
            f = lambda s: ft.chi_square(dx, dy, phi, events_rand, s, events_per_sim)
        else:
            raise ValueError('undefined function, should be likelihood or chi_square')
        estim_max = f(sims)
        crossings = []
        crossings_idx = []
        for i in range(len(sims)):
            estim = []
            temp_sims = np.array(sims)
            for x_sims in range(first, last):
                temp_sims[i] = x_sims
                estim.append(f(temp_sims))
                print(estim[x_sims]-(estim_max-delta))
            estim_diff = np.diff(estim)
            crossings_idx_temp = np.where(np.diff(np.sign(estim-(estim_max-delta))))[0]
            crossings_temp = crossings_idx - (estim-(estim_max-delta))[crossings_idx] / estim_diff[crossings_idx]
            crossings.append(crossings_temp)
            crossings_idx.append(crossings_idx_temp)
            print('crossings_idx - ', crossings_idx_temp)
            print('crossings - ', crossings_temp)
        return crossings, crossings_idx


if __name__ == "__main__":
    import matplotlib.pyplot as plt

    test_curve_fit = False
    test_chi2_min = True
    test_likelihood_max = False

    #lib = lib2dl("/home/eric/cernbox/Channeling_analysis/FDD_libraries/GaN_24Na/ue646g26.2dl")
    lib = lib2dl("/home/eric/cernbox/Channeling_analysis/FDD_libraries/GaN_24Na/ue567g29.2dl")

    ft = fits(lib)
    ft.verbose_graphics = False

    # set a pattern to fit
    #x=np.arange(-1.79,1.8,0.01)
    #xmesh, ymesh = np.meshgrid(x,x)
    #xmesh, ymesh = create_detector_mesh(20, 20, 1.4, 300)
    xmesh, ymesh = create_detector_mesh(50, 50, 0.5, 300)

    #mm = MedipixMatrix(file_path='/home/eric/Desktop/jsontest.json')
    #mm = MedipixMatrix(file_path='/home/eric/cernbox/Channeling_analysis/2015_GaN_24Na/TPX/800C/-1102/pattern_d3_Npix0-20_rebin2x2_180.json')

    mm = MedipixMatrix(file_path='/home/eric/cernbox/Channeling_analysis/2015_GaN_24Na/TPX/800C/-1101/pattern_d3_Npix0-20_rebin16x16_180.json')
    patt = mm.matrixOriginal
    xmesh = mm.xmesh
    ymesh = mm.ymesh

    creator = PatternCreator(lib, xmesh, ymesh, (1,65))#(249-249+1,377-249+1))
    fractions_per_sim = np.array([0.60, 0.30, 0.10]) # first is random
    total_events = 1e6
    patt = creator.make_pattern(-0.08, 0.18, 5, fractions_per_sim, total_events, sigma=0.1, type='poisson')
    #patt = ma.masked_where(xmesh >=1.5,patt)
    #patt = ma.array(data=patt, mask=mm.matrixOriginal.mask)

    plt.figure(0)
    plt.contourf(xmesh, ymesh, patt)#, np.arange(0, 3000, 100))
    plt.colorbar()
    plt.show(block=False)

    # set a fitting routine
    counts_ordofmag = 10**(int(math.log10(patt.sum())))
    ft.set_data_pattern(xmesh, ymesh, patt)
    #ft.set_patterns_to_fit(249-249,377-249)
    ft.set_patterns_to_fit(1,65)#,129)
    ft.parameters_dict['sub_pixels']['value'] = 1

    if test_chi2_min:
        ft.set_scale_values(dx=1, dy=1, phi=1, total_cts=counts_ordofmag, sigma=1, f_p1=1)
        ft.set_inicial_values(0.1, 0.1, 1, counts_ordofmag, sigma=0.1)
        #ft.set_inicial_values(mm.center[0], mm.center[1], mm.angle, counts_ordofmag, sigma=0.1)
        ft.minimize_chi2()
        print(ft.results)
        print('sigma in sim step units - ', ft.results['x'][4] / lib.xstep)
        print('Calculating errors ...')
        #var = ft.get_variance_from_hessian(ft.results['x'], enable_scale=False, func='chi_square')
        #print('var - ', var)
        #ft.print_variance(ft.res['x'],var)
        # x = res['x'] * ft.p0_scale[0:5]
        # ft.set_scale_values()
        # # There is a warning because the hessian starts with a step too big, don't worry about it
        # H = nd.Hessian(ft.log_likelihood_call)#,step=1e-9)
        # hh = H(x)
        # print(hh)
        # print(np.linalg.inv(hh))
        # ft.set_scale_values(dx=1, dy=1, phi=10, f_rand=counts_ordofmag, f_p1=counts_ordofmag)
        # ft.print_results(res,hh)

    if test_likelihood_max:
        ft.set_scale_values(dx=1, dy=1, phi=1, total_cts=-1, f_p1=1, f_p2=1)
        ft.set_inicial_values(-0.05, 0.1, 1, -1, sigma=0.1)
        ft.fix_parameters(True,False,False,False,False,False,False,False)
        #ft.set_inicial_values(mm.center[0], mm.center[1], mm.angle, -1, sigma=0.1)
        ft.maximize_likelyhood()
        print(ft.results)
        print('sigma in sim step units - ', ft.results['x'][4] / lib.xstep)
        print('Calculating errors ...')
        #var = ft.get_variance_from_hessian(ft.results['x'], enable_scale=False, func='likelihood')
        #print('var - ', var)
        #ft.print_variance(ft.res['x'],var)
        #ft.get_location_errors(res['x'], (0,), last=300, func='likelihood')

    print('data points ', np.sum(~patt.mask))

    plt.figure(2)
    plt.contourf(xmesh, ymesh, ft.sim_pattern)
    plt.colorbar()

    plt.figure(3)
    if test_chi2_min:
        plt.contourf(xmesh, ymesh, ft.sim_pattern - patt)
    if test_likelihood_max:
        plt.contourf(xmesh, ymesh, ft.sim_pattern-patt/patt.sum())
    plt.colorbar()
    plt.show(block=True)

