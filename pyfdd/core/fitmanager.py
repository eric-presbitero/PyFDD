#!/usr/bin/env python3

"""
FitManager is the user class for fitting.
"""

# Imports from standard library
import os
import warnings
import collections
import math

# Imports from 3rd party
import pandas as pd
import numpy as np
import numpy.ma as ma
import matplotlib.pyplot as plt

# Imports from project
from pyfdd.core.lib2dl import Lib2dl
from pyfdd.core.patterncreator import PatternCreator
from pyfdd.core.datapattern import DataPattern
from pyfdd.core.fit import Fit


class FitManager:
    """
    The class FitManager is a helper class for using Fit in pyfdd.
    You should be able to do all standard routine analysis from FitManager.
    It also help in creating graphs, using fit options and saving results.
    """

    default_parameter_keys = ['dx', 'dy', 'phi', 'total_cts', 'sigma', 'f_px']
    default_profiles_fit_options = {
            # likelihood values are orders of mag bigger than chi2, so they need smaller ftol
            # real eps is the eps in fit options times the parameter scale
            'coarse': {'ml': {'disp': False, 'maxiter': 10, 'maxfun': 200, 'ftol': 1e-7, 'maxls': 50,
                              'maxcor': 10, 'eps': 1e-8},
                       'chi2': {'disp': False, 'maxiter': 10, 'maxfun': 200, 'ftol': 1e-6, 'maxls': 50,
                                'maxcor': 10, 'eps': 1e-8}},
            'default': {'ml': {'disp': False, 'maxiter': 20, 'maxfun': 200, 'ftol': 1e-9, 'maxls': 100,
                               'maxcor': 10, 'eps': 1e-8},  # maxfun to 200 prevents memory problems,
                        'chi2': {'disp': False, 'maxiter': 20, 'maxfun': 300, 'ftol': 1e-6, 'maxls': 100,
                                 'maxcor': 10, 'eps': 1e-8}},
            'fine': {'ml': {'disp': False, 'maxiter': 60, 'maxfun': 1200, 'ftol': 1e-12, 'maxls': 100,
                            'maxcor': 10, 'eps': 1e-8},
                     'chi2': {'disp': False, 'maxiter': 60, 'maxfun': 1200, 'ftol': 1e-9, 'maxls': 100,
                              'maxcor': 10, 'eps': 1e-8}}
    }
    # total_cts is overwriten with values from the data pattern
    default_scale = {'dx': .01, 'dy': .01, 'phi': 0.10, 'total_cts': 0.01,
                     'sigma': .001, 'f_px': 0.01}
    default_bounds = {'dx': (-3, +3), 'dy': (-3, +3), 'phi': (None, None), 'total_cts': (1, None),
                      'sigma': (0.01, None),  'f_px': (0, 1)}

    # settings methods
    def __init__(self, *, cost_function='chi2', n_sites, sub_pixels=1):
        """
        FitManager is a helper class for using Fit in pyfdd.
        :param cost_function: The type of cost function to use. Possible values are 'chi2' for chi-square
        and 'ml' for maximum likelihood.
        :param sub_pixels: The number of subpixels to integrate during fit in x and y.
        """

        if cost_function not in ('chi2', 'ml'):
            raise ValueError('cost_function not valid. Use chi2 or ml')

        if not isinstance(sub_pixels, (int, np.integer)):
            raise ValueError('sub_pixels must be of type int')

        self.done_param_verbose = False

        # Output
        self.verbose = 1
        self.results = None

        # Stored objects
        self.min_value = None
        self.best_fit = None
        self.last_fit = None
        self.dp_pattern = None
        self.lib = None
        self.current_fit_obj = None

        # Fit settings
        self._n_sites = n_sites
        self._sub_pixels = sub_pixels
        self._cost_function = cost_function
        self._fit_options = {}
        self._fit_options_profile = 'default'
        self._minimization_method = 'L-BFGS-B'
        self._profiles_fit_options = FitManager.default_profiles_fit_options.copy()
        self.set_minimization_settings()

        # Parameter settings
        self.parameter_keys = FitManager.default_parameter_keys.copy()
        self.parameter_keys.pop()  # remove 'f_px'
        for i in range(self._n_sites):
            fraction_key = 'f_p' + str(i+1)  # 'f_p1', 'f_p2', 'f_p3',...
            self.parameter_keys.append(fraction_key)
        self._scale = FitManager.default_scale.copy()
        self._bounds = FitManager.default_bounds.copy()
        fraction_scale = self._scale.pop('f_px')  # remove 'f_px'
        fraction_bounds = self._bounds.pop('f_px')  # remove 'f_px'
        scale_temp = dict()
        bounds_temp = dict()
        for i in range(self._n_sites):
            fraction_key = 'f_p' + str(i+1)  # 'f_p1', 'f_p2', 'f_p3',...
            scale_temp[fraction_key] = fraction_scale
            bounds_temp[fraction_key] = fraction_bounds
        self._scale = {**self._scale, **scale_temp}  # Join dictionaries
        self._bounds = {**self._bounds, **bounds_temp}

        # overwrite defaults from Fit
        self.p_initial_values = dict()
        self.p_fixed_values = dict()

        # order of columns in results
        self.columns_horizontal = \
            ('value', 'D.O.F.', 'x', 'x_err', 'y', 'y_err', 'phi', 'phi_err',
             'counts', 'counts_err', 'sigma', 'sigma_err')
        self.columns_template = \
            ('site{:d} n', 'p{:d}', 'site{:d} description', 'site{:d} factor', 'site{:d} u1',
             'site{:d} fraction', 'fraction{:d}_err')
        for i in range(self._n_sites):
            for k in self.columns_template:
                self.columns_horizontal += (k.format(i + 1),)
        self.columns_horizontal += ('success', 'orientation gradient')

        self.columns_vertical = \
            ('value', 'D.O.F.', 'x', 'x_err', 'y', 'y_err', 'phi', 'phi_err',
             'counts', 'counts_err', 'sigma', 'sigma_err')
        self.columns_vertical += \
            ('site n', 'p', 'site description', 'site factor', 'site u1',
             'site fraction', 'fraction_err')
        self.columns_vertical += ('success', 'orientation gradient')

        self.df_horizontal = pd.DataFrame(data=None, columns=self.columns_horizontal)
        self.df_vertical = pd.DataFrame(data=None)#, columns=self.columns_vertical) # columns are set during filling

    def print(self, *msg):
        """
        This method is overwriten on the GUI to print to the message box
        :param msg:
        :return:
        """
        print(*msg)

    def set_pattern(self, data_pattern, library):
        """
        Set the pattern to fit.
        :param data_pattern: path or DataPattern
        :param library: path or Lib2dl
        """
        if isinstance(data_pattern, DataPattern):
            # all good
            self.dp_pattern = data_pattern
        elif isinstance(data_pattern,  str):
            if not os.path.isfile(data_pattern):
                raise ValueError('data is a str but filepath is not valid')
            else:
                self.dp_pattern = DataPattern(file_path=data_pattern, verbose=self.verbose)
        else:
            ValueError('data_pattern input error')

        if isinstance(library, Lib2dl):
            # all good
            self.lib = library
        elif isinstance(library, str):
            if not os.path.isfile(library):
                raise ValueError('data is a str but filepath is not valid')
            else:
                self.lib = Lib2dl(library)
        else:
            ValueError('data_pattern input error')

        self.print('\nData pattern added')
        self.print('Initial orientation (x, y, phi) is (',
              self.dp_pattern.center[0], ', ', self.dp_pattern.center[1], ',',
              self.dp_pattern.angle, ')')

    def _print_settings(self, ft):
        """
        prints the settings that are in use during fit
        :param ft: Fit object
        """
        assert isinstance(ft, Fit)
        self.print('\n')
        self.print('Fit settings')
        self.print('Cost function       -', self._cost_function)
        self.print('Minimization method -', self._minimization_method)
        self.print('Fit option profile  -', self._fit_options_profile)
        self.print('Fit options         -', self._fit_options)
        self.print('Sub pixels          -', self._sub_pixels)
        self.print('\nParameter settings')
        self.print('{:<16}{:<16}{:<16}{:<16}{:<16}'.format('Name', 'Initial Value', 'Fixed', 'Bounds', 'Scale'))
        string_temp = '{:<16}{:<16.2f}{:<16}{:<16}{:<16}'
        for key in self.parameter_keys:
            # {'p0':None, 'value':None, 'use':False, 'std':None, 'scale':1, 'bounds':(None,None)}
            self.print(string_temp.format(
                key,
                ft._parameters_dict[key]['p0'],
                ft._parameters_dict[key]['use'] == False,
                '({},{})'.format(ft._parameters_dict[key]['bounds'][0],ft._parameters_dict[key]['bounds'][1]),
                ft._parameters_dict[key]['scale']
            ))
        self.print('\n')

        self.done_param_verbose = True

    def set_initial_values(self, **kwargs):
        """
        Set the initial values for a parameter. It might be overwriten if pass_results option is used
        :param kwargs: possible arguments are 'dx','dy','phi','total_cts','sigma','f_p1','f_p2','f_p3'
        """
        #('dx','dy','phi','total_cts','sigma','f_p1','f_p2','f_p3')
        for key in kwargs.keys():
            if key in self.parameter_keys:
                self.p_initial_values[key] = kwargs[key]
            else:
                raise(ValueError, 'key word ' + key + 'is not recognized!' +
                      '\n Valid keys are, \'dx\',\'dy\',\'phi\',\'total_cts\',\'sigma\',\'f_p1\',\'f_p2\',\'f_p3\'')

    def set_fixed_values(self, **kwargs):
        """
        Fix a parameter to a value. Overwrites initial value
        :param kwargs: possible arguments are 'dx','dy','phi','total_cts','sigma','f_p1','f_p2','f_p3'
        """
        #('dx','dy','phi','total_cts','sigma','f_p1','f_p2','f_p3')
        for key in kwargs.keys():
            if key in self.parameter_keys:
                self.p_fixed_values[key] = kwargs[key]
            else:
                raise ValueError('key word ' + key + 'is not recognized!' +
                       '\n Valid keys are, \'dx\',\'dy\',\'phi\',\'total_cts\',\'sigma\',\'f_p1\',\'f_p2\',\'f_p3\'')

    def set_bounds(self, **kwargs):
        """
        Set bounds to a paramater. Bounds are a tuple with two values, for example, (0, None).
        :param kwargs: possible arguments are 'dx','dy','phi','total_cts','sigma','f_p1','f_p2','f_p3'
        """
        #('dx','dy','phi','total_cts','sigma','f_p1','f_p2','f_p3')
        for key in kwargs.keys():
            if key in self.parameter_keys:
                if not isinstance(kwargs[key], tuple) or len(kwargs[key]) != 2:
                    raise ValueError('Bounds must be a tuple of length 2.')
                self._bounds[key] = kwargs[key]
            else:
                raise ValueError('key word ' + key + 'is not recognized!' +
                       '\n Valid keys are, \'dx\',\'dy\',\'phi\',\'total_cts\',\'sigma\',\'f_p1\',\'f_p2\',\'f_p3\'')

    def set_step_modifier(self, **kwargs):
        """
        Set a step modifier value for a parameter.
        If a modifier of 10 is used for parameter P the fit will try step 10x the default step.
        For the L-BFGS-B minimization method the default steps are 1 for each value exept for the total counts
        that is the order of magnitude of the counts in the data pattern
        :param kwargs: possible arguments are 'dx','dy','phi','total_cts','sigma','f_p1','f_p2','f_p3'
        """
        #('dx','dy','phi','total_cts','sigma','f_p1','f_p2','f_p3')
        for key in kwargs.keys():
            if key in self.parameter_keys:
                self._scale[key] = kwargs[key]
            else:
                raise ValueError('key word ' + key + 'is not recognized!' +
                       '\n Valid keys are, \'dx\',\'dy\',\'phi\',\'total_cts\',\'sigma\',\'f_p1\',\'f_p2\',\'f_p3\'')

    def set_minimization_settings(self, profile='default', min_method='L-BFGS-B', options=None):
        """
        Set the options for the minimization.
        :param profile: choose between 'coarse', 'default' and 'fine', predefined options.
        :param min_method: minimization algorith to use.
        :param options: python dict with options to use. overwrites profile.
        """
        # Using a coarse profile will lead to faster results but less optimized.
        # Using a fine profile can lead to rounding errors and jumping to other minima which causes artifacts
        # scipy default eps is 1e-8 this, sometimes, is too small to correctly get the derivative of phi
        if not isinstance(options, dict) and options is not None:
            raise ValueError('options must be of type dict.')

        if options is None:
            options = dict()

        if not isinstance(min_method, str):
            raise ValueError('min_method must be of type str.')

        if profile not in ('coarse', 'default', 'fine', 'custom'):
            raise ValueError('profile value should be set to: coarse, default or fine.')

        self._minimization_method = min_method

        if len(options) > 0:
            self._fit_options = options
            self._fit_options_profile = 'custom'

        elif min_method == 'L-BFGS-B':
            self._fit_options_profile = profile
            self._fit_options = self._profiles_fit_options[profile][self._cost_function]

        else:
            warnings.warn('No profile for method {} and no options provided. Using library defaults'.format(min_method))

    def get_pattern_counts(self, ignore_masked=True):
        """
        Get the total counts of the pattern to be fit
        :param ignore_masked:
        :return:
        """

        if not isinstance(ignore_masked, bool):
            raise ValueError('ignore_masked must be of type bool.')

        if self.dp_pattern is None:
            raise ValueError('The data_pattern is not properly set.')

        if ignore_masked:
            total_cts = self.dp_pattern.pattern_matrix.sum()
        else:
            total_cts = self.dp_pattern.pattern_matrix.data.sum()
        return total_cts

    def _get_initial_values(self, pass_results=False):
        """
        Get the initial values for the next fit
        :param pass_results: Use the previous fit results
        :return p0, p_fix: initial values and tuple of bools indicating if it is fixed
        """
        # decide if using last fit results
        p0_pass = pass_results \
            and self.last_fit is not None \
            and self.last_fit.results['success']

        new_initial_values = self.p_initial_values.copy()

        if p0_pass:  # change initial values
            p0_last = self.last_fit.results['x']
            p0_last_i = 0

            for key in self.parameter_keys:
                if key in self.p_fixed_values:
                    pass  # Fixed, dont change
                else:
                    # starting too close from a minimum can cause errors so 1e-5 is added
                    new_initial_values[key] = p0_last[p0_last_i] + 1e-5
                    p0_last_i += 1

        p0, p_fix = self.compute_initial_fit_values(
                            datapattern=self.dp_pattern,
                            n_sites=self._n_sites,
                            p_fixed_values=self.p_fixed_values,
                            p_initial_values=new_initial_values)

        return p0, p_fix

    def _get_scale_values(self):
        scale = ()
        for key in self.parameter_keys:
            # ('dx','dy','phi','total_cts','sigma','f_p1','f_p2','f_p3')
            # total_cts is a spacial case at it uses the counts from the pattern
            if key == 'total_cts':
                if self._cost_function == 'chi2':
                    patt = self.dp_pattern.pattern_matrix
                    counts_ordofmag = 10 ** (int(math.log10(patt.sum())))
                    scale += (counts_ordofmag * self._scale[key],)
                elif self._cost_function == 'ml':
                    scale += (-1,)
            else:
                scale += (self._scale[key],)
        return scale

    def _build_fits_obj(self, sites, verbose_graphics=False, pass_results=False):
        """
        Builds a Fit object
        :param p1: pattern 1
        :param p2: pattern 2
        :param p3: pattern 3
        :param verbose_graphics: plot pattern as it is being fit
        :param pass_results: argument for _get_initial_values
        :return: Fit object
        """

        ft = Fit(self.lib, sites, verbose_graphics)

        ft.set_sub_pixels(self._sub_pixels)
        ft.set_fit_options(self._fit_options)

        patt = self.dp_pattern.pattern_matrix
        xmesh = self.dp_pattern.xmesh
        ymesh = self.dp_pattern.ymesh
        ft.set_data_pattern(xmesh, ymesh, patt)

        # Get initial values
        p0, p0_fix = self._get_initial_values(pass_results=pass_results)

        # Get scale
        scale = self._get_scale_values()

        # base input
        scale_dict = {
            'dx':scale[0], 'dy':scale[1], 'phi':scale[2], 'total_cts':scale[3], 'sigma':scale[4]
        }
        init_dict = {
            'dx':p0[0], 'dy':p0[1], 'phi':p0[2], 'total_cts':p0[3], 'sigma':p0[4]
        }
        fix_dict = {
            'dx': p0_fix[0], 'dy': p0_fix[1], 'phi': p0_fix[2], 'total_cts': p0_fix[3], 'sigma': p0_fix[4]
        }
        bound_dict = {
            'dx':self._bounds['dx'], 'dy':self._bounds['dy'], 'phi':self._bounds['phi'],
            'total_cts':self._bounds['total_cts'], 'sigma':self._bounds['sigma']
        }
        # add site values

        for i in range(self._n_sites):
            fraction_key = 'f_p' + str(i + 1)  # 'f_p1', 'f_p2', 'f_p3',...
            scale_dict[fraction_key] = scale[5+i]
            init_dict[fraction_key] = p0[5+i]
            fix_dict[fraction_key] = p0_fix[5+i]
            bound_dict[fraction_key] = self._bounds[fraction_key]

        ft.set_scale_values(**scale_dict)
        ft.set_initial_values(**init_dict)
        ft.fix_parameters(**fix_dict)
        ft.set_bound_values(**bound_dict)

        return ft

    def _fill_horizontal_results_dict(self, ft, get_errors, sites):#p1=None, p2=None, p3=None):
        assert isinstance(ft, Fit), "ft is not of type PyFDD.Fit."

        patt = self.dp_pattern.pattern_matrix.copy()

        # keys are 'pattern_1','pattern_2','pattern_3','sub_pixels','dx','dy','phi',
        # 'total_cts','sigma','f_p1','f_p2','f_p3'
        parameter_dict = ft._parameters_dict.copy()
        append_dic = {}
        append_dic['value'] = ft.results['fun']
        append_dic['success'] = ft.results['success']
        append_dic['orientation gradient'] = np.linalg.norm(ft.results['orientation jac'])
        append_dic['D.O.F.'] = ft.get_dof()
        append_dic['x'] = parameter_dict['dx']['value']
        append_dic['y'] = parameter_dict['dy']['value']
        append_dic['phi'] = parameter_dict['phi']['value']
        append_dic['counts'] = parameter_dict['total_cts']['value'] if self._cost_function == 'chi2' else np.nan
        append_dic['sigma'] = parameter_dict['sigma']['value']

        for i in range(self._n_sites):
            patt_num = sites[i] # index of the pattern in dict_2dl is patt_num - 1
            append_dic['site{:d} n'.format(i + 1)] = self.lib.dict_2dl["Spectrums"][patt_num - 1]["Spectrum number"]
            append_dic['p{:d}'.format(i + 1)] = patt_num
            append_dic['site{:d} description'.format(i + 1)] = \
                self.lib.dict_2dl["Spectrums"][patt_num - 1]["Spectrum_description"]
            append_dic['site{:d} factor'.format(i + 1)] = self.lib.dict_2dl["Spectrums"][patt_num - 1]["factor"]
            append_dic['site{:d} u1'.format(i + 1)] = self.lib.dict_2dl["Spectrums"][patt_num - 1]["u1"]
            append_dic['site{:d} fraction'.format(i + 1)] = parameter_dict['f_p{:d}'.format(i + 1)]['value']

        if get_errors:
            append_dic['x_err'] = parameter_dict['dx']['std']
            append_dic['y_err'] = parameter_dict['dy']['std']
            append_dic['phi_err'] = parameter_dict['phi']['std']
            append_dic['counts_err'] = parameter_dict['total_cts']['std'] if self._cost_function == 'chi2' else np.nan
            append_dic['sigma_err'] = parameter_dict['sigma']['std']
            for i in range(self._n_sites):
                append_dic['fraction{:d}_err'.format(i + 1)] = \
                    parameter_dict['f_p{:d}'.format(i + 1)]['std']

        self.df_horizontal = self.df_horizontal.append(append_dic, ignore_index=True)
        self.df_horizontal = self.df_horizontal[list(self.columns_horizontal)]

    def _fill_vertical_results_dict(self, ft, get_errors, sites):#p1=None, p2=None, p3=None):
        assert isinstance(ft, Fit), "ft is not of type PyFDD.Fit."

        patt = self.dp_pattern.pattern_matrix.copy()

        # keys are 'pattern_1','pattern_2','pattern_3','sub_pixels','dx','dy','phi',
        # 'total_cts','sigma','f_p1','f_p2','f_p3'
        parameter_dict = ft._parameters_dict.copy()
        append_dic = {}
        append_dic['value'] = ft.results['fun']
        append_dic['success'] = ft.results['success']
        append_dic['orientation gradient'] = np.linalg.norm(ft.results['orientation jac'])
        append_dic['D.O.F.'] = ft.get_dof()
        append_dic['x'] = parameter_dict['dx']['value']
        append_dic['y'] = parameter_dict['dy']['value']
        append_dic['phi'] = parameter_dict['phi']['value']
        append_dic['counts'] = parameter_dict['total_cts']['value'] if self._cost_function == 'chi2' else np.nan
        append_dic['sigma'] = parameter_dict['sigma']['value']

        if get_errors:
            append_dic['x_err'] = parameter_dict['dx']['std']
            append_dic['y_err'] = parameter_dict['dy']['std']
            append_dic['phi_err'] = parameter_dict['phi']['std']
            append_dic['counts_err'] = parameter_dict['total_cts']['std'] if self._cost_function == 'chi2' else np.nan
            append_dic['sigma_err'] = parameter_dict['sigma']['std']
        else:
            append_dic['x_err'] = np.nan
            append_dic['y_err'] = np.nan
            append_dic['phi_err'] = np.nan
            append_dic['counts_err'] = np.nan
            append_dic['sigma_err'] = np.nan

        # print('append_dic ', append_dic)
        main_columns = pd.DataFrame().append(append_dic, ignore_index=True)

        for i in range(self._n_sites):
            patt_num = sites[i]  # index of the pattern in dict_2dl is patt_num - 1
            if i == 0:
                append_dic = {}
                append_dic['site n'] = [self.lib.dict_2dl["Spectrums"][patt_num - 1]["Spectrum number"], ]
                append_dic['p'] = [patt_num, ]
                append_dic['site description'] = \
                    [self.lib.dict_2dl["Spectrums"][patt_num - 1]["Spectrum_description"], ]
                append_dic['site factor'] = [self.lib.dict_2dl["Spectrums"][patt_num - 1]["factor"], ]
                append_dic['site u1'] = [self.lib.dict_2dl["Spectrums"][patt_num - 1]["u1"], ]
                append_dic['site fraction'] = [parameter_dict['f_p{:d}'.format(i + 1)]['value'], ]
                if get_errors:
                    append_dic['fraction_err'] = \
                        [parameter_dict['f_p{:d}'.format(i + 1)]['std'], ]
                else:
                    append_dic['fraction_err'] = np.nan
            else:
                append_dic['site n'] += [self.lib.dict_2dl["Spectrums"][patt_num - 1]["Spectrum number"], ]
                append_dic['p'] += [patt_num, ]
                append_dic['site description'] += \
                    [self.lib.dict_2dl["Spectrums"][patt_num - 1]["Spectrum_description"], ]
                append_dic['site factor'] += [self.lib.dict_2dl["Spectrums"][patt_num - 1]["factor"], ]
                append_dic['site u1'] += [self.lib.dict_2dl["Spectrums"][patt_num - 1]["u1"], ]
                append_dic['site fraction'] += [parameter_dict['f_p{:d}'.format(i + 1)]['value'], ]
                if get_errors:
                    append_dic['fraction_err'] += \
                        [parameter_dict['f_p{:d}'.format(i + 1)]['std'], ]
                else:
                    append_dic['fraction_err'] += np.nan


        temp_df = pd.concat([main_columns, pd.DataFrame.from_dict(append_dic)],
                                     axis=1 ,ignore_index=False)

        self.df_vertical = self.df_vertical.append(temp_df, ignore_index=True, sort=False)
        self.df_vertical = self.df_vertical[list(self.columns_vertical)]

    def run_fits(self, *args, pass_results=False, verbose=1, get_errors=False):
        """
        Run Fit for a list of sites.
        :param args: list of patterns for each site. Up to tree sites are possible
        :param pass_results: Use the last fit parameter results as input for the next.
        :param verbose: 0 silent, 1 default and 2 max verbose
        :return:
        """

        if not self.is_datapattern_inrange():
            warnings.warn('The datapattern is not in the simulation range. \n'
                          'Consider reducing the fit range arount the axis.')
            raise ValueError

        self.done_param_verbose = False

        patterns_list = ()
        #print('args, ',args)
        for ar in args:
            # if a pattern index is just a scalar make it iterable
            patterns_list += (np.atleast_1d(np.array(ar)),)
        assert len(patterns_list) >= 1

        def recursive_call(patterns_list, sites = ()):
            #print('patterns_list, sites -', patterns_list, sites)
            if len(patterns_list) > 0:
                for s in patterns_list[0]:
                    sites_new = sites + (s,)
                    recursive_call(patterns_list[1:], sites_new)
            else:
                # visualization is by default off in run_fits
                self._single_fit(sites, verbose=verbose, pass_results=pass_results, get_errors=get_errors)
        try:
            recursive_call(patterns_list)
        except:
            # Reset current fit object
            self.current_fit_obj = None

    def run_single_fit(self, *args, verbose=1,
                       verbose_graphics=False, get_errors=False):

        if not self.is_datapattern_inrange():
            warnings.warn('The datapattern is not in the simulation range. \n'
                          'Consider reducing the fit range arount the axis.')

        args = list(args)
        sites = ()
        for i in range(len(args)):
            # Convert array of single number to scalar
            if isinstance(args[i], (np.ndarray, collections.Sequence)) and len(args[i]) == 1:
                args[i] = args[i][0]
            # Ensure index is an int.
            if not isinstance(args[i], (int, np.integer)):
                raise ValueError('Each pattern index must an int.')
            sites += (args[i],)

        self.done_param_verbose = False

        try:
            self._single_fit(sites, get_errors=get_errors, pass_results=False,
                         verbose=verbose, verbose_graphics=verbose_graphics)
        except:
            # Reset current fit object
            self.current_fit_obj = None

    def _single_fit(self, sites, get_errors=False, pass_results=False,
                    verbose=1, verbose_graphics=False):

        if not isinstance(sites, collections.Sequence):
            if isinstance(sites, (int, np.integer)):
                sites = (sites,)
            else:
                raise ValueError('sites needs to be an int or a sequence of ints')
        for s in sites:
            if not isinstance(s, (int, np.integer)):
                raise ValueError('sites needs to be an int or a sequence of ints')

        # Ensure the number of sites indexes is the same as the number of sites in __init__
        if len(sites) != self._n_sites:
            raise ValueError('Error, you need to input the pattern indices for all the '
                             '{0} expected sites. {1} were provided. '
                             'The expected number of sites can be '
                             'changed in the constructor.'.format(self._n_sites, len(sites)))

        # sanity check
        assert isinstance(verbose_graphics, bool)
        assert isinstance(get_errors, bool)
        assert isinstance(self.dp_pattern, DataPattern)

        self.current_fit_obj = self._build_fits_obj(sites, verbose_graphics, pass_results=pass_results)

        if verbose > 0 and self.done_param_verbose is False:
            self._print_settings(self.current_fit_obj)

        if verbose > 0:
            self.print('Sites (P1, P2, ...) - ', sites)

        self.current_fit_obj.minimize_cost_function(self._cost_function)

        if verbose > 1:
            print(self.current_fit_obj.results)

        if get_errors:
            self.current_fit_obj.get_std_from_hessian(self.current_fit_obj.results['x'], enable_scale=True, func=self._cost_function)

        self._fill_horizontal_results_dict(self.current_fit_obj, get_errors, sites)
        self._fill_vertical_results_dict(self.current_fit_obj, get_errors, sites)

        # Keep best fit
        if self.min_value is None:
            self.best_fit = self.current_fit_obj
            self.min_value = self.current_fit_obj.results['fun']
        elif self.current_fit_obj.results['fun'] < self.min_value:
           self.best_fit = self.current_fit_obj
           self.min_value = self.current_fit_obj.results['fun']

        self.last_fit = self.current_fit_obj

        # Reset current fit object
        self.current_fit_obj = None

    def stop_current_fit(self):
        if self.current_fit_obj is not None:
            self.current_fit_obj.stop_current_fit()

    def is_datapattern_inrange(self, orientation_values=None):

        if orientation_values is not None and len(orientation_values) < 3:
            raise ValueError('Orientation_values need to be at least of lenght 3.')

        if orientation_values is None:
            orientation_values, _ = self._get_initial_values()

        dx = orientation_values[0]
        dy = orientation_values[1]
        phi = orientation_values[2]

        # generate sim pattern
        gen = PatternCreator(self.lib, self.dp_pattern.xmesh, self.dp_pattern.ymesh, 1,
                             mask=self.dp_pattern.pattern_matrix.mask,  # need the mask for the normalization
                             sub_pixels=self._sub_pixels,
                             mask_out_of_range=True)
        # mask out of range false means that points that are out of the range of simulations are not masked,
        # instead they are substituted by a very small number 1e-12
        sim_pattern = gen.make_pattern(dx, dy, phi, 0, 1, sigma=0, pattern_type='ideal')

        # Logic verification
        # Data points that are not masked should not be in a position where the simulation is masked
        data_mask = self.dp_pattern.pattern_matrix.mask
        sim_mask = sim_pattern.mask
        inrange = not np.any(~data_mask == sim_mask)

        return inrange

    # results and output methods
    def save_output(self, filename, layout='horizontal', save_figure=False):
        if layout == 'horizontal':
            df = self.df_horizontal
        if layout == 'vertical':
            df = self.df_vertical

        base_name, ext = os.path.splitext(filename)
        if ext == '.txt' or ext == '.csv':
            df.to_csv(filename)
        elif ext == '.xlsx' or ext == '.xls':
            df.to_excel(filename)
        else:
            raise ValueError('Extention not recognized, use txt, csv, xls or xlsx')

        if save_figure:
            xmesh = self.best_fit.XXmesh
            ymesh = self.best_fit.YYmesh
            # data pattern
            fig = plt.figure()
            plt.contourf(xmesh, ymesh, self.best_fit.data_pattern)
            plt.colorbar()
            fig.savefig(base_name + '_data.png')
            plt.close(fig)
            # sim pattern
            fig = plt.figure()
            plt.contourf(xmesh, ymesh, self.best_fit.sim_pattern)
            plt.colorbar()
            fig.savefig(base_name + '_sim.png')
            plt.close(fig)
            # sim-data pattern
            fig = plt.figure()
            plt.contourf(xmesh, ymesh, self.best_fit.sim_pattern - self.best_fit.data_pattern)
            plt.colorbar()
            fig.savefig(base_name + '_sim-data.png')
            plt.close(fig)

    def _get_sim_normalization_factor(self, normalization, pattern_type, fit_obj=None):

        assert isinstance(fit_obj, Fit) or fit_obj is None
        total_counts = np.sum(self.dp_pattern.pattern_matrix)
        if fit_obj is None:
            total_yield = None
        else:
            sim_pattern = self._gen_detector_pattern_from_fit(fit_obj=fit_obj, generator='yield', rm_mask=False)
            total_yield = sim_pattern.sum()
            # print('total_yield', total_yield, '# pixels', np.sum(~sim_pattern.mask))
            #total_yield = np.sum(~self.dp_pattern.pattern_matrix.mask)
        norm_factor = None
        if normalization is None:
            norm_factor = 1
        elif normalization == 'counts':
            if pattern_type == 'chi2' or pattern_type == 'data':
                norm_factor = 1
            elif pattern_type == 'ml':
                norm_factor = total_counts
        elif normalization == 'yield':
            if total_yield is None:
                raise ValueError('Simulation pattern is not defined.')
            if pattern_type == 'chi2' or pattern_type == 'data':
                norm_factor = total_yield / total_counts
            elif pattern_type == 'ml':
                norm_factor = total_yield
        elif normalization == 'probability':
            if  pattern_type == 'chi2' or pattern_type == 'data':
                norm_factor = 1 / total_counts
            elif pattern_type == 'ml':
                norm_factor = 1
        else:
            raise ValueError('normalization needs to be, None, \'counts\', \'yield\' or \'probability\'')
        return norm_factor

    def _gen_detector_pattern_from_fit(self, fit_obj, generator='ideal', rm_mask=False):

        assert isinstance(fit_obj, Fit)

        # get values
        parameter_dict = fit_obj._parameters_dict.copy()
        dx = parameter_dict['dx']['value']
        dy = parameter_dict['dy']['value']
        phi = parameter_dict['phi']['value']
        total_events = parameter_dict['total_cts']['value'] if self._cost_function == 'chi2' else \
            np.sum(self.dp_pattern.pattern_matrix)
        sigma = parameter_dict['sigma']['value']
        fractions_sims = ()
        for i in range(self._n_sites):
            fractions_sims += (parameter_dict['f_p{:d}'.format(i + 1)]['value'],)

        # generate sim pattern
        gen = PatternCreator(fit_obj._lib, fit_obj.XXmesh, fit_obj.YYmesh, fit_obj._sites_idx,
                             mask=fit_obj.data_pattern.mask, # need the mask for the normalization
                             sub_pixels=parameter_dict['sub_pixels']['value'],
                             mask_out_of_range = True)
        # mask out of range false means that points that are out of the range of simulations are not masked,
        # instead they are substituted by a very small number 1e-12
        sim_pattern = gen.make_pattern(dx, dy, phi, fractions_sims, total_events, sigma=sigma, pattern_type=generator)

        # Substitute only masked pixels that are in range (2.7° from center) and are not the chip edges
        # This can't really be made without keeping 2 set of masks, so all masked pixels are susbstituted.
        # This means some pixels with valid data but masked can still be susbtituted
        if rm_mask:
            # only mask what is outside of simulation range
            sim_pattern_ideal = gen.make_pattern(dx, dy, phi, fractions_sims, total_events, sigma=sigma, pattern_type='ideal')
            return ma.array(sim_pattern.data, mask=(sim_pattern_ideal.data == 0))
        else:
            return sim_pattern

    def get_pattern_from_last_fit(self, normalization=None):
        fit_obj = self.last_fit
        assert isinstance(fit_obj, Fit)
        #print(fit_obj.sim_pattern.data)

        norm_factor = \
            self._get_sim_normalization_factor(normalization, pattern_type=self._cost_function, fit_obj=fit_obj)

        dp = DataPattern(pattern_array=fit_obj.sim_pattern.data)
        dp.set_xymesh(fit_obj.XXmesh, fit_obj.YYmesh)
        dp.set_mask(fit_obj.sim_pattern.mask)

        return dp * norm_factor

    def get_pattern_from_best_fit(self, normalization=None):
        fit_obj = self.best_fit
        assert isinstance(fit_obj, Fit)
        #print(fit_obj.sim_pattern.data)

        norm_factor = \
            self._get_sim_normalization_factor(normalization, pattern_type=self._cost_function, fit_obj=fit_obj)

        dp = DataPattern(pattern_array=fit_obj.sim_pattern.data)
        dp.set_xymesh(fit_obj.XXmesh, fit_obj.YYmesh)
        dp.set_mask(fit_obj.sim_pattern.mask)
        return dp * norm_factor

    def get_datapattern(self, normalization=None, substitute_masked_with=None, which_fit='last'):

        # which_fit can be the best or last
        if which_fit == 'best':
            fit_obj = self.best_fit
        elif which_fit == 'last':
            fit_obj = self.last_fit
        else:
            raise ValueError('parameter fit must be either \'best\' or \'last\'')

        dp_pattern = self.dp_pattern.copy()

        if substitute_masked_with is not None:
            # Get a pattern with no mask besides what is outside of the simulation.
            sim_pattern = self._gen_detector_pattern_from_fit(fit_obj=fit_obj, generator=substitute_masked_with,
                                                              rm_mask=True)

            # Substitute pixels that are masked and that are not in the fitregion mask
            substitute_matrix = np.logical_and(dp_pattern.pixels_mask,
                                               np.logical_not(sim_pattern.mask))

            dp_pattern.pattern_matrix.data[substitute_matrix] = \
                sim_pattern.data[substitute_matrix]
            dp_pattern.clear_mask(pixels_mask=True, fitregion_mask=True)

        norm_factor = self._get_sim_normalization_factor(normalization, pattern_type='data', fit_obj=fit_obj)

        return dp_pattern * norm_factor

    @staticmethod
    def compute_parameter_keys(n_sites=1):
        # Set the parameter keys
        # Example: ('dx','dy','phi','total_cts','sigma','f_p1','f_p2','f_p3')
        parameter_keys = FitManager.default_parameter_keys.copy()
        parameter_keys.pop()  # remove 'f_px'
        for i in range(n_sites):
            fraction_key = 'f_p' + str(i + 1)  # 'f_p1', 'f_p2', 'f_p3',...
            parameter_keys.append(fraction_key)

        return parameter_keys

    @staticmethod
    def compute_initial_fit_values(datapattern: DataPattern, n_sites=1,
                                   p_fixed_values=None, p_initial_values=None):
        """
        Static method to get the initial values for the next fit according to a given DataPattern.
        :param datapattern: DataPattern object to fit
        :param n_sites: Number of sites in the fit
        :param p_fixed_values: User defined fixed values
        :param p_initial_values: User defined initial values
        :return: p0, p_fix: initial values and tuple of bools indicating if it is fixed
        """

        # Set the parameter keys
        # Example: ('dx','dy','phi','total_cts','sigma','f_p1','f_p2','f_p3')
        parameter_keys = FitManager.compute_parameter_keys(n_sites)

        # If None make them as empty dictionaries
        if p_fixed_values is None:
            p_fixed_values = dict()

        if p_initial_values is None:
            p_initial_values = dict()

        p0 = ()
        p_fix = ()

        for key in parameter_keys:
            # Use user defined fixed value
            if key in p_fixed_values:
                p0 += (p_fixed_values[key],)
                p_fix += (True,)

            # Use user defined initial value
            elif key in p_initial_values:
                p0 += (p_initial_values[key],)
                p_fix += (False,)

            # Use FitManager choice
            else:
                if key == 'dx':
                    p0 += (datapattern.center[0],)
                    p_fix += (False,)
                elif key == 'dy':
                    p0 += (datapattern.center[1],)
                    p_fix += (False,)
                elif key == 'phi':
                    p0 += (datapattern.angle,)
                    p_fix += (False,)
                elif key == 'total_cts':
                    counts = datapattern.pattern_matrix.sum()
                    p0 += (counts,)
                    p_fix += (True,)  # Defaults to fixed
                elif key == 'sigma':
                    p0 += (0.1,)
                    p_fix += (True,)  # Defaults to fixed
                else:
                    # assuming a pattern fraction
                    p0 += (min(0.15, 0.5 / n_sites),)
                    p_fix += (False,)


        return p0, p_fix

    @staticmethod
    def compute_bounds(datapattern: DataPattern = None, n_sites=1, p_bounds=None):
        """
        Static method to compute the fit bounds
        :param datapattern: DataPattern object used to compute the bounds of dx and dy
        :param n_sites: Number of sites in the fit
        :param p_bounds: User overwrite of bounds
        :return: bounds dictionary
        """

        p_bounds = dict() if p_bounds is None else p_bounds

        # Set the parameter keys
        # Example: ('dx','dy','phi','total_cts','sigma','f_p1','f_p2','f_p3')
        parameter_keys = FitManager.compute_parameter_keys(n_sites)

        # Compute defaults
        bounds = FitManager.default_bounds.copy()
        default_fraction_bounds = bounds.pop('f_px')  # remove 'f_px'
        bounds_temp = dict()
        for i in range(n_sites):
            fraction_key = 'f_p' + str(i + 1)  # 'f_p1', 'f_p2', 'f_p3',...
            bounds_temp[fraction_key] = default_fraction_bounds
        bounds = {**bounds, **bounds_temp}  # Join dictionaries

        # Computer with user input and datapattern
        if datapattern is not None:
            bounds['dx'] = (np.round(datapattern.xmesh[0, 0], 2),
                            np.round(datapattern.xmesh[0, -1], 2))
            bounds['dy'] = (np.round(datapattern.ymesh[0, 0], 2),
                            np.round(datapattern.ymesh[-1, 0], 2))

        for key in parameter_keys:
            if key in p_bounds:
                bounds[key] = p_bounds[key]

        return bounds

    @staticmethod
    def compute_step_modifier(n_sites=1, p_scale=None):
        """
        Static method to compute the fit step modifiers (scale)
        :param n_sites: Number of sites in the fit
        :param p_scale: User overwrite of bounds
        :return: step modifier dictionary
        """

        p_scale = dict() if p_scale is None else p_scale

        # Set the parameter keys
        # Example: ('dx','dy','phi','total_cts','sigma','f_p1','f_p2','f_p3')
        parameter_keys = FitManager.compute_parameter_keys(n_sites)

        # Compute defaults
        scale = FitManager.default_scale.copy()
        default_fraction_scale = scale.pop('f_px')  # remove 'f_px'
        scale_temp = dict()
        for i in range(n_sites):
            fraction_key = 'f_p' + str(i + 1)  # 'f_p1', 'f_p2', 'f_p3',...
            scale_temp[fraction_key] = default_fraction_scale
        scale = {**scale, **scale_temp}  # Join dictionaries

        # Computer with user input
        for key in parameter_keys:
            if key in p_scale:
                scale[key] = p_scale[key]

        return scale


